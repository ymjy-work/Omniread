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
from omniread.pipelines.evaluation.generation import MEMBERSHIP_KEY
from omniread.pipelines.evaluation.types import (
    GenerationScoreRecord,
    RetrievalScoreRecord,
)

#: 本 run 没有经过这一层。写明确的值而不是空串：空串在库里看起来像「漏填」，
#: 而它是确定结论——这一层没跑（检索层 run 的 `answer_*` / `judge_*` 就是这种）。
NOT_EXERCISED = "not-exercised"

#: 逐题取值不一致（同一个 run 里混了多版 prompt 或多个回答模型）。
#: **它不等于 `NOT_EXERCISED`**：后者是「这一层没跑」，而这里是「跑了，但用的不是一个值」。
#: 用 `NOT_EXERCISED` 兼表两义会让 config.json 在生成层明明跑过的情况下宣称它没跑。
MIXED_ACROSS_QUESTIONS = "mixed-across-questions"

#: 两层分开测是 `M0-04` §1 的硬要求：混测会让失败无法归因。
PHASE_RETRIEVAL = "retrieval"
PHASE_GENERATION = "generation"


@dataclass(frozen=True, slots=True)
class EvalRunConfig:
    """本次评测 run 的参数快照，供 baseline diff。

    只列白名单字段。**不要**改成 `Mapping[str, Any]`、也不要塞 `Settings.model_dump()`：
    `minio_access_key` 是普通 str，整体 dump 会把凭据写进仓库。

    生成层与 judge 的字段**同一份 config 承载两层**：检索层 run 留 `NOT_EXERCISED`，
    生成层 run 填真值。`rag_runs` 那一行直接由这份 config 派生（`build_run_row`），
    不再另传一遍参数——「同一次跑用了什么」只有一个来源。
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

    只写传进来的那几类文件——检索层 run 不产 `generation.scores.jsonl`，
    空文件会让人以为「跑了但全是 0」。缺哪类就是没跑哪类。

    两类逐题记录的写入方式**必须一致**：都过 `guard_payload`（它检查的是字段里的
    字符串长度），而真正的防线是 dataclass 的字段集本身——生成层尤其如此，因为
    「与语料逐字重合」那条扫描对模型写的文本天然失效。
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

    if generation_records:
        gen_rows = [asdict(record) for record in generation_records]
        for row in gen_rows:
            guard_payload("generation.scores.jsonl", row)
        _write_jsonl(run_dir / "generation.scores.jsonl", gen_rows)

    # 失败清单只落 `failures.md`（M0-02 §7.1 的目录布局里没有 failures.jsonl）。
    # 逐条内容仍是「指针 + 阶段 + 指标快照」，渲染时由 `_render_failures_markdown` 限制。
    for item in failures:
        guard_payload("failures.md", dict(item))

    if summary is not None:
        renderer = (
            _render_generation_summary_markdown
            if config.phase == PHASE_GENERATION
            else _render_summary_markdown
        )
        (run_dir / "summary.md").write_text(
            renderer(config, summary), encoding="utf-8", newline="\n"
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
    must_cite_denominator = summary.get("must_cite_recall_denominator")
    for key in (
        "must_cite_recall",
        "evidence_recall",
        "group_recall",
        "all_evidence_recall",
        "chapter_recall",
        "evidence_mapped",
        "leak",
    ):
        if key not in summary:
            continue
        # 头条与分列必须是同一条渲染规则：同一个量在两处读法不同，本身就是缺陷。
        value = (
            fmt_ratio(summary[key], must_cite_denominator)
            if key == "must_cite_recall"
            else _fmt(summary[key])
        )
        lines.append(f"- `{key}`：{value}")
    lines.extend(
        [
            "",
            f"（`must_cite_recall` 分母 = {_fmt_denominator(must_cite_denominator)}。"
            "拒答题不进这个分母——它衡量的是「答案该引的都引了」，而拒答题本就不该引用；"
            "拒答题的检索质量由 `evidence_recall` 与失败清单承载，"
            "**没能召回到判定所需的证据仍算失败**。分列表同口径，"
            "**分母为 0 的记 `—`**：那是「没有可判定的题」，不是「一道都没中」。）",
            "",
        ]
    )

    for dimension in ("per_difficulty", "per_type", "per_level"):
        breakdown = summary.get(dimension)
        if not breakdown:
            continue
        lines.extend([f"## 按{_DIMENSION_LABEL[dimension]}分列", ""])
        lines.append("| 分组 | 题数 | must_cite 分母 | must_cite_recall | evidence_recall | leak |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for key, values in breakdown.items():
            denominator = values.get("must_cite_recall_denominator")
            lines.append(
                f"| `{key}` | {values['questions']} | {_fmt_denominator(denominator)} "
                f"| {fmt_ratio(values['must_cite_recall'], denominator)} "
                f"| {_fmt(values['evidence_recall'])} | {values['leak']} |"
            )
        lines.append("")
    return "\n".join(lines)


_JUDGE_METRICS = (
    "point_coverage",
    "faithfulness",
    "answer_relevancy",
    "answer_boundary_violation",
    "citation_supported",
)


def _render_generation_summary_markdown(
    config: EvalRunConfig, summary: Mapping[str, Any]
) -> str:
    """生成层汇总。与检索层同一个规矩：只写计数与比率，不写任何题面或正文。

    与检索层的两处实质差别：

    - **门禁口径不同**。检索层头条是 `must_cite_recall`（分母排除拒答题）；生成层
      头条是 `answer_citation_membership`，**分母是全部题**，拒答题只免第二个条件。
    - **judge 指标未执行时写「未执行」**，不写 `0.0000`。judge 在 Cohen's kappa ≥ 0.6
      校准完成前只报告（`M0-04` §6），把它们渲染成 0 分会让人以为「跑了但全错」。
    """
    lines = [
        f"# 评测 run {config.run_id}",
        "",
        f"- 阶段：{config.phase}；kind：{config.kind}",
        f"- dataset_hash：`{config.dataset_hash}`（schema {config.dataset_version}）",
        f"- corpus_manifest_hash：`{config.corpus_manifest_hash}`",
        f"- 切片：`{config.chunking_version}`；chunk 来源：{config.chunk_source}",
        f"- 回答：{config.answer_provider} / `{config.answer_model}`"
        f"（prompt `{config.prompt_version}`）",
        f"- judge：{config.judge_provider} / `{config.judge_model}`",
        f"- 题目数：{summary.get('question_count', 0)}",
        "",
    ]
    if config.trust_note:
        lines.extend([f"> **可信度**：{config.trust_note}", ""])

    denominator = summary.get("citation_membership_denominator")
    lines.extend(
        [
            "## 门禁：引用成员性",
            "",
            f"- `{MEMBERSHIP_KEY}`：{_fmt_metric(summary.get(MEMBERSHIP_KEY), denominator)}"
            f"（分母 = {_fmt_denominator(denominator)}）",
            f"- `generation_failed`：{summary.get('generation_failed', 0)}",
            "",
            "（两个条件都要满足：① 引用**全部**在本次允许集合内；② **非拒答题至少 1 条引用**。"
            "拒答题免 ②、不免 ①。失败的题**留在分母里**——分母随结果塌缩会让指标偏高。"
            "`generation_failed` > 0 说明这次 run 带故障，应重跑而不是当作结论。）",
            "",
            "## 引用计数",
            "",
            f"- 越界引用合计：{summary.get('citation_out_of_range_total', 0)}",
            f"- 非规范写法合计：{summary.get('citation_malformed_total', 0)}",
            f"- 正常作答（`answered`）：{summary.get('answered', 0)}",
            "",
            "（越界引用只记标记本身（`[C45]`）且由章号重拼；非规范写法只记条数——"
            "那类片段可能裹着正文，原文在 `temp/run.gen.jsonl`。）",
            "",
            "## judge 指标（未校准，只报告）",
            "",
        ]
    )
    for key in _JUDGE_METRICS:
        value = summary.get(key)
        rendered = "未执行" if value is None else _fmt(value)
        lines.append(f"- `{key}`：{rendered}")
    lines.extend(
        [
            "",
            "（Cohen's kappa ≥ 0.6 校准完成前，这些数字**不可作为结论**、也不作构建门禁"
            "（`M0-04` §6/§7）。）",
            "",
        ]
    )

    for dimension in ("per_difficulty", "per_type"):
        breakdown = summary.get(dimension)
        if not breakdown:
            continue
        lines.extend([f"## 按{_DIMENSION_LABEL[dimension]}分列", ""])
        lines.append("| 分组 | 题数 | membership 分母 | 引用成员性 | 生成失败 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for key, values in breakdown.items():
            group_denominator = values.get("citation_membership_denominator")
            lines.append(
                f"| `{key}` | {values['questions']} | {_fmt_denominator(group_denominator)} "
                f"| {_fmt_metric(values.get(MEMBERSHIP_KEY), group_denominator)} "
                f"| {values.get('generation_failed', 0)} |"
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


def _fmt_metric(value: Any, denominator: Any) -> str:
    """缺值记 `?`（产物里没有这个键，多半是太旧），分母为 0 记 `—`（没有可判定的题）。

    两个占位符必须分开：前者是「不知道」，后者是「算出来就是 0 道题」。
    少了这一层，缺值的指标会被 `_fmt` 渲染成字符串 `None`。
    """
    return "?" if value is None else fmt_ratio(value, denominator)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: Sequence[Any]) -> None:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
