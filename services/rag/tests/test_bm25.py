"""BM25 单测：全局统计 + realm 过滤候选（不按子集重建索引）、分词、确定性与边界。

假 provider 不参与本文件——BM25 只依赖 `bm25s` 与 `jieba`，全程不联网。
"""

from __future__ import annotations

import math

import pytest

from omniread.pipelines.retrieval.bm25 import Bm25Index, tokenize

# 4 章 8 块：ch1/ch2 含「咒语」，ch3 含「钢琴」，ch4 含「钓鱼」。
CHUNKS: list[tuple[str, int, str]] = [
    ("book:1:chapter:1#c0", 1, "阿尔法在图书馆阅读关于魔法的书籍，书中记载了古老的咒语。"),
    ("book:1:chapter:1#c1", 1, "贝塔在教室里练习剑术，汗水浸湿了衣服。"),
    ("book:1:chapter:2#c0", 2, "伽马研究古老的魔法阵，反复推演咒语的读法。"),
    ("book:1:chapter:2#c1", 2, "德尔塔在厨房里做甜点，烤箱里飘出香味。"),
    ("book:1:chapter:3#c0", 3, "艾普西隆朗读诗歌并弹奏钢琴。"),
    ("book:1:chapter:3#c1", 3, "泽塔在庭院里照料花草。"),
    ("book:1:chapter:4#c0", 4, "伊塔在河边钓鱼。"),
    ("book:1:chapter:4#c1", 4, "西塔整理书架，把书按编号排好。"),
]

KEYS = [chunk_key for chunk_key, _, _ in CHUNKS]
CONTENTS = [content for _, _, content in CHUNKS]
# realm = past(progress=2) 时可见的 chunk。
PAST_KEYS = [key for key, chapter_index, _ in CHUNKS if chapter_index <= 2]


@pytest.fixture(scope="module")
def index() -> Bm25Index:
    return Bm25Index(KEYS, CONTENTS)


def test_realm_narrowing_reuses_global_statistics(index: Bm25Index) -> None:
    """窄域排名同源：候选被 realm 收窄，分数仍由全书统计量算出。

    对照物是「直接对该子集建索引」——它的 IDF 与平均文档长度都不同。
    本实现若走后者，分数会与全量索引的同一 chunk 对不上；断言逐条比分即可证伪。
    """
    full = index.search("咒语", k=10)
    narrow = index.search("咒语", k=10, allowed_keys=PAST_KEYS)

    subset_index = Bm25Index(PAST_KEYS, [CONTENTS[KEYS.index(key)] for key in PAST_KEYS])
    subset_hits = subset_index.search("咒语", k=10)

    # 两种做法的候选集合一致（两章里只有 c0 含「咒语」），差别只在统计量。
    assert {hit.chunk_key for hit in narrow} == {hit.chunk_key for hit in subset_hits}
    assert {hit.chunk_key for hit in narrow} == {hit.chunk_key for hit in full}

    full_scores = {hit.chunk_key: hit.score for hit in full}
    subset_scores = {hit.chunk_key: hit.score for hit in subset_hits}
    assert all(hit.score == pytest.approx(full_scores[hit.chunk_key]) for hit in narrow)
    assert any(
        not math.isclose(full_scores[hit.chunk_key], subset_scores[hit.chunk_key], rel_tol=1e-6)
        for hit in narrow
    )


def test_realm_filter_drops_out_of_realm_candidates(index: Bm25Index) -> None:
    """「钢琴」只在 ch3：past(progress=2) 下无候选，全域下能召回。"""
    assert index.search("钢琴", k=10, allowed_keys=PAST_KEYS) == []
    assert [hit.chunk_key for hit in index.search("钢琴", k=10)] == ["book:1:chapter:3#c0"]


def test_same_chunk_scores_identically_under_any_realm(index: Bm25Index) -> None:
    """同一 chunk 的分数不随候选范围变化——这是「不同进度下排名不可漂移」的前提。"""
    full = {hit.chunk_key: hit.score for hit in index.search("咒语", k=10)}
    lonely = index.search("咒语", k=10, allowed_keys={"book:1:chapter:1#c0"})

    assert len(lonely) == 1
    assert lonely[0].score == pytest.approx(full["book:1:chapter:1#c0"])


def test_zero_score_documents_are_not_candidates(index: Bm25Index) -> None:
    """零分 = 无查询词命中，不进候选，否则会给 RRF 注入与查询无关的名次。"""
    hits = index.search("钓鱼", k=10)

    assert [hit.chunk_key for hit in hits] == ["book:1:chapter:4#c0"]


def test_empty_allowed_keys_differs_from_no_filter(index: Bm25Index) -> None:
    assert index.search("咒语", k=10, allowed_keys=set()) == []
    assert index.search("咒语", k=10, allowed_keys=None) != []


def test_search_limits_to_k(index: Bm25Index) -> None:
    hits = index.search("咒语", k=1)

    assert len(hits) == 1
    assert hits[0].rank == 1


def test_search_is_deterministic(index: Bm25Index) -> None:
    first = index.search("咒语", k=10, allowed_keys=PAST_KEYS)
    second = Bm25Index(KEYS, CONTENTS).search("咒语", k=10, allowed_keys=PAST_KEYS)

    assert first == second


def test_query_without_tokens_returns_nothing(index: Bm25Index) -> None:
    assert index.search("   ", k=10) == []


def test_tokenize_uses_jieba_and_drops_whitespace() -> None:
    tokens = tokenize("阿尔法 在图书馆\n阅读")

    assert "阿尔法" in tokens
    assert "图书馆" in tokens
    assert all(token.strip() for token in tokens)


def test_index_rejects_inconsistent_input() -> None:
    with pytest.raises(ValueError):
        Bm25Index(["a", "b"], ["只有一条"])
    with pytest.raises(ValueError):
        Bm25Index(["a", "a"], ["一", "二"])
    with pytest.raises(ValueError):
        Bm25Index(["a"], ["一"]).search("一", k=0)
