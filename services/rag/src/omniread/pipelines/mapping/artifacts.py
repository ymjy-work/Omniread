"""映射 run 产物落盘（M0-02 §7.1），按「eval/ 进 git」的红线约束写法。

`M0-02` §7.1 的白名单只列了 retrieval / generation / failures 三类逐题产物，
映射产物不在其中；这里沿同一条原则补上它的字段集——**只带指针与指标值**：
question_id、evidence_hash、chapter_id、chunk_key、match_status、confidence、判据档位。
evidence 的 content 与 chunk 正文一律不进 `eval/`。

两处易被忽略的正文入口，这里显式堵死：

- `overlap_reason` 是自由文本。确定性路径下它是本模块生成的「位置 + 键名」描述，不含正文；
  兜底路径下它来自模型，**可能回显候选 chunk 原文**——写入前统一截断并压平换行。
- 人工复核产物必须让人看到 evidence 与 chunk 正文，那部分属语料，只落 `temp/`（见 `review.py`），
  与「回答原文只落 temp/」同一条规矩。

`config.json` 只写白名单字段：`Settings` 里 `minio_access_key` 是普通 str，
整体 `model_dump()` 会把凭据写进仓库——所以这里不接受任意字典，只接受 `RunConfig`。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from omniread.pipelines.mapping.types import MATCH_MATCHED, MappingOutcome

# M0-02 §7.1：CI 检查 JSONL 内任一字符串字段长度上限 500 字符，超限即视为夹带了正文。
MAX_STRING_FIELD = 500

# 自由文本列的落盘上限。规格给的 500 是「夹带正文」的判定线，这里再收紧一档：
# 理由是这一列由模型产出，长度越短、越难塞下一段正文。
MAX_REASON_CHARS = 200

# run 目录**只准**出现这些文件。多出来的文件（debug.txt、raw/、请求响应 dump）
# 不受白名单约束，是整章语料入库最现实的路径，所以以「白名单 + 目录校验」而非「黑名单」来管。
ALLOWED_RUN_FILES = frozenset(
    {
        "config.json",
        "summary.json",
        "summary.md",
        "mappings.jsonl",
        "mapping_failures.jsonl",
    }
)


class ArtifactRedlineError(ValueError):
    """产物违反入库红线：字段超长、出现正文、或目录里有白名单外的文件。"""


@dataclass(frozen=True, slots=True)
class RunConfig:
    """本次映射 run 的参数快照。

    只列白名单字段。**不要**改成 `Mapping[str, Any]` 或塞 `Settings.model_dump()`：
    凭据一旦进 `config.json` 就随 git 永久留存。
    """

    run_id: str
    kind: str
    dataset_hash: str
    dataset_version: str
    golden_question_count: int
    evidence_count: int
    chunking_version: str
    tokenizer_id: str
    chunk_source: str
    mapper_model: str
    mapper_prompt_version: str
    mapper_provider: str
    deterministic_only: bool


@dataclass(frozen=True, slots=True)
class MappingRecord:
    """`mappings.jsonl` 的一行；字段集即允许进 git 的全部内容。"""

    question_id: str
    evidence_hash: str
    chapter_id: str
    match_status: str
    matched_chunk_key: str | None
    alternative_chunk_key: str | None
    confidence: float
    decision_tier: str
    mapper_model: str
    mapper_prompt_version: str
    overlap_reason: str

    @classmethod
    def from_outcome(
        cls, question_id: str, outcome: MappingOutcome
    ) -> MappingRecord:
        return cls(
            question_id=question_id,
            evidence_hash=outcome.evidence_hash,
            chapter_id=outcome.chapter_id,
            match_status=outcome.match_status,
            matched_chunk_key=outcome.matched_chunk_key,
            alternative_chunk_key=outcome.alternative_chunk_key,
            confidence=outcome.confidence,
            decision_tier=outcome.decision_tier,
            mapper_model=outcome.mapper_model,
            mapper_prompt_version=outcome.mapper_prompt_version,
            overlap_reason=flatten_reason(outcome.overlap_reason),
        )


def flatten_reason(reason: str) -> str:
    """压平自由文本：换行折成空格、按 `MAX_REASON_CHARS` 截断。

    模型可能把候选 chunk 原文粘进理由里，截断是这里唯一能做的确定性收敛；
    真要禁止正文进入该列，只能靠「不让模型产出自由文本」——那正是默认走确定性路径的理由之一。
    """
    flattened = " ".join(reason.split())
    return flattened[:MAX_REASON_CHARS]


def write_run_dir(
    run_dir: Path,
    *,
    config: RunConfig,
    records: Sequence[MappingRecord],
    summary: Mapping[str, Any],
) -> None:
    """写一个映射 run 的产物目录；已存在则整体重写（同一 run_id 重跑即覆盖）。"""
    run_dir.mkdir(parents=True, exist_ok=True)

    payloads: dict[str, Any] = {
        "config.json": asdict(config),
        "summary.json": dict(summary),
    }
    for name, payload in payloads.items():
        _guard_payload(name, payload)

    records_payload = [asdict(record) for record in records]
    for row in records_payload:
        _guard_payload("mappings.jsonl", row)

    failures = [row for row in records_payload if row["match_status"] != MATCH_MATCHED]
    for row in failures:
        _guard_payload("mapping_failures.jsonl", row)

    _write_json(run_dir / "config.json", payloads["config.json"])
    _write_json(run_dir / "summary.json", payloads["summary.json"])
    _write_jsonl(run_dir / "mappings.jsonl", records_payload)
    _write_jsonl(run_dir / "mapping_failures.jsonl", failures)
    (run_dir / "summary.md").write_text(
        _render_summary_markdown(config, summary, len(records), len(failures)),
        encoding="utf-8",
        newline="\n",
    )


def check_run_dir(run_dir: Path) -> list[str]:
    """校验一个已存在的 run 目录是否合规；返回问题清单（空即通过）。

    供 `scripts/verify-artifacts.py` 在 CI 里对 `eval/runs/` 全量扫描用。
    """
    problems: list[str] = []
    if not run_dir.is_dir():
        return [f"{run_dir} 不是目录"]

    for entry in sorted(run_dir.rglob("*")):
        if entry.is_dir():
            problems.append(f"run 目录内不应有子目录：{entry.name}")
            continue
        if entry.name not in ALLOWED_RUN_FILES:
            problems.append(f"run 目录内出现白名单外的文件：{entry.name}")
            continue
        try:
            if entry.suffix == ".jsonl":
                rows = [
                    json.loads(line)
                    for line in entry.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            elif entry.suffix == ".json":
                rows = [json.loads(entry.read_text(encoding="utf-8"))]
            else:
                problems.extend(_check_markdown(entry))
                continue
        except json.JSONDecodeError as exc:
            problems.append(f"{entry.name} 不是合法 JSON：{exc}")
            continue
        for index, row in enumerate(rows):
            problems.extend(_check_strings(entry.name, index, row))

    return problems


def _check_markdown(path: Path) -> list[str]:
    """Markdown 不受 JSONL 长度检查保护，单独兜一道：按行看是否有超长行。

    summary.md 由本模块生成、只含计数与键名，但它是 run 目录里唯一的非结构化文件，
    一旦有人往模板里塞正文，没有别的检查会拦。
    """
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if len(line) > MAX_STRING_FIELD:
            problems.append(f"{path.name}:{number} 单行超过 {MAX_STRING_FIELD} 字符")
    return problems


def _guard_payload(name: str, payload: Any) -> None:
    problems = _check_strings(name, 0, payload)
    if problems:
        raise ArtifactRedlineError("；".join(problems))


def _check_strings(name: str, index: int, payload: Any, prefix: str = "") -> list[str]:
    problems: list[str] = []
    if isinstance(payload, str):
        if len(payload) > MAX_STRING_FIELD:
            problems.append(
                f"{name}[{index}]{prefix} 字符串长度 {len(payload)} 超上限 {MAX_STRING_FIELD}"
            )
    elif isinstance(payload, Mapping):
        for key, value in payload.items():
            problems.extend(_check_strings(name, index, value, f"{prefix}.{key}"))
    elif isinstance(payload, Iterable) and not isinstance(payload, (bytes, bytearray)):
        for position, value in enumerate(payload):
            problems.extend(_check_strings(name, index, value, f"{prefix}[{position}]"))
    return problems


def _write_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, rows: Sequence[Any]) -> None:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")


def _render_summary_markdown(
    config: RunConfig, summary: Mapping[str, Any], record_count: int, failure_count: int
) -> str:
    lines = [
        f"# 映射 run {config.run_id}",
        "",
        f"- dataset_hash：`{config.dataset_hash}`",
        f"- 题目 {config.golden_question_count} 道，evidence {config.evidence_count} 条",
        f"- chunk 来源：{config.chunk_source}",
        f"- mapper：`{config.mapper_model}` / prompt `{config.mapper_prompt_version}`",
        f"- 产物行数：{record_count}；其中未命中 {failure_count} 条",
        "",
        "## 判据档位",
        "",
    ]
    tiers = summary.get("decision_tiers", {})
    for tier, count in sorted(tiers.items()):
        lines.append(f"- `{tier}`：{count}")
    lines.extend(["", "## 状态分布", ""])
    for status, count in sorted(summary.get("match_status", {}).items()):
        lines.append(f"- `{status}`：{count}")
    lines.append("")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class RunSummary:
    """`summary.json` 的形状；`extra` 里只放计数与键名，不放正文。"""

    run_id: str
    dataset_hash: str
    evidence_count: int
    match_status: dict[str, int] = field(default_factory=dict)
    decision_tiers: dict[str, int] = field(default_factory=dict)
    per_type: dict[str, dict[str, int]] = field(default_factory=dict)
