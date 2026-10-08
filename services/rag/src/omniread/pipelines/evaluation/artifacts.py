"""评测 run 产物落盘（M0-02 §7.1）；`eval/` 进 git，按红线约束写法。

与映射侧同一套规矩（`domain.artifacts`）：**字段白名单 + 长度上限**，两半都要。
逐题记录是 frozen dataclass，`asdict` 出来的字段集就是允许进 git 的全部内容；
写入前再递归查一遍字符串长度兜底。

本模块只产检索层 run：逐题记录 `RetrievalScoreRecord` + 汇总 + 失败清单。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from omniread.domain.artifacts import guard_payload
from omniread.pipelines.evaluation.types import (
    GenerationScoreRecord,
    RetrievalScoreRecord,
)

#: 本 run 没有经过这一层。写明确的值而不是空串：空串在产物里看起来像「漏填」，
#: 而它是确定结论——这一层没跑。
NOT_EXERCISED = "not-exercised"

#: 检索层之外的字段在本 run 里一律 `NOT_EXERCISED`；`rag_runs` 有对应的列
#: （`M0-02` §3.5），列留着、值写「没跑」，不要为了少一列去改库表。
PHASE_RETRIEVAL = "retrieval"


@dataclass(frozen=True, slots=True)
class EvalRunConfig:
    """本次评测 run 的参数快照，供 baseline diff。

    只列白名单字段。**不要**改成 `Mapping[str, Any]`、也不要塞 `Settings.model_dump()`：
    `minio_access_key` 是普通 str，整体 dump 会把凭据写进仓库。

    `answer_*` / `judge_*` / `prompt_version` 是 `rag_runs` 的列（`M0-02` §3.5），
    本层不产它们，一律留 `NOT_EXERCISED`。`rag_runs` 那一行直接由这份 config 派生
    （`build_run_row`）——「同一次跑用了什么」只有一个来源。
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
    # ── 生成层与 judge（`M0-02` §3.5 的对应列）：检索层 run 一律 NOT_EXERCISED ──
    answer_provider: str = NOT_EXERCISED
    answer_model: str = NOT_EXERCISED
    judge_provider: str = NOT_EXERCISED
    judge_model: str = NOT_EXERCISED
    #: 答案 prompt 的内容 sha256 短串，随模板语义变更而变。改它即新基线。
    prompt_version: str = NOT_EXERCISED
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
    generation_records: Sequence[GenerationScoreRecord] = (),
    summary: Mapping[str, Any] | None = None,
    failures: Sequence[Mapping[str, Any]] = (),
) -> None:
    """写一个评测 run 的产物目录；已存在则整体重写（同一 run_id 重跑即覆盖）。

    只写传进来的那几类文件——空文件会让人以为「跑了但全是 0」。缺哪类就是没跑哪类。
    两层可以只跑一层：`retrieval_records` 与 `generation_records` 各自独立落盘。
    """
    run_dir.mkdir(parents=True, exist_ok=True)

    config_payload = asdict(config)
    guard_payload("config.json", config_payload)

    if summary is not None:
        summary_payload = dict(summary)
        guard_payload("summary.json", summary_payload)
        _write_json(run_dir / "summary.json", summary_payload)
    _write_json(run_dir / "config.json", config_payload)

    for name, records in (
        ("retrieval.scores.jsonl", retrieval_records),
        ("generation.scores.jsonl", generation_records),
    ):
        if not records:
            continue
        rows = [asdict(record) for record in records]
        for row in rows:
            guard_payload(name, row)
        _write_jsonl(run_dir / name, rows)

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
    ]
    if config.answer_provider != NOT_EXERCISED:
        lines.append(
            f"- 回答：{config.answer_provider} / `{config.answer_model}`"
            f"（prompt `{config.prompt_version}`）"
        )
    lines.extend([f"- 题目数：{summary.get('question_count', 0)}", ""])
    if config.trust_note:
        lines.extend([f"> **可信度**：{config.trust_note}", ""])

    if "evidence_total" in summary:
        lines.extend(_render_retrieval_section(summary))
    if isinstance(generation := summary.get("generation"), dict):
        lines.extend(_render_generation_section(generation))
        lines.extend(_render_generation_breakdown(generation))

    for dimension in ("per_difficulty", "per_type", "per_level"):
        breakdown = summary.get(dimension)
        if not breakdown:
            continue
        lines.extend([f"## 按{_DIMENSION_LABEL[dimension]}分列", ""])
        lines.append("| 分组 | 题数 | 证据总数 | evidence_recall | leak |")
        lines.append("| --- | --- | --- | --- | --- |")
        for key, values in breakdown.items():
            # 缺列记 `?` 而不是崩：分母是后补的口径，早于它产出的 summary 没有这一列。
            denominator = values.get("evidence_total")
            lines.append(
                f"| `{key}` | {values['questions']} | {_fmt_denominator(denominator)} "
                f"| {fmt_ratio(values.get('evidence_recall'), denominator)} "
                f"| {values['leak']} |"
            )
        lines.append("")
    return "\n".join(lines)


def _render_retrieval_section(summary: Mapping[str, Any]) -> list[str]:
    """检索层：两个数 + 分母说明。只写计数与比率，不写任何题面或正文。"""
    lines = ["## 指标", ""]
    evidence_denominator = summary.get("evidence_total")
    for key in ("evidence_recall", "evidence_total", "evidence_mapped", "leak"):
        if key not in summary:
            continue
        # 头条与分列必须是同一条渲染规则：同一个量在两处读法不同，本身就是缺陷。
        # 两个比率共用同一个分母（全部 evidence 条数），所以走同一条判据；
        # `evidence_total` / `leak` 是绝对量，没有分母可言。
        value = (
            fmt_ratio(summary[key], evidence_denominator)
            if key in ("evidence_recall", "evidence_mapped")
            else _fmt(summary[key])
        )
        lines.append(f"- `{key}`：{value}")
    lines.extend(
        [
            "",
            f"（`evidence_recall` 分母 = {_fmt_denominator(evidence_denominator)} 条证据。"
            "它是**逐条证据**的召回率，分母是该题全部 evidence（含没映射上的）——"
            "分母随映射结果塌缩会让指标虚高。`evidence_mapped` 单列，"
            "它衡量的是**映射**而不是检索：切片没对上与检索没召回到，修法不同。"
            "`leak` 是硬门禁，任一阶段 >0 即红。**分母为 0 的记 `—`**："
            "那是「没有可判定的证据」，不是「一条都没中」。）",
            "",
        ]
    )
    return lines


def _render_generation_section(summary: Mapping[str, Any]) -> list[str]:
    """答案层：引用越界率 + 拒答正确性。同样只写计数与比率。"""
    denominator = summary.get("citation_in_set_denominator")
    refusal_denominator = summary.get("refusal_denominator")
    lines = [
        "## 答案层",
        "",
        f"- `answered`：{_fmt(summary.get('answered'))} / {_fmt(summary.get('question_count'))}"
        f"（`generation_failed` {_fmt(summary.get('generation_failed'))}）",
        f"- `citation_in_set`：{fmt_ratio(summary.get('citation_in_set'), denominator)}"
        f"（分母 {_fmt_denominator(denominator)} = 真答出来的题）",
        f"- `answered_without_citation`：{_fmt(summary.get('answered_without_citation'))}",
        f"- `citation_out_of_range_total`：{_fmt(summary.get('citation_out_of_range_total'))}"
        f"；`citation_malformed_total`：{_fmt(summary.get('citation_malformed_total'))}",
        f"- `refusal_correct`：{fmt_ratio(summary.get('refusal_correct'), refusal_denominator)}"
        f"（分母 {_fmt_denominator(refusal_denominator)} 道该拒答的题）",
        f"- `refusal_false_positive`：{_fmt(summary.get('refusal_false_positive'))}",
        "",
        "（`citation_in_set` 的分母**不含**拒答与生成失败的题：它们没有引用可判，"
        "算通过会虚高、算失败又不对——所以分母单列，缩水多少一眼可见。"
        "`answered_without_citation` 必须与 `citation_in_set` 并读：集合判定对空集天然安全，"
        "一个从不标注引用的回答会带着 `1.0000` 通过。`refusal_false_positive` 同理，"
        "它挡住「见谁都拒答」这个能拿满 `refusal_correct` 的退化解。）",
        "",
    ]
    return lines


def _render_generation_breakdown(summary: Mapping[str, Any]) -> list[str]:
    """答案层的分列。检索层那套列名（证据总数 / leak）在这里没有对应量。"""
    lines: list[str] = []
    for dimension in ("per_difficulty", "per_type"):
        breakdown = summary.get(dimension)
        if not breakdown:
            continue
        lines.extend([f"## 答案层 · 按{_DIMENSION_LABEL[dimension]}分列", ""])
        lines.append("| 分组 | 题数 | answered | citation_in_set | 生成失败 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for key, values in breakdown.items():
            denominator = values.get("citation_in_set_denominator")
            lines.append(
                f"| `{key}` | {values['questions']} | {values['answered']} "
                f"| {fmt_ratio(values.get('citation_in_set'), denominator)} "
                f"| {values['generation_failed']} |"
            )
        lines.append("")
    return lines


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


def _fmt_denominator(value: Any) -> str:
    """老产物没有这个字段（口径是本轮才补的），缺了记 `?` 而不是假装是 0。

    `?` 与 `—` 必须分开：前者是「产物太旧、算不出来」，后者是「算出来就是 0 道题」。
    """
    return "?" if value is None else str(value)


def fmt_ratio(value: Any, denominator: Any) -> str:
    """分母为 0 时不写 `0.0000`。

    `_ratio` 在空分母上返回 `0.0`（是个防御性默认值，不是测量结果），照直渲染
    会被读成「该档引用全错」。本 Golden 的 `spoiler` 档全是拒答题，正是这个情形。

    判据是 `denominator == 0`，**不是 `not denominator`**：后者会把「分母字段缺失」
    一并吞成 `—`，连真实算出来的比率（比如 `1.0000`）都不显示了——而缺失是「不知道」，
    与「就是 0」是两回事，分母列已用 `?` 区分，比率列不能把它抹平。
    """
    return "—" if denominator == 0 else _fmt(value)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: Sequence[Any]) -> None:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
