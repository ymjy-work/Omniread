"""未命中 evidence 归因的阶段划分与一致性闸门（M1-1 步骤 1）。

这里钉的是两件事，它们都会静默出错：

1. **阶段划分**：一条 evidence 归属哪一阶段，取决于它的 chunk_key 最后一次出现在
   哪里。判错就指向错的参数——把 rerank 窗口的问题报成装配 cap，改完不涨。
2. **口径闸门**：归因算出的命中数必须等于记录里的 `evidence_hit`。少了这道闸门，
   `metrics.py` 的命中规则一变，归因就会继续按旧理解出一份看着合理的报告。
"""

from __future__ import annotations

from typing import Any

import pytest

from omniread.domain.text import evidence_hash
from omniread.pipelines.evaluation.attribution import (
    STAGE_ASSEMBLED,
    STAGE_CHANNEL_MISSED,
    STAGE_FUSED,
    STAGE_FUSED_TRUNCATED,
    STAGE_RERANK,
    STAGE_UNMAPPED,
    AttributionError,
    attribute_losses,
    classify_evidence,
    stage_sets,
)
from omniread.pipelines.evaluation.types import RetrievalScoreRecord

CHAPTER = "book:1:chapter:1"
OTHER_CHAPTER = "book:1:chapter:2"


def _record(**overrides: Any) -> RetrievalScoreRecord:
    base: dict[str, Any] = {
        "question_id": "fact-001",
        "question_type": "fact",
        "difficulty": "easy",
        "level": "past",
        "progress": 10,
        "expect_refusal": False,
        "evidence_total": 0,
        "evidence_hit": 0,
        "evidence_mapped": 0,
        "leak_dense": 0,
        "leak_kw": 0,
        "leak_fused": 0,
        "leak_rerank": 0,
        "leak_assembled": 0,
        "dense_keys": (),
        "kw_keys": (),
        "fused_keys": (),
        "rerank_keys": (),
        "assembled_keys": (),
        "dropped": (),
        "mapped_not_assembled_keys": (),
    }
    base.update(overrides)
    return RetrievalScoreRecord(**base)


def _question(question_id: str, evidences: list[tuple[str, str]], qtype: str = "fact") -> dict:
    return {
        "id": question_id,
        "type": qtype,
        "question": "q",
        "level": "past",
        "progress": 10,
        "expect_refusal": False,
        "must_cite_groups": [[{"chapter_id": ch, "content": text} for ch, text in evidences]],
    }


def _key(chapter_id: str, text: str) -> str:
    return evidence_hash(chapter_id, text)


class TestClassify:
    """一条 evidence 的阶段，按它最后一次出现在哪一层判定。"""

    def test_each_stage_is_reachable(self) -> None:
        record = _record(
            assembled_keys=("k-assembled",),
            rerank_keys=("k-assembled", "k-rerank"),
            fused_keys=("k-assembled", "k-rerank", "k-fused"),
            dense_keys=("k-assembled", "k-rerank", "k-fused", "k-dense"),
            kw_keys=(),
        )
        sets = stage_sets(record)
        assert classify_evidence("k-assembled", sets) == STAGE_ASSEMBLED
        assert classify_evidence("k-rerank", sets) == STAGE_RERANK
        assert classify_evidence("k-fused", sets) == STAGE_FUSED
        assert classify_evidence("k-dense", sets) == STAGE_FUSED_TRUNCATED
        assert classify_evidence("k-nowhere", sets) == STAGE_CHANNEL_MISSED
        assert classify_evidence(None, sets) == STAGE_UNMAPPED

    def test_kw_is_a_channel_too(self) -> None:
        """KW 通道单独出现时也算「进过通道」，不能只认 dense。"""
        sets = stage_sets(_record(kw_keys=("k-kw",)))
        assert classify_evidence("k-kw", sets) == STAGE_FUSED_TRUNCATED


class TestAggregate:
    def test_counts_are_per_evidence_not_per_key(self) -> None:
        """两条 evidence 落在同一个 chunk_key 上时，条数记 2、唯一 key 记 1。

        这正是 107（条）与 73（唯一 key）分叉的来源——两个数都不能当成另一个用。
        """
        shared = _key(CHAPTER, "同一段原文")
        question = _question("fact-001", [(CHAPTER, "同一段原文"), (CHAPTER, "同一段原文")])
        record = _record(
            evidence_total=2,
            evidence_hit=0,
            evidence_mapped=2,
            rerank_keys=(shared,),
            mapped_not_assembled_keys=(shared,),
        )
        attribution = attribute_losses([question], {shared: shared}, [record])
        assert attribution.by_stage[STAGE_RERANK] == 2
        assert attribution.unique_keys_missed == 1

    def test_reuse_across_questions_counts_once_per_question(self) -> None:
        """同一段原文被两道题复用：每题各记一条。"""
        shared = _key(CHAPTER, "复用段")
        questions = [
            _question("fact-001", [(CHAPTER, "复用段")]),
            _question("fact-002", [(CHAPTER, "复用段")]),
        ]
        records = [
            _record(
                question_id="fact-001",
                evidence_total=1,
                evidence_mapped=1,
                rerank_keys=(shared,),
            ),
            _record(
                question_id="fact-002",
                evidence_total=1,
                evidence_mapped=1,
                rerank_keys=(shared,),
            ),
        ]
        attribution = attribute_losses(questions, {shared: shared}, records)
        assert attribution.by_stage[STAGE_RERANK] == 2
        assert attribution.unique_keys_missed == 1

    def test_unmapped_evidence_is_counted_separately(self) -> None:
        question = _question("fact-001", [(CHAPTER, "没映射上的")])
        record = _record(evidence_total=1, evidence_hit=0, evidence_mapped=0)
        attribution = attribute_losses([question], {}, [record])
        assert attribution.by_stage[STAGE_UNMAPPED] == 1
        assert attribution.missed == 1

    def test_type_split_is_independent(self) -> None:
        """分题型拆分：每题的 evidence 只落进它自己的题型。"""
        questions = [
            _question("a", [(CHAPTER, "x")], qtype="cross"),
            _question("b", [(CHAPTER, "y")], qtype="fact"),
        ]
        records = [
            _record(
                question_id="a",
                evidence_total=1,
                evidence_mapped=1,
                rerank_keys=("kx",),
            ),
            _record(
                question_id="b",
                evidence_total=1,
                evidence_mapped=1,
                assembled_keys=("ky",),
                evidence_hit=1,
            ),
        ]
        attribution = attribute_losses(
            questions,
            {_key(CHAPTER, "x"): "kx", _key(CHAPTER, "y"): "ky"},
            records,
        )
        assert attribution.by_type_total == {"cross": 1, "fact": 1}
        assert attribution.by_type_stage["cross"][STAGE_RERANK] == 1
        assert attribution.by_type_stage["fact"][STAGE_ASSEMBLED] == 1
        assert attribution.hit == 1
        assert attribution.missed == 1


class TestGate:
    """闸门：归因与逐题记录对不上时必须抛，不能出一份看着合理的报告。"""

    def test_hit_mismatch_raises(self) -> None:
        question = _question("fact-001", [(CHAPTER, "命中的")])
        # 记录说命中 0，但 evidence 的 key 明明在 assembled 里。
        record = _record(evidence_total=1, evidence_hit=0, evidence_mapped=1, assembled_keys=("k",))
        with pytest.raises(AttributionError, match="命中规则分叉"):
            attribute_losses([question], {_key(CHAPTER, "命中的"): "k"}, [record])

    def test_missing_record_raises(self) -> None:
        question = _question("fact-001", [(CHAPTER, "x")])
        with pytest.raises(AttributionError, match="不是同一批"):
            attribute_losses([question], {}, [])

    def test_evidence_total_mismatch_raises(self) -> None:
        """题目里的 evidence 条数与记录声明的不一致——分母不同，比率即无意义。"""
        question = _question("fact-001", [(CHAPTER, "a"), (OTHER_CHAPTER, "b")])
        record = _record(
            evidence_total=1,  # 题目里其实有 2 条
            evidence_hit=0,
            evidence_mapped=1,
            rerank_keys=("ka",),
        )
        with pytest.raises(AttributionError, match="阶段划分漏了分支"):
            attribute_losses([question], {_key(CHAPTER, "a"): "ka"}, [record])
