"""评测指标口径单测（M0-04 §5.1）。

这些函数是纯计算，不连库、不调模型——指标口径一旦滑掉，整条评测线的数字都不可比，
所以每条口径都单独钉住，而不是只测一个「端到端跑通」。

重点钉住的两条：

- `must_cite_hit`（组内 OR）与 `all_evidence_hit`（组内 AND）**是两回事**。
  前者曾被误写成后者的同义反复，那样「组内只中一条」的比例就永远看不见。
- `evidence_recall` 的分母含**未映射**的 evidence。分母随映射塌缩会让指标虚高。
"""

from __future__ import annotations

from omniread.domain.text import evidence_hash
from omniread.pipelines.assembly import AssembledChunk, DroppedChunk
from omniread.pipelines.evaluation.metrics import (
    aggregate,
    chapter_index_of,
    matched_keys_from_records,
    score_question,
)
from omniread.pipelines.mapping.artifacts import MappingRecord
from omniread.pipelines.retrieval.query import RealmBounds
from omniread.pipelines.retrieval.types import RetrievalOutcome, StageHit

REALM = RealmBounds(lo=1, hi=193)


def _question(
    *,
    question_id: str = "fact-001",
    groups: list[list[tuple[str, str]]] | None = None,
    level: str = "past",
    progress: int | None = 10,
    difficulty: str = "easy",
    expect_refusal: bool = False,
) -> dict:
    groups = groups or [[("book:1:chapter:2", "证据甲")]]
    return {
        "id": question_id,
        "type": "fact",
        "difficulty": difficulty,
        "level": level,
        "progress": progress,
        "expect_refusal": expect_refusal,
        "must_cite_groups": [
            [{"chapter_id": chapter_id, "content": content} for chapter_id, content in group]
            for group in groups
        ],
    }


def _hit(chunk_key: str, chapter_index: int, rank: int = 1) -> StageHit:
    return StageHit(chunk_key=chunk_key, chapter_index=chapter_index, score=1.0, rank=rank)


def _assembled(chunk_key: str, chapter_index: int, chunk_index: int = 0) -> AssembledChunk:
    return AssembledChunk(
        chunk_key=chunk_key,
        chapter_index=chapter_index,
        chunk_index=chunk_index,
        source="hit",
        from_hit_chunk_key=chunk_key,
        token_count=100,
        rank=1,
    )


def _outcome(
    *,
    query: str = "问",
    dense: list[StageHit] | None = None,
    kw: list[StageHit] | None = None,
    fused: list[StageHit] | None = None,
    reranked: list[StageHit] | None = None,
    assembled: list[AssembledChunk] | None = None,
    dropped: list[DroppedChunk] | None = None,
) -> RetrievalOutcome:
    return RetrievalOutcome(
        query=query,
        realm=REALM,
        dense=tuple(dense or []),
        kw=tuple(kw or []),
        fused=tuple(fused or []),
        reranked=tuple(reranked or []),
        assembled=tuple(assembled or []),
        dropped=tuple(dropped or []),
        token_estimate=0,
    )


def _mapping(chapter_id: str, content: str, chunk_key: str | None) -> dict[str, str | None]:
    return {evidence_hash(chapter_id, content): chunk_key}


class TestMustCite:
    def test_all_groups_hit(self) -> None:
        question = _question(
            groups=[[("book:1:chapter:2", "甲")], [("book:1:chapter:3", "乙")]]
        )
        lookup = {
            **_mapping("book:1:chapter:2", "甲", "book:1:chapter:2#c0"),
            **_mapping("book:1:chapter:3", "乙", "book:1:chapter:3#c1"),
        }
        outcome = _outcome(
            assembled=[_assembled("book:1:chapter:2#c0", 2), _assembled("book:1:chapter:3#c1", 3)]
        )
        record = score_question(question, outcome, lookup)
        assert record.must_cite_hit is True
        assert record.groups_hit == 2 and record.groups_total == 2
        assert record.all_evidence_hit is True

    def test_group_is_or_within_and_within(self) -> None:
        """组内 OR：一条命中即整组命中；组间 AND：另一组没中就不算整题命中。"""
        question = _question(
            groups=[
                [("book:1:chapter:2", "甲"), ("book:1:chapter:2", "乙")],
                [("book:1:chapter:5", "丙")],
            ]
        )
        lookup = {
            **_mapping("book:1:chapter:2", "甲", "book:1:chapter:2#c0"),
            **_mapping("book:1:chapter:2", "乙", "book:1:chapter:2#c9"),
            **_mapping("book:1:chapter:5", "丙", "book:1:chapter:5#c0"),
        }
        # 只召回「甲」，乙（同组）与丙（另一组）都没进装配
        outcome = _outcome(assembled=[_assembled("book:1:chapter:2#c0", 2)])
        record = score_question(question, outcome, lookup)
        assert record.groups_hit == 1 and record.groups_total == 2
        assert record.must_cite_hit is False
        assert record.evidence_hit == 1 and record.evidence_total == 3

    def test_all_evidence_hit_is_stricter_than_must_cite(self) -> None:
        """组内只中一条时，must_cite_hit 为真而 all_evidence_hit 必须为假。

        这两个指标曾因 `group_all` 算而不用而退化成一个——那样「靠一条撑住整组」
        的比例就永远看不见。这条断言就是那次的回归防线。
        """
        question = _question(
            groups=[[("book:1:chapter:2", "甲"), ("book:1:chapter:2", "乙")]]
        )
        lookup = {
            **_mapping("book:1:chapter:2", "甲", "book:1:chapter:2#c0"),
            **_mapping("book:1:chapter:2", "乙", "book:1:chapter:2#c9"),
        }
        outcome = _outcome(assembled=[_assembled("book:1:chapter:2#c0", 2)])
        record = score_question(question, outcome, lookup)
        assert record.must_cite_hit is True
        assert record.all_evidence_hit is False

    def test_unmapped_evidence_stays_in_denominator(self) -> None:
        """未映射的 evidence 仍进分母，否则分母随映射结果塌缩、指标虚高。"""
        question = _question(
            groups=[[("book:1:chapter:2", "甲"), ("book:1:chapter:2", "乙")]]
        )
        lookup = _mapping("book:1:chapter:2", "甲", "book:1:chapter:2#c0")
        outcome = _outcome(assembled=[_assembled("book:1:chapter:2#c0", 2)])
        record = score_question(question, outcome, lookup)
        assert record.evidence_total == 2
        assert record.evidence_mapped == 1
        assert record.evidence_hit == 1


class TestLeak:
    def test_counts_across_every_stage_not_just_assembled(self) -> None:
        """逐阶段都算：召回了越界内容但被装配丢掉，仍是检索链的泄漏。"""
        question = _question(progress=10)
        outcome = _outcome(
            dense=[_hit("book:1:chapter:2#c0", 2), _hit("book:1:chapter:99#c0", 99)],
            kw=[_hit("book:1:chapter:99#c1", 99)],
            assembled=[_assembled("book:1:chapter:2#c0", 2)],
        )
        record = score_question(question, outcome, {})
        assert record.leak_dense == 1
        assert record.leak_kw == 1
        assert record.leak_assembled == 0
        assert record.leak_total == 2

    def test_full_level_has_no_leak_by_definition(self) -> None:
        question = _question(level="full", progress=None)
        outcome = _outcome(dense=[_hit("book:1:chapter:99#c0", 99)])
        record = score_question(question, outcome, {})
        assert record.leak_total == 0
        assert record.progress is None


class TestAggregate:
    def _record(self, **overrides: object):
        question = _question()
        outcome = _outcome(assembled=[_assembled("book:1:chapter:2#c0", 2)])
        lookup = _mapping("book:1:chapter:2", "证据甲", "book:1:chapter:2#c0")
        record = score_question(question, outcome, lookup)
        return record if not overrides else _replace(record, **overrides)

    def test_refusal_questions_are_excluded_from_must_cite_denominator(self) -> None:
        hit = self._record()
        refusal = self._record(expect_refusal=True, question_id="spoiler-001")
        summary = aggregate([hit, refusal])
        assert summary["question_count"] == 2
        assert summary["must_cite_recall_denominator"] == 1
        assert summary["must_cite_recall"] == 1.0

    def test_empty_denominator_is_zero_not_a_crash(self) -> None:
        summary = aggregate([self._record(expect_refusal=True)])
        assert summary["must_cite_recall"] == 0.0
        assert summary["must_cite_recall_denominator"] == 0

    def test_per_difficulty_is_a_slice_not_a_weight(self) -> None:
        """按难度分列：各档独立算比率，不合成一个加权总分。"""
        easy = self._record(difficulty="easy")
        hard = self._record(difficulty="hard", groups_hit=0, must_cite_hit=False)
        breakdown = aggregate([easy, hard])["per_difficulty"]
        assert isinstance(breakdown, dict)
        assert breakdown["easy"]["must_cite_recall"] == 1.0
        assert breakdown["hard"]["must_cite_recall"] == 0.0
        # 总口径是简单计数，不是两档的加权平均
        assert breakdown["easy"]["questions"] == 1


class TestHelpers:
    def test_chapter_index_of_rejects_bad_ids(self) -> None:
        assert chapter_index_of("book:1:chapter:17") == 17
        try:
            chapter_index_of("book:1:chapter:缺")
        except ValueError:
            return
        raise AssertionError("非数字 chapter_id 应抛错，而不是静默当 0")

    def test_low_conf_mapping_does_not_count_as_hit(self) -> None:
        record = MappingRecord(
            question_id="fact-001",
            evidence_hash="a" * 64,
            chapter_id="book:1:chapter:2",
            match_status="low_conf",
            matched_chunk_key="book:1:chapter:2#c0",
            alternative_chunk_key=None,
            confidence=0.0,
            decision_tier="partial_overlap",
            mapper_model="m",
            mapper_prompt_version="p",
            overlap_reason="仅部分覆盖",
        )
        lookup = matched_keys_from_records([record])
        assert lookup["a" * 64] is None


def _replace(record, **overrides):
    from dataclasses import replace

    return replace(record, **overrides)
