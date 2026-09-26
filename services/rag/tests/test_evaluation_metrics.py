"""评测指标口径单测（M0-04 §5.1）。

这些函数是纯计算，不连库、不调模型——指标口径一旦滑掉，整条评测线的数字都不可比，
所以每条口径都单独钉住，而不是只测一个「端到端跑通」。

重点钉住的三条：

- `evidence_recall` 的**命中判定以 `assembled` 为准**——映射上了但被装配截掉不算命中，
  否则「检索没召回到」与「装配把证据挤出去了」就分不开，而两者的修法完全不同。
- `evidence_recall` 的分母含**未映射**的 evidence。分母随映射塌缩会让指标虚高。
- `evidence_mapped` 与 `evidence_recall` **分开报**：前者衡量映射，后者衡量检索。
"""

from __future__ import annotations

import json
from dataclasses import asdict

from omniread.domain.text import evidence_hash
from omniread.pipelines.assembly import AssembledChunk, DroppedChunk
from omniread.pipelines.evaluation.metrics import (
    aggregate,
    matched_keys_from_records,
    score_question,
)
from omniread.pipelines.evaluation.types import RetrievalScoreRecord
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


class TestEvidenceRecall:
    """逐条证据的召回：命中判定以 `assembled` 为准（M0-04 §5.1）。"""

    def test_every_evidence_recalled(self) -> None:
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
        assert record.evidence_hit == 2 and record.evidence_total == 2

    def test_partial_recall_counts_per_evidence_not_per_group(self) -> None:
        """组内只中一条也算 1/2——逐条口径下「漏了哪几条」才是能指到修法的信息。"""
        question = _question(
            groups=[[("book:1:chapter:2", "甲"), ("book:1:chapter:2", "乙")]]
        )
        lookup = {
            **_mapping("book:1:chapter:2", "甲", "book:1:chapter:2#c0"),
            **_mapping("book:1:chapter:2", "乙", "book:1:chapter:2#c9"),
        }
        outcome = _outcome(assembled=[_assembled("book:1:chapter:2#c0", 2)])
        record = score_question(question, outcome, lookup)
        assert record.evidence_hit == 1 and record.evidence_total == 2

    def test_mapped_but_not_assembled_is_not_a_hit(self) -> None:
        """映射上了、但被装配截掉，不算命中——正是这条把「召回」与「截断」分开。"""
        question = _question(groups=[[("book:1:chapter:2", "甲")]])
        lookup = _mapping("book:1:chapter:2", "甲", "book:1:chapter:2#c9")
        outcome = _outcome(assembled=[_assembled("book:1:chapter:2#c0", 2)])
        record = score_question(question, outcome, lookup)
        assert record.evidence_mapped == 1
        assert record.evidence_hit == 0
        assert record.mapped_not_assembled_keys == ("book:1:chapter:2#c9",)

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

    def test_refusal_questions_stay_in_the_denominator(self) -> None:
        """分母是**全部** evidence，拒答题也进。

        这一条与曾经那个按题聚合、把拒答题排除在外的口径相反：它问「答案该引的都引了」，
        拒答题本就不该引用、所以排除；而 `evidence_recall` 问的是**检索有没有
        把证据捞上来**，与答案该不该引用无关。混用两种分母会让同一个数字
        在两次 run 里度量不同的人群。
        """
        hit = self._record()
        refusal = self._record(expect_refusal=True, question_id="spoiler-001")
        summary = aggregate([hit, refusal])
        assert summary["question_count"] == 2
        assert summary["evidence_total"] == 2
        assert summary["evidence_recall"] == 1.0

    def test_evidence_mapped_is_reported_separately(self) -> None:
        """映射与检索分开报：切片没对上与检索没召回到，修法不同。"""
        miss = self._record(evidence_hit=0, evidence_mapped=0)
        summary = aggregate([miss])
        assert summary["evidence_recall"] == 0.0
        assert summary["evidence_mapped"] == 0.0
        assert summary["evidence_total"] == 1

    def test_empty_denominator_is_zero_not_a_crash(self) -> None:
        summary = aggregate(
            [self._record(evidence_total=0, evidence_hit=0, evidence_mapped=0)]
        )
        assert summary["evidence_recall"] == 0.0
        assert summary["evidence_total"] == 0

    def test_per_difficulty_is_a_slice_not_a_weight(self) -> None:
        """按难度分列：各档独立算比率，不合成一个加权总分。"""
        easy = self._record(difficulty="easy")
        hard = self._record(difficulty="hard", evidence_hit=0)
        breakdown = aggregate([easy, hard])["per_difficulty"]
        assert isinstance(breakdown, dict)
        assert breakdown["easy"]["evidence_recall"] == 1.0
        assert breakdown["hard"]["evidence_recall"] == 0.0
        assert breakdown["easy"]["questions"] == 1

    def test_breakdown_carries_its_own_denominator(self) -> None:
        """分列必须自带分母：不列出来就没法判断两次 run 是否同分母。

        `_ratio` 在空分母上返回 `0.0`（防御性默认，不是测量结果），照直渲染会被
        读成「一条都没中」；可读性由分母列与渲染层的 `—` 负责，不在这一层包装。
        """
        answer = self._record(difficulty="easy")
        refusal = self._record(
            difficulty="hard", expect_refusal=True, question_id="spoiler-001"
        )
        breakdown = aggregate([answer, refusal])["per_difficulty"]
        assert isinstance(breakdown, dict)
        assert breakdown["easy"]["evidence_total"] == 1
        assert breakdown["hard"]["evidence_total"] == 1
        empty = aggregate([self._record(difficulty="hard", evidence_total=0)])[
            "per_difficulty"
        ]
        assert isinstance(empty, dict)
        assert empty["hard"]["evidence_total"] == 0
        assert empty["hard"]["evidence_recall"] == 0.0


class TestHelpers:
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


class TestRecordRoundTrip:
    def test_tuple_fields_survive_a_json_round_trip(self) -> None:
        """逐题记录要能从产物原样还原。

        JSON 没有元组，指针列读回来是 list。还原不准的话，「改口径离线重算」
        就会算出一份与 run 当时不同的产物——而那条路正是为了不重花真实调用
        才存在的，错了还看不出来（数字仍会是一组看着合理的数）。
        """
        original = score_question(
            _question(),
            _outcome(assembled=[_assembled("book:1:chapter:2#c0", 2)]),
            _mapping("book:1:chapter:2", "证据甲", "book:1:chapter:2#c0"),
        )
        payload = json.loads(json.dumps(asdict(original), ensure_ascii=False))
        assert asdict(RetrievalScoreRecord.from_payload(payload)) == asdict(original)


def _replace(record, **overrides):
    from dataclasses import replace

    return replace(record, **overrides)
