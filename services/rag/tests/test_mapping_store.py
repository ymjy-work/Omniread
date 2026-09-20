"""`chunk_mappings` 待写行的构造规则（M0-7b）。

这里只测纯函数、不连库：去重规则一旦退回「把 run 产物行原样批量写入」，
真库会整批拒绝（`ON CONFLICT DO UPDATE command cannot affect row a second time`），
而那个错误只有连库跑才看得见——所以它必须在离线测试里就被钉住。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from omniread.domain.text import evidence_hash
from omniread.pipelines.mapping.artifacts import MappingRecord
from omniread.pipelines.mapping.store import build_mapping_rows

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GOLDEN = _REPO_ROOT / "eval" / "golden"
_SKIP = {"schema.json", "example.json"}

CHUNKING_VERSION = "m0-placeholder-v1"
TOKENIZER_ID = "tokenizers:test"


def _record(evidence_hash_value: str, **overrides: object) -> MappingRecord:
    base = MappingRecord(
        question_id="fact-001",
        evidence_hash=evidence_hash_value,
        chapter_id="book:1:chapter:1",
        match_status="matched",
        matched_chunk_key="book:1:chapter:1#c0",
        alternative_chunk_key=None,
        confidence=1.0,
        decision_tier="unique_cover",
        mapper_model="deterministic:substring-interval-v1",
        mapper_prompt_version="no-prompt",
        overlap_reason="精确子串位于章内 [0,10)",
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


class TestDedupe:
    def test_same_evidence_from_two_questions_folds_to_one_row(self) -> None:
        """同一段原文被多道题复用是正常的——映射是 evidence 的属性，不是题的属性。"""
        rows = build_mapping_rows(
            [
                _record("a" * 64, question_id="alias-001"),
                _record("a" * 64, question_id="alias-003"),
            ],
            CHUNKING_VERSION,
            TOKENIZER_ID,
        )
        assert len(rows) == 1
        assert rows[0]["evidence_hash"] == "a" * 64

    def test_distinct_evidence_stay_distinct(self) -> None:
        rows = build_mapping_rows(
            [_record("a" * 64), _record("b" * 64)],
            CHUNKING_VERSION,
            TOKENIZER_ID,
        )
        assert len(rows) == 2

    def test_same_evidence_different_mapper_is_not_folded(self) -> None:
        """主键的每个分量都要参与去重：换模型就是另一行，否则缓存失效语义就没了。"""
        rows = build_mapping_rows(
            [
                _record("a" * 64),
                _record("a" * 64, mapper_model="other:mapper-v1"),
                _record("a" * 64, mapper_prompt_version="deadbeef"),
            ],
            CHUNKING_VERSION,
            TOKENIZER_ID,
        )
        assert len(rows) == 3

    def test_same_evidence_different_chunking_version_is_not_folded(self) -> None:
        first = build_mapping_rows([_record("a" * 64)], "profile-a", TOKENIZER_ID)
        second = build_mapping_rows([_record("a" * 64)], "profile-b", TOKENIZER_ID)
        assert len(first) == 1 and len(second) == 1
        assert first[0]["chunking_version"] != second[0]["chunking_version"]

    def test_empty_input(self) -> None:
        assert build_mapping_rows([], CHUNKING_VERSION, TOKENIZER_ID) == []

    def test_row_carries_every_table_column(self) -> None:
        """列集必须与 `chunk_mappings` 对齐；少一列会在连库时才炸。"""
        (row,) = build_mapping_rows([_record("a" * 64)], CHUNKING_VERSION, TOKENIZER_ID)
        assert set(row) == {
            "evidence_hash",
            "chunking_version",
            "tokenizer_id",
            "mapper_model",
            "mapper_prompt_version",
            "match_status",
            "matched_chunk_key",
            "confidence",
            "overlap_reason",
            "alternative_chunk_key",
        }


class TestAgainstRealGolden:
    """用真实 Golden 钉住重复规模：357 条 evidence 只对应 347 个唯一 hash。

    只读 `eval/golden`（进 git），不需要语料。
    """

    def _records(self) -> list[MappingRecord]:
        records: list[MappingRecord] = []
        for path in sorted(_GOLDEN.glob("*.json")):
            if path.name in _SKIP:
                continue
            question = json.loads(path.read_text(encoding="utf-8"))
            for group in question["must_cite_groups"]:
                for evidence in group:
                    records.append(
                        _record(
                            evidence_hash(evidence["chapter_id"], evidence["content"]),
                            question_id=question["id"],
                            chapter_id=evidence["chapter_id"],
                        )
                    )
        return records

    def test_evidence_reuse_folds_357_records_into_347_rows(self) -> None:
        records = self._records()
        assert len(records) == 357
        rows = build_mapping_rows(records, CHUNKING_VERSION, TOKENIZER_ID)
        assert len(rows) == 347, (
            "重复数变了：要么改过题，要么去重规则坏了。"
            "前者请同步更新本断言的期望值，后者是真 bug。"
        )

    def test_every_row_is_unique_on_the_five_tuple(self) -> None:
        rows = build_mapping_rows(self._records(), CHUNKING_VERSION, TOKENIZER_ID)
        keys = [
            (
                row["evidence_hash"],
                row["chunking_version"],
                row["tokenizer_id"],
                row["mapper_model"],
                row["mapper_prompt_version"],
            )
            for row in rows
        ]
        assert len(keys) == len(set(keys)), "去重后仍有重复主键，批量 INSERT 会被 Postgres 拒绝"
