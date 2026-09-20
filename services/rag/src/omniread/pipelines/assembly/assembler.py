"""上下文装配：章去重 + 邻块补位 + 截断 + realm re-check + token budget（M0-01 §4.3）。

顺序不可调换，且每一步的判据都独立可查：

1. **先限章**（`ask_max_chapters`）：按 rerank 序做章级去重，保留入选章而不是「保留整章」；
   已选满 8 章后，候选池里其余章节的命中记 `chapter_cap`。
2. **再限每章段数**（`ask_chunks_per_chapter`）：章内先取主命中（`source=hit`），再用同章
   prev/next 补位（`source=neighbor`）；hit + neighbor 合计 ≤2，多出的 hit 记
   `chapter_chunk_cap`。邻块固定一跳、必须同章、必须满足 realm，**不递归、不再检索、
   不再 rerank**；补位先取 prev，prev 不可用（不存在 / 已入选）再取 next。
3. **最后按 rerank 序截断**（`ask_top_k`）：顺序是「章序 → 章内 hit 序 → 该章邻居」，
   超出的记 `top_k_cap`。先截断再限章会让章上限永不生效，所以这一步必须在最后。
4. **realm re-check**：截断后再查一遍章节成员，越界的记 `realm`。
5. **token budget**：先保 hit 再保 neighbor；hit 自身超预算时按 rerank 逆序丢最低分 hit，
   丢 hit 时连带丢掉它的邻居（`from_hit_chunk_key` 必须指向仍入选的 hit，否则失败定位失效）。

最终 `chunks` 按 `chunk_index` 升序呈现（喂给模型时的顺序），截断仍按 rerank 序。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from omniread.pipelines.params import M0_PARAMS, RetrievalParams

if TYPE_CHECKING:
    # 只在类型注解里用到：运行期装配靠 `realm.contains()` 鸭子调用。写进运行期 import
    # 会让 `retrieval` 包在装配之前被加载，从而与 pipeline 形成循环导入。
    from omniread.pipelines.retrieval.query import RealmBounds

# 装配产物的来源：主命中，或同章邻居补位。
Source = Literal["hit", "neighbor"]

# 被裁原因；`retrieval-only` 的 `dropped[].reason` 直接用这些字面量。
REASON_MISSING_CHUNK = "missing_chunk"
REASON_REALM = "realm"
REASON_CHAPTER_CAP = "chapter_cap"
REASON_CHAPTER_CHUNK_CAP = "chapter_chunk_cap"
REASON_TOP_K_CAP = "top_k_cap"
REASON_TOKEN_BUDGET = "token_budget"


class Neighborhood(Protocol):
    """装配需要的 chunk 邻域视图；`ChunkRecord` 与测试替身都满足它。

    属性声明成只读：`ChunkRecord` 是 frozen dataclass，只读字段无法满足可写属性的契约。
    """

    @property
    def chapter_index(self) -> int: ...

    @property
    def chunk_index(self) -> int: ...

    @property
    def token_count(self) -> int: ...

    @property
    def prev_chunk_key(self) -> str | None: ...

    @property
    def next_chunk_key(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ChunkCandidate:
    """进入装配池的一条候选，按 rerank 序排列。`rank` 从 1 起，`score` 是 rerank 分。"""

    chunk_key: str
    score: float
    rank: int


@dataclass(frozen=True, slots=True)
class AssembledChunk:
    """最终上下文里的一段。`from_hit_chunk_key` 供失败定位：邻居回指它的锚点命中。

    `rank` 是锚点在 rerank 结果里的名次（邻居沿用锚点的名次）：装配按章分组呈现，
    呈现顺序不等于 rerank 序，而 token budget 丢 hit 时必须按 rerank 逆序丢最低分，
    所以名次随段一起带到结算这一步。
    """

    chunk_key: str
    chapter_index: int
    chunk_index: int
    source: Source
    from_hit_chunk_key: str
    token_count: int
    rank: int


@dataclass(frozen=True, slots=True)
class DroppedChunk:
    chunk_key: str
    reason: str


@dataclass(frozen=True, slots=True)
class AssemblyResult:
    """`chunks` 已结算 realm 与 budget，按 `(chapter_index, chunk_index)` 升序。"""

    chunks: tuple[AssembledChunk, ...]
    dropped: tuple[DroppedChunk, ...]
    token_estimate: int


def assemble(
    candidates: Sequence[ChunkCandidate],
    *,
    chunks: Mapping[str, Neighborhood],
    realm: RealmBounds,
    params: RetrievalParams = M0_PARAMS,
    expand_neighbors: bool = True,
) -> AssemblyResult:
    """按 M0-01 §4.3 把 rerank 候选池装配成最终上下文。

    `candidates` 是 rerank 序的候选池（入口按 `rank` 再排一次，避免调用方传乱序）；
    `chunks` 是本次加载的 chunk 视图，邻块补位只在这里面查，不触发新的检索。
    """
    dropped: list[DroppedChunk] = []
    ordered = sorted(candidates, key=lambda candidate: candidate.rank)

    # 1. 章级去重：按 rerank 序保留入选章。
    chapter_order: list[int] = []
    hits_by_chapter: dict[int, list[ChunkCandidate]] = {}
    for candidate in ordered:
        record = chunks.get(candidate.chunk_key)
        if record is None:
            dropped.append(DroppedChunk(candidate.chunk_key, REASON_MISSING_CHUNK))
            continue
        chapter = record.chapter_index
        if not realm.contains(chapter):
            dropped.append(DroppedChunk(candidate.chunk_key, REASON_REALM))
            continue
        if chapter not in hits_by_chapter:
            if len(chapter_order) >= params.ask_max_chapters:
                dropped.append(DroppedChunk(candidate.chunk_key, REASON_CHAPTER_CAP))
                continue
            chapter_order.append(chapter)
            hits_by_chapter[chapter] = []
        hits_by_chapter[chapter].append(candidate)

    # 2. 每章：先 hit，再同章 prev/next 补位，合计 ≤ ask_chunks_per_chapter。
    items: list[AssembledChunk] = []
    for chapter in chapter_order:
        picked: list[ChunkCandidate] = []
        for candidate in hits_by_chapter[chapter]:
            if len(picked) >= params.ask_chunks_per_chapter:
                dropped.append(DroppedChunk(candidate.chunk_key, REASON_CHAPTER_CHUNK_CAP))
                continue
            picked.append(candidate)
        for candidate in picked:
            record = chunks[candidate.chunk_key]
            items.append(
                AssembledChunk(
                    chunk_key=candidate.chunk_key,
                    chapter_index=chapter,
                    chunk_index=record.chunk_index,
                    source="hit",
                    from_hit_chunk_key=candidate.chunk_key,
                    token_count=record.token_count,
                    rank=candidate.rank,
                )
            )
        if expand_neighbors and len(picked) < params.ask_chunks_per_chapter:
            neighbor = _pick_neighbor(
                picked[0], chunks=chunks, realm=realm, taken={item.chunk_key for item in items}
            )
            if neighbor is not None:
                items.append(neighbor)

    # 3. 按 rerank 序截断到 ask_top_k。
    # 必须先按名次排序再切片：items 是按章分组拼出来的，直接切片等于按「章序 → 章内序」截断，
    # 会让同一章的第二条命中挤掉后面章里名次更高的命中（实测可复现 rank9 入选、rank8 被截）。
    # 邻居的 rank 沿用其锚点名次；sorted 稳定，同 rank 时先出现的 hit 排在它的邻居之前，
    # 因此只剩一个名额时留下的是 hit。
    by_rank = sorted(items, key=lambda item: item.rank)
    kept = by_rank[: params.ask_top_k]
    dropped.extend(
        DroppedChunk(item.chunk_key, REASON_TOP_K_CAP) for item in by_rank[params.ask_top_k :]
    )

    # 4. realm re-check：补位与前序过滤之后仍以同一区间复查一次。
    rechecked: list[AssembledChunk] = []
    for item in kept:
        if realm.contains(item.chapter_index):
            rechecked.append(item)
        else:
            dropped.append(DroppedChunk(item.chunk_key, REASON_REALM))
    kept = rechecked

    # 5. token budget：先保 hit 再保 neighbor。
    kept, budget_dropped = _apply_token_budget(kept, params)
    dropped.extend(budget_dropped)

    # 6. 呈现顺序：按章内 chunk_index 升序；截断早已按 rerank 序完成。
    presented = tuple(sorted(kept, key=lambda item: (item.chapter_index, item.chunk_index)))
    return AssemblyResult(
        chunks=presented,
        dropped=tuple(dropped),
        token_estimate=sum(item.token_count for item in presented),
    )


def _pick_neighbor(
    anchor: ChunkCandidate,
    *,
    chunks: Mapping[str, Neighborhood],
    realm: RealmBounds,
    taken: set[str],
) -> AssembledChunk | None:
    """按 prev_first 取锚点的一个同章邻居；不可用则返回 None。

    「不可用」包括：不存在、已入选、跨章（`prev/next` 理论上只在同章，仍校验）、
    越出 realm；prev 不可用时才看 next。只取一跳，不沿着邻居继续找。
    """
    anchor_record = chunks[anchor.chunk_key]
    for key in (anchor_record.prev_chunk_key, anchor_record.next_chunk_key):
        if key is None or key in taken:
            continue
        record = chunks.get(key)
        if record is None or record.chapter_index != anchor_record.chapter_index:
            continue
        if not realm.contains(record.chapter_index):
            continue
        return AssembledChunk(
            chunk_key=key,
            chapter_index=record.chapter_index,
            chunk_index=record.chunk_index,
            source="neighbor",
            from_hit_chunk_key=anchor.chunk_key,
            token_count=record.token_count,
            rank=anchor.rank,
        )
    return None


def _apply_token_budget(
    items: Sequence[AssembledChunk], params: RetrievalParams
) -> tuple[list[AssembledChunk], list[DroppedChunk]]:
    """先保 hit 再保 neighbor：邻居先让位，只有 hit 自身装不下时才丢 hit。

    丢 hit 一律按 rerank 逆序（名次最大 = 分数最低的先出局），不能用呈现顺序——
    装配按章分组后呈现顺序不再是 rerank 序，拿它当优先级会丢掉分数更高的 hit。
    丢 hit 时连带丢它的邻居（`from_hit_chunk_key` 必须指向仍入选的 hit，否则失败定位失效）；
    邻居同按锚点名次的逆序让位，名次相同再按 chunk_key 定序，保证确定性。
    """
    kept = list(items)
    dropped: list[DroppedChunk] = []
    budget = params.prompt_token_budget

    hits = [item for item in kept if item.source == "hit"]
    hits_total = _total_tokens(hits)
    if hits_total > budget:
        for hit in sorted(hits, key=lambda item: (-item.rank, item.chunk_key)):
            if hits_total <= budget:
                break
            # 命中项自身；以及 from_hit 指向它的邻居——锚点被丢后邻居的 from_hit 就悬空了。
            removed = [
                item
                for item in kept
                if item.chunk_key == hit.chunk_key
                or (item.source == "neighbor" and item.from_hit_chunk_key == hit.chunk_key)
            ]
            for item in removed:
                kept.remove(item)
                dropped.append(DroppedChunk(item.chunk_key, REASON_TOKEN_BUDGET))
            hits_total -= hit.token_count

    neighbors = sorted(
        (item for item in kept if item.source == "neighbor"),
        key=lambda item: (-item.rank, item.chunk_key),
    )
    for neighbor in neighbors:
        if _total_tokens(kept) <= budget:
            break
        kept.remove(neighbor)
        dropped.append(DroppedChunk(neighbor.chunk_key, REASON_TOKEN_BUDGET))

    return kept, dropped


def _total_tokens(items: Sequence[AssembledChunk]) -> int:
    return sum(item.token_count for item in items)


__all__ = [
    "REASON_CHAPTER_CAP",
    "REASON_CHAPTER_CHUNK_CAP",
    "REASON_MISSING_CHUNK",
    "REASON_REALM",
    "REASON_TOKEN_BUDGET",
    "REASON_TOP_K_CAP",
    "AssembledChunk",
    "AssemblyResult",
    "ChunkCandidate",
    "DroppedChunk",
    "Neighborhood",
    "Source",
    "assemble",
]
