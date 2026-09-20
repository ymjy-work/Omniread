"""RRF 融合单测：手算核对、空输入、单边为空、重复 chunk 去重、并列决胜。"""

from __future__ import annotations

import pytest

from omniread.pipelines.retrieval import RRF_K, reciprocal_rank_fusion

A = "book:1:chapter:1#c0"
B = "book:1:chapter:1#c1"
C = "book:1:chapter:2#c0"
D = "book:1:chapter:3#c0"


def test_rrf_matches_hand_computed_order_and_scores() -> None:
    """dense=[A,B,C] / kw=[B,D,A]，k=60 手算：

    A = 1/61 + 1/63，B = 1/62 + 1/61，D = 1/62，C = 1/63 → B > A > D > C。
    """
    fused = reciprocal_rank_fusion({"dense": [A, B, C], "kw": [B, D, A]})

    assert [hit.chunk_key for hit in fused] == [B, A, D, C]
    assert [hit.rank for hit in fused] == [1, 2, 3, 4]
    expected = {
        B: 1 / 62 + 1 / 61,
        A: 1 / 61 + 1 / 63,
        D: 1 / 62,
        C: 1 / 63,
    }
    for hit in fused:
        assert hit.score == pytest.approx(expected[hit.chunk_key])
    assert fused[0].sources == ("dense", "kw")
    assert fused[2].sources == ("kw",)
    assert fused[3].sources == ("dense",)


def test_rrf_constant_is_frozen_baseline() -> None:
    assert RRF_K == 60


def test_rrf_dedupes_across_and_within_rankings() -> None:
    """同一 chunk 在融合里只出现一次：跨路累加分数，同路重复只按首次出现计分。

    名次是列表下标 + 1，所以 dense 里第 3 位的 B 仍是 1/63——重复项不压缩后续项名次。
    """
    fused = reciprocal_rank_fusion({"dense": [A, A, B], "kw": [A]})

    assert [hit.chunk_key for hit in fused] == [A, B]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 61)
    assert fused[0].sources == ("dense", "kw")
    assert fused[1].score == pytest.approx(1 / 63)


def test_rrf_empty_inputs() -> None:
    assert reciprocal_rank_fusion({}) == []
    assert reciprocal_rank_fusion({"dense": [], "kw": []}) == []


def test_rrf_single_sided_ranking() -> None:
    """单边为空时退化为该路排名，分数仍是 1/(k+rank)。"""
    fused = reciprocal_rank_fusion({"dense": [A, B], "kw": []})

    assert [hit.chunk_key for hit in fused] == [A, B]
    assert fused[0].score == pytest.approx(1 / 61)
    assert fused[1].score == pytest.approx(1 / 62)
    assert fused[0].sources == ("dense",)


def test_rrf_tie_break_is_deterministic() -> None:
    """同分时按「最好排名 → 首次出现次序」决胜，次序不随字典遍历抖动。"""
    fused = reciprocal_rank_fusion({"dense": [A], "kw": [B]})

    assert [hit.chunk_key for hit in fused] == [A, B]
    assert fused[0].score == pytest.approx(fused[1].score)


def test_rrf_rejects_non_positive_k() -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion({"dense": [A]}, k=0)
