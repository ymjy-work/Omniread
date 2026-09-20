"""评测 run 产物落盘（M0-02 §7.1）；`eval/` 进 git，按红线约束写法。

与映射侧同一套规矩（`domain.artifacts`）：**字段白名单 + 长度上限**，两半都要。
逐题记录是 frozen dataclass，`asdict` 出来的字段集就是允许进 git 的全部内容；
写入前再递归查一遍字符串长度兜底。

两个只在 generation 层才出现的正文入口，这里预先堵死（M0-04 §5.2）：

- **judge 的解释文本**。DeepEval 的指标结果不是裸数字而是 `{score, reason, ...}`，
  `reason` 是 LLM judge 的自然语言解释，按定义会复述回答原文与检索上下文。
  落盘的只能有 `metric` 名与标量分数，`reason` / `rationale` / `explanation`
  与整个 `LLMTestCase` 一律不进。
- **回答原文**。`answer_citation_membership` 只需要引用标记的解析结果，
  `leak_text` 只需要越界引用的**标记本身**（`[C数字]` 那种短 token），
  都不是「答案里的一段话」。规范没给 `leak_text` 的落盘形状，本模块把它定为
  有界的引用标记列表——按字面存「答案里的越界片段」就是泄漏。

`verify_artifacts.py` 的「与语料逐字重合」比对**对生成文本天然失效**（模型写的答案
不是语料），所以 generation 层的防线只能是这里的字段白名单，不能指望那条比对。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from omniread.domain.artifacts import guard_payload
from omniread.pipelines.evaluation.types import RetrievalScoreRecord


@dataclass(frozen=True, slots=True)
class EvalRunConfig:
    """本次评测 run 的参数快照，供 baseline diff。

    只列白名单字段。**不要**改成 `Mapping[str, Any]`、也不要塞 `Settings.model_dump()`：
    `minio_access_key` 是普通 str，整体 dump 会把凭据写进仓库。
    """

    run_id: str
    kind: str
    phase: str
    dataset_hash: str
    dataset_version: str
    corpus_manifest_hash: str
    chunking_version: str
    tokenizer_id: str
    chunk_source: str
    retrieval_provider: str
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    rerank_provider: str
    rerank_model: str
    # 检索参数整体快照（M0-00 §5 的旋钮），改一个即新基线。
    retrieval_params: dict[str, object] = field(default_factory=dict)
    # 只有真 provider 才谈得上「结果可信」；离线跑必须显式记下来，
    # 免得日后把噪声数字当成 baseline。
    trust_note: str = ""


def write_eval_run_dir(
    run_dir: Path,
    *,
    config: EvalRunConfig,
    retrieval_records: Sequence[RetrievalScoreRecord] = (),
    summary: Mapping[str, Any] | None = None,
    failures: Sequence[Mapping[str, Any]] = (),
) -> None:
    """写一个评测 run 的产物目录；已存在则整体重写（同一 run_id 重跑即覆盖）。

    只写传进来的那几类文件——检索层 run 不产 `generation.scores.jsonl`，
    空文件会让人以为「跑了但全是 0」。缺哪类就是没跑哪类。
    """
    run_dir.mkdir(parents=True, exist_ok=True)

    config_payload = asdict(config)
    guard_payload("config.json", config_payload)

    if summary is not None:
        summary_payload = dict(summary)
        guard_payload("summary.json", summary_payload)
        _write_json(run_dir / "summary.json", summary_payload)
    _write_json(run_dir / "config.json", config_payload)

    if retrieval_records:
        rows = [asdict(record) for record in retrieval_records]
        for row in rows:
            guard_payload("retrieval.scores.jsonl", row)
        _write_jsonl(run_dir / "retrieval.scores.jsonl", rows)

    # 失败清单只落 `failures.md`（M0-02 §7.1 的目录布局里没有 failures.jsonl）。
    # 逐条内容仍是「指针 + 阶段 + 指标快照」，渲染时由 `_render_failures_markdown` 限制。
    for item in failures:
        guard_payload("failures.md", dict(item))

    if summary is not None:
        (run_dir / "summary.md").write_text(
            _render_summary_markdown(config, summary), encoding="utf-8", newline="\n"
        )
        (run_dir / "failures.md").write_text(
            _render_failures_markdown(failures), encoding="utf-8", newline="\n"
        )


def _render_summary_markdown(config: EvalRunConfig, summary: Mapping[str, Any]) -> str:
    """只写计数与比率，不写任何题面或正文。"""
    lines = [
        f"# 评测 run {config.run_id}",
        "",
        f"- 阶段：{config.phase}；kind：{config.kind}",
        f"- dataset_hash：`{config.dataset_hash}`（schema {config.dataset_version}）",
        f"- corpus_manifest_hash：`{config.corpus_manifest_hash}`",
        f"- 切片：`{config.chunking_version}`；chunk 来源：{config.chunk_source}",
        f"- embedding：{config.embedding_provider} / `{config.embedding_model}`"
        f"（{config.embedding_dim} 维）",
        f"- rerank：{config.rerank_provider} / `{config.rerank_model}`",
        f"- 题目数：{summary.get('question_count', 0)}",
        "",
    ]
    if config.trust_note:
        lines.extend([f"> **可信度**：{config.trust_note}", ""])

    lines.extend(["## 指标", ""])
    for key in (
        "must_cite_recall",
        "evidence_recall",
        "group_recall",
        "all_evidence_recall",
        "chapter_recall",
        "evidence_mapped",
        "leak",
    ):
        if key in summary:
            lines.append(f"- `{key}`：{_fmt(summary[key])}")
    lines.extend(
        ["", f"（`must_cite_recall` 分母 = {summary.get('must_cite_recall_denominator')}）", ""]
    )

    for dimension in ("per_difficulty", "per_type", "per_level"):
        breakdown = summary.get(dimension)
        if not breakdown:
            continue
        lines.extend([f"## 按{_DIMENSION_LABEL[dimension]}分列", ""])
        lines.append("| 分组 | 题数 | must_cite_recall | evidence_recall | leak |")
        lines.append("| --- | --- | --- | --- | --- |")
        for key, values in breakdown.items():
            lines.append(
                f"| `{key}` | {values['questions']} | {_fmt(values['must_cite_recall'])} "
                f"| {_fmt(values['evidence_recall'])} | {values['leak']} |"
            )
        lines.append("")
    return "\n".join(lines)


_DIMENSION_LABEL = {
    "per_difficulty": "难度",
    "per_type": "题型",
    "per_level": "realm 等级",
}


def _render_failures_markdown(failures: Sequence[Mapping[str, Any]]) -> str:
    """失败清单：只写指针、阶段与指标快照，**不写答案也不写检索到的正文**。

    规范给的字段集是 `question_id + 失败阶段 + request_id + chunk_key + 指标快照`——
    全是标识符与数字。想展示「为什么失败」的冲动最容易在这里把答案粘进来，
    而它的长度检查只按行，折行即可绕过，所以由这里从源头限制写什么。
    """
    lines = ["# 失败样本", ""]
    if not failures:
        lines.append("（无）")
        return "\n".join(lines) + "\n"
    lines.append("| 题目 | 失败阶段 | chunk_key | 指标快照 |")
    lines.append("| --- | --- | --- | --- |")
    for item in failures:
        lines.append(
            f"| `{item.get('question_id', '')}` | {item.get('stage', '')} "
            f"| `{item.get('chunk_key', '')}` | {item.get('metrics', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: Sequence[Any]) -> None:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
