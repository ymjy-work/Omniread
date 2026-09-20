"""映射编排：读 Golden → 逐条映射 → 落 run 产物（M0-02 §6.2）。

`dataset_hash` **不在本模块重算**：规范序列化（`sort_keys=True`、`separators=(",", ":")`）
只存在于 `scripts/validate_golden.py`，另写一份必然在某个细节上分叉，而分叉的后果是
「冻结的 hash」与「实际的数据集」对不上却无人察觉。这里改为调校验器取它的输出，
顺带把 Ready Gate 第 1 条（schema 零报错）与映射放在同一次运行里。

失败不静默：`unmatched` / `low_conf` 一并写进 `mapping_failures.jsonl`，
分母不随映射结果塌缩（M0-02 §6.2 第 5 步）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from omniread.domain.text import evidence_hash
from omniread.pipelines.mapping.artifacts import MappingRecord, RunConfig
from omniread.pipelines.mapping.deterministic import (
    TIER_MAX_COVERAGE,
    map_evidence_deterministic,
)
from omniread.pipelines.mapping.sources import ChapterSlices
from omniread.pipelines.mapping.types import (
    DETERMINISTIC_MAPPER_MODEL,
    MATCH_MATCHED,
    MappingOutcome,
)

_REPO_ROOT = Path(__file__).resolve().parents[6]
DEFAULT_CORPUS_ROOT = _REPO_ROOT / "asset" / "《不时轻声地以俄语遮羞的邻座艾莉同学》"
DEFAULT_GOLDEN_DIR = _REPO_ROOT / "eval" / "golden"
DEFAULT_RUNS_DIR = _REPO_ROOT / "eval" / "runs"
VALIDATOR = _REPO_ROOT / "scripts" / "validate_golden.py"

_QUESTION_FILE_RE = re.compile(r"^(?P<type>[a-z]+)-\d{3}\.json$")
_HASH_LINE_RE = re.compile(r"^dataset_hash:\s*(?P<hash>[0-9a-f]{64})\s*$", re.MULTILINE)
# 非题目文件：schema / 示例不参与数据集（与校验器同一口径）。
_NON_QUESTION_FILES = frozenset({"schema.json", "example.json"})


class GoldenError(ValueError):
    """Golden 目录不可用：缺文件、缺字段或校验器未通过。"""


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """一条待映射的证据；`ordinal` 是该题内 `must_cite_groups` 展平后的序号。"""

    question_id: str
    question_type: str
    # 带上难度只为**分列统计**：评测结果要能按 easy / medium / hard 分开看。
    # 它**不参与任何加权**——难度是评测者的主观标签，加权会把它乘进被测系统的分数。
    difficulty: str
    ordinal: int
    chapter_id: str
    content: str


@dataclass(frozen=True, slots=True)
class MappingRunResult:
    config: RunConfig
    records: tuple[MappingRecord, ...]
    summary: dict[str, object]


def load_golden_evidence(golden_dir: Path = DEFAULT_GOLDEN_DIR) -> list[EvidenceRef]:
    """按题目 id 升序展平 `must_cite_groups`，顺序即分组顺序（组内保序）。"""
    if not golden_dir.is_dir():
        raise GoldenError(f"Golden 目录不存在：{golden_dir}")

    entries: list[tuple[str, EvidenceRef]] = []
    for path in sorted(golden_dir.glob("*.json")):
        if path.name in _NON_QUESTION_FILES or not _QUESTION_FILE_RE.match(path.name):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        question_id = payload["id"]
        question_type = payload["type"]
        difficulty = payload["difficulty"]
        ordinal = 0
        for group in payload["must_cite_groups"]:
            for evidence in group:
                entries.append(
                    (
                        question_id,
                        EvidenceRef(
                            question_id=question_id,
                            question_type=question_type,
                            difficulty=difficulty,
                            ordinal=ordinal,
                            chapter_id=evidence["chapter_id"],
                            content=evidence["content"],
                        ),
                    )
                )
                ordinal += 1

    entries.sort(key=lambda item: (item[0], item[1].ordinal))
    return [evidence for _, evidence in entries]


def golden_dataset_hash(golden_dir: Path = DEFAULT_GOLDEN_DIR) -> str:
    """调校验器取 `dataset_hash`；校验不通过即抛错，不带着坏数据集往下走。"""
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), str(golden_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        raise GoldenError(
            f"Golden 校验未通过（退出码 {completed.returncode}）：\n"
            f"{completed.stdout}\n{completed.stderr}"
        )
    matched = _HASH_LINE_RE.search(completed.stdout)
    if matched is None:
        raise GoldenError("校验器未输出 dataset_hash，无法冻结版本")
    return matched.group("hash")


def map_all(
    evidence: Sequence[EvidenceRef],
    slices: Mapping[str, ChapterSlices],
    *,
    mapper_prompt_version: str,
) -> list[MappingOutcome]:
    """逐条跑确定性映射。chapter 缺失或区间不可还原即抛错——不跳过、不降级。"""
    outcomes: list[MappingOutcome] = []
    for item in evidence:
        chapter = slices.get(item.chapter_id)
        if chapter is None:
            raise GoldenError(
                f"{item.question_id} 的 evidence 指向不存在的章节 {item.chapter_id}"
            )
        outcomes.append(
            map_evidence_deterministic(
                chapter.text,
                item.content,
                chapter.spans,
                evidence_hash=evidence_hash(item.chapter_id, item.content),
                chapter_id=item.chapter_id,
                mapper_prompt_version=mapper_prompt_version,
                mapper_model=DETERMINISTIC_MAPPER_MODEL,
            )
        )
    return outcomes


def build_records(
    evidence: Sequence[EvidenceRef], outcomes: Sequence[MappingOutcome]
) -> list[MappingRecord]:
    return [
        MappingRecord.from_outcome(item.question_id, outcome)
        for item, outcome in zip(evidence, outcomes, strict=True)
    ]


def summarize(
    run_id: str,
    dataset_hash: str,
    evidence: Sequence[EvidenceRef],
    records: Sequence[MappingRecord],
) -> dict[str, object]:
    status = Counter(record.match_status for record in records)
    tiers = Counter(record.decision_tier for record in records)

    pairs = list(zip(evidence, records, strict=True))
    matched = status.get(MATCH_MATCHED, 0)
    total = len(records)
    return {
        "run_id": run_id,
        "dataset_hash": dataset_hash,
        "evidence_count": total,
        "matched_count": matched,
        # 映射完整度。注意这不是检索侧的 evidence_recall：那个要有检索结果才算得出来，
        # 属 M0-9；两者分母相同、分子不同，混用会让数字看起来比实际好。
        "mapping_coverage": (matched / total) if total else 0.0,
        "match_status": dict(sorted(status.items())),
        "decision_tiers": dict(sorted(tiers.items())),
        "per_type": _breakdown(pairs, lambda item: item.question_type),
        # 按难度分列。**只分列、不加权**：难度是评测者给的主观标签，权重会把它乘进
        # 被测系统的分数，改一个标签就悄悄挪动总分。分列既能看到「难题差在哪」，
        # 又不会让标签动一下就把头条数字带走。
        "per_difficulty": _breakdown(pairs, lambda item: item.difficulty),
        "multi_cover_count": tiers.get(TIER_MAX_COVERAGE, 0),
    }


def _breakdown(
    pairs: Sequence[tuple[EvidenceRef, MappingRecord]],
    key_of: Callable[[EvidenceRef], str],
) -> dict[str, dict[str, int]]:
    """按某个维度把映射状态分列，供「难题是不是更差」这类问题直接看数。"""
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for item, record in pairs:
        grouped[key_of(item)][record.match_status] += 1
    return {key: dict(sorted(counts.items())) for key, counts in sorted(grouped.items())}


def run_mapping(
    *,
    run_id: str,
    slices: Mapping[str, ChapterSlices],
    evidence: Sequence[EvidenceRef],
    dataset_hash: str,
    chunk_source: str,
    chunking_version: str,
    tokenizer_id: str,
    mapper_prompt_version: str,
    golden_question_count: int,
    deterministic_only: bool = True,
    mapper_provider: str = "none",
) -> MappingRunResult:
    outcomes = map_all(evidence, slices, mapper_prompt_version=mapper_prompt_version)
    records = build_records(evidence, outcomes)
    summary = summarize(run_id, dataset_hash, evidence, records)
    config = RunConfig(
        run_id=run_id,
        kind="mapping",
        dataset_hash=dataset_hash,
        dataset_version=chunking_version,
        golden_question_count=golden_question_count,
        evidence_count=len(records),
        chunking_version=chunking_version,
        tokenizer_id=tokenizer_id,
        chunk_source=chunk_source,
        mapper_model=DETERMINISTIC_MAPPER_MODEL,
        mapper_prompt_version=mapper_prompt_version,
        mapper_provider=mapper_provider,
        deterministic_only=deterministic_only,
    )
    return MappingRunResult(
        config=config, records=tuple(records), summary=dict(summary)
    )
