"""装配（M0-01 §4.3）：三道 cap、邻块方向与同章、realm、token budget。

语料是合成的小书：章内 chunk 用 prev/next 串成链，与导入后 `chunks` 表的形状一致。
装配只读这份视图，测试不碰数据库也不需要 provider。
"""

from __future__ import annotations

from collections.abc import Sequence

from omniread.pipelines.assembly import (
    REASON_CHAPTER_CAP,
    REASON_CHAPTER_CHUNK_CAP,
    REASON_REALM,
    REASON_TOKEN_BUDGET,
    REASON_TOP_K_CAP,
    AssembledChunk,
    AssemblyResult,
    ChunkCandidate,
    DroppedChunk,
    assemble,
)
from omniread.pipelines.params import RetrievalParams
from omniread.pipelines.retrieval.query import RealmBounds
from omniread.pipelines.retrieval.types import ChunkRecord

FULL = RealmBounds(lo=1, hi=999)


def _chapter_id(chapter: int) -> str:
    return f"book:1:chapter:{chapter}"


def _key(chapter: int, index: int) -> str:
    return f"{_chapter_id(chapter)}#c{index}"


def _chain(chapter: int, count: int, *, tokens: int = 100) -> list[ChunkRecord]:
    """一章 `count` 个 chunk，prev/next 只指向同章。"""
    records: list[ChunkRecord] = []
    for index in range(count):
        records.append(
            ChunkRecord(
                chunk_key=_key(chapter, index),
                chapter_index=chapter,
                chunk_index=index,
                content=f"第{chapter}章第{index}段",
                token_count=tokens,
                prev_chunk_key=_key(chapter, index - 1) if index > 0 else None,
                next_chunk_key=_key(chapter, index + 1) if index + 1 < count else None,
            )
        )
    return records


def _index(records: Sequence[ChunkRecord]) -> dict[str, ChunkRecord]:
    return {record.chunk_key: record for record in records}


def _run(
    candidates: Sequence[ChunkCandidate],
    records: Sequence[ChunkRecord],
    *,
    realm: RealmBounds = FULL,
    params: RetrievalParams | None = None,
) -> AssemblyResult:
    return assemble(
        candidates,
        chunks=_index(records),
        realm=realm,
        params=params or RetrievalParams(),
    )


def _keys(items: Sequence[AssembledChunk]) -> list[str]:
    return [item.chunk_key for item in items]


def _reasons(dropped: Sequence[DroppedChunk], reason: str) -> list[DroppedChunk]:
    return [item for item in dropped if item.reason == reason]


def test_chapter_cap_keeps_first_eight_chapters() -> None:
    # 9 个章各一条命中：章上限 8 生效，第 9 章整章的候选记 chapter_cap。
    records = [record for chapter in range(1, 10) for record in _chain(chapter, 1)]
    candidates = [
        ChunkCandidate(_key(chapter, 0), score=1.0, rank=chapter) for chapter in range(1, 10)
    ]

    result = _run(candidates, records)

    assert sorted({item.chapter_index for item in result.chunks}) == list(range(1, 9))
    assert len(result.chunks) == 8
    assert [item.chunk_key for item in _reasons(result.dropped, REASON_CHAPTER_CAP)] == [_key(9, 0)]


def test_chapter_chunk_cap_keeps_two_chunks_per_chapter() -> None:
    # 同章 3 条命中：每章 ≤2 生效，第 3 条记 chapter_chunk_cap，且不再补邻块。
    records = _chain(1, 3)
    candidates = [
        ChunkCandidate(_key(1, 0), 3.0, 1),
        ChunkCandidate(_key(1, 1), 2.0, 2),
        ChunkCandidate(_key(1, 2), 1.0, 3),
    ]

    result = _run(candidates, records)

    assert _keys(result.chunks) == [_key(1, 0), _key(1, 1)]
    assert all(item.source == "hit" for item in result.chunks)
    assert [item.chunk_key for item in _reasons(result.dropped, REASON_CHAPTER_CHUNK_CAP)] == [
        _key(1, 2)
    ]


def test_top_k_cap_truncates_after_the_other_two_caps() -> None:
    # 8 章各 1 hit + 1 邻居 = 16 段，最后按 rerank 序截断到 8。
    # 章上限与每章段数都已先结算，所以被截掉的是第 5–8 章，而不是「只剩 8 章候选」。
    records = [record for chapter in range(1, 9) for record in _chain(chapter, 2)]
    candidates = [ChunkCandidate(_key(chapter, 0), 1.0, chapter) for chapter in range(1, 9)]

    result = _run(candidates, records)

    assert len(result.chunks) == 8
    assert sorted({item.chapter_index for item in result.chunks}) == [1, 2, 3, 4]
    assert len(_reasons(result.dropped, REASON_TOP_K_CAP)) == 8
    assert not _reasons(result.dropped, REASON_CHAPTER_CAP)


def test_top_k_truncates_by_rerank_rank_not_by_chapter_order() -> None:
    # 截断必须按 rerank 名次，不能按「章序 → 章内序」。
    # 构造：第 1 章两条命中（名次 1 与 9），第 2..8 章各一条（名次 2..8）。
    # 两种截断法结果不同：
    #   按名次 → 留名次 1..8，丢第 1 章的第二条（名次 9）；
    #   按章序 → 第 1 章两条都靠前，反而丢掉第 8 章那条名次更高的命中。
    # 各章只有一个 chunk，所以没有可补的邻居，候选池就是这 9 条本身。
    records = _chain(1, 2) + [record for chapter in range(2, 9) for record in _chain(chapter, 1)]
    candidates = [
        ChunkCandidate(_key(1, 0), 9.0, 1),
        *[ChunkCandidate(_key(chapter, 0), 1.0, chapter) for chapter in range(2, 9)],
        ChunkCandidate(_key(1, 1), 0.5, 9),
    ]

    result = _run(candidates, records)

    assert len(result.chunks) == 8
    assert _key(8, 0) in _keys(result.chunks), "名次 8 的命中被名次 9 挤掉了"
    assert _key(1, 1) not in _keys(result.chunks)
    assert [item.chunk_key for item in _reasons(result.dropped, REASON_TOP_K_CAP)] == [_key(1, 1)]


def test_neighbor_prefers_prev_over_next() -> None:
    # 命中 c1：prev=c0、next=c2 都在，补位必须取 prev。
    records = _chain(1, 3)
    candidates = [ChunkCandidate(_key(1, 1), 1.0, 1)]

    result = _run(candidates, records)

    neighbors = [item for item in result.chunks if item.source == "neighbor"]
    assert [item.chunk_key for item in neighbors] == [_key(1, 0)]
    assert neighbors[0].from_hit_chunk_key == _key(1, 1)


def test_neighbor_falls_back_to_next_when_prev_is_absent() -> None:
    # 命中章内首块（无 prev），补位取 next。
    records = _chain(1, 2)
    candidates = [ChunkCandidate(_key(1, 0), 1.0, 1)]

    result = _run(candidates, records)

    neighbors = [item for item in result.chunks if item.source == "neighbor"]
    assert [item.chunk_key for item in neighbors] == [_key(1, 1)]
    assert neighbors[0].from_hit_chunk_key == _key(1, 0)


def test_neighbor_never_crosses_chapter() -> None:
    # 锚点是第 1 章末块，其 next 指向第 2 章首块（构造出的越界链）：不得补位。
    chapter_one = _chain(1, 1)
    chapter_one[0] = ChunkRecord(
        chunk_key=_key(1, 0),
        chapter_index=1,
        chunk_index=0,
        content="第1章",
        token_count=100,
        prev_chunk_key=None,
        next_chunk_key=_key(2, 0),
    )
    records = [*chapter_one, *_chain(2, 1)]
    candidates = [ChunkCandidate(_key(1, 0), 1.0, 1)]

    result = _run(candidates, records)

    assert _keys(result.chunks) == [_key(1, 0)]
    assert all(item.source == "hit" for item in result.chunks)


def test_neighbor_is_single_hop_only() -> None:
    # 命中 c2，prev=c1：只补一跳（c1），不得沿 c1.prev 递归到 c0。
    records = _chain(1, 3)
    candidates = [ChunkCandidate(_key(1, 2), 1.0, 1)]

    result = _run(candidates, records)

    assert _keys(result.chunks) == [_key(1, 1), _key(1, 2)]
    assert _key(1, 0) not in _keys(result.chunks)


def test_hit_and_neighbor_share_the_per_chapter_cap() -> None:
    # 同章两条命中时不再补位：hit + neighbor 合计 ≤2。
    records = _chain(1, 3)
    candidates = [ChunkCandidate(_key(1, 1), 2.0, 1), ChunkCandidate(_key(1, 0), 1.0, 2)]

    result = _run(candidates, records)

    assert sorted(_keys(result.chunks)) == sorted([_key(1, 0), _key(1, 1)])
    assert all(item.source == "hit" for item in result.chunks)


def test_realm_drops_candidates_outside_the_interval() -> None:
    records = [record for chapter in range(1, 4) for record in _chain(chapter, 1)]
    candidates = [ChunkCandidate(_key(chapter, 0), 1.0, chapter) for chapter in range(1, 4)]

    result = _run(candidates, records, realm=RealmBounds(lo=1, hi=2))

    assert [item.chapter_index for item in result.chunks] == [1, 2]
    assert [item.chunk_key for item in _reasons(result.dropped, REASON_REALM)] == [_key(3, 0)]


def test_realm_bounds_membership_is_closed_on_both_ends() -> None:
    records = [record for chapter in (1, 2, 3) for record in _chain(chapter, 1)]
    candidates = [ChunkCandidate(_key(chapter, 0), 1.0, chapter) for chapter in (1, 2, 3)]

    result = _run(candidates, records, realm=RealmBounds(lo=2, hi=3))

    assert [item.chapter_index for item in result.chunks] == [2, 3]


def test_presentation_is_ascending_by_chunk_index() -> None:
    # 同章内命中按 rerank 序为 c2 → c0，但呈现必须按 chunk_index 升序。
    records = _chain(1, 3)
    candidates = [ChunkCandidate(_key(1, 2), 2.0, 1), ChunkCandidate(_key(1, 0), 1.0, 2)]

    result = _run(candidates, records)

    assert _keys(result.chunks) == [_key(1, 0), _key(1, 2)]
    assert result.token_estimate == 200


def test_token_budget_drops_lowest_rank_hits_first() -> None:
    # 8 条 hit 各 700 token，预算 4800：按 rerank 逆序丢最低分，丢 rank 8、7。
    records = [record for chapter in range(1, 9) for record in _chain(chapter, 1, tokens=700)]
    candidates = [ChunkCandidate(_key(chapter, 0), 1.0, chapter) for chapter in range(1, 9)]
    params = RetrievalParams(prompt_token_budget=4800)

    result = _run(candidates, records, params=params)

    assert [item.rank for item in result.chunks] == [1, 2, 3, 4, 5, 6]
    assert {item.chunk_key for item in _reasons(result.dropped, REASON_TOKEN_BUDGET)} == {
        _key(7, 0),
        _key(8, 0),
    }


def test_token_budget_drops_neighbors_before_hits() -> None:
    # 截断后 4 组 hit+邻居各 700，共 5600 > 预算 4800：hit（2800）保得住，
    # 邻居按锚点名次逆序让位，丢 rank 4、3 的补位后回到 4200。
    records = [record for chapter in range(1, 9) for record in _chain(chapter, 2, tokens=700)]
    candidates = [ChunkCandidate(_key(chapter, 0), 1.0, chapter) for chapter in range(1, 9)]
    params = RetrievalParams(prompt_token_budget=4800)

    result = _run(candidates, records, params=params)

    hits = [item for item in result.chunks if item.source == "hit"]
    neighbors = [item for item in result.chunks if item.source == "neighbor"]
    assert sorted(item.chapter_index for item in hits) == [1, 2, 3, 4]
    assert sorted(item.chapter_index for item in neighbors) == [1, 2]
    assert result.token_estimate == 4200
    assert {item.chunk_key for item in _reasons(result.dropped, REASON_TOKEN_BUDGET)} == {
        _key(3, 1),
        _key(4, 1),
    }


def test_token_budget_hit_drop_takes_its_neighbor() -> None:
    # hit 2000 + 邻居 100，预算 4800：hit 自身超预算，按 rerank 逆序丢 rank 4、3 的 hit，
    # 并连带丢它们的邻居，避免 from_hit 指向已出局的锚点。
    records: list[ChunkRecord] = []
    for chapter in range(1, 9):
        records.append(
            ChunkRecord(
                chunk_key=_key(chapter, 0),
                chapter_index=chapter,
                chunk_index=0,
                content=f"第{chapter}章命中",
                token_count=2000,
                prev_chunk_key=None,
                next_chunk_key=_key(chapter, 1),
            )
        )
        records.append(
            ChunkRecord(
                chunk_key=_key(chapter, 1),
                chapter_index=chapter,
                chunk_index=1,
                content=f"第{chapter}章邻居",
                token_count=100,
                prev_chunk_key=_key(chapter, 0),
                next_chunk_key=None,
            )
        )
    candidates = [ChunkCandidate(_key(chapter, 0), 1.0, chapter) for chapter in range(1, 9)]
    params = RetrievalParams(prompt_token_budget=4800)

    result = _run(candidates, records, params=params)

    hit_keys = {item.chunk_key for item in result.chunks if item.source == "hit"}
    assert hit_keys == {_key(1, 0), _key(2, 0)}
    for item in result.chunks:
        if item.source == "neighbor":
            assert item.from_hit_chunk_key in hit_keys
    dropped_keys = {item.chunk_key for item in _reasons(result.dropped, REASON_TOKEN_BUDGET)}
    assert dropped_keys == {
        _key(3, 0),
        _key(3, 1),
        _key(4, 0),
        _key(4, 1),
    }


def test_missing_chunk_is_dropped_instead_of_crashing() -> None:
    records = _chain(1, 1)
    candidates = [ChunkCandidate("不存在#c0", 1.0, 1), ChunkCandidate(_key(1, 0), 0.5, 2)]

    result = _run(candidates, records)

    assert _keys(result.chunks) == [_key(1, 0)]
    assert [item.chunk_key for item in result.dropped] == ["不存在#c0"]
