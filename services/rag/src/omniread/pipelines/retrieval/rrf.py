"""RRF 融合（M0-01 §4.1，自研）。

分数 = Σ 1 / (k + rank)，`k = RRF_K = 60`，rank 从 1 起。只用排名不用原始分数——
dense 的余弦相似度与 BM25 的分值不同量纲，直接加权需要各自归一化，RRF 绕开了这件事。

同一个 chunk 在多路里命中时只出现一次，分数累加；`sources` 记录命中了哪几路，
供 `retrieval-only` 诊断与失败定位。排序键带并列决胜项（最好排名 → 首次出现次序），
保证同一输入永远得到同一顺序。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# 已冻结基线（M0-00 §5）。改动即新基线，必须走 run 对比。
RRF_K = 60


@dataclass(frozen=True, slots=True)
class FusedHit:
    """一条融合结果。`rank` 从 1 起，`sources` 按入参 mapping 的插入序。"""

    chunk_key: str
    score: float
    rank: int
    sources: tuple[str, ...]


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]], *, k: int = RRF_K
) -> list[FusedHit]:
    """把多路有序 chunk_key 列表融成一序。

    `rankings` 的键是路名（如 `dense` / `kw`），值是**按排名升序**的 chunk_key。
    名次就是列表下标 + 1；单路内部出现重复项时只按首次出现计分一次，重复项不再计分，
    也不压缩其后项的名次。
    """
    if k <= 0:
        raise ValueError("RRF 的 k 必须为正整数")

    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    sources: dict[str, list[str]] = {}
    sequence = 0

    for source_name, keys in rankings.items():
        seen_in_source: set[str] = set()
        for rank, chunk_key in enumerate(keys, start=1):
            if chunk_key in seen_in_source:
                continue
            seen_in_source.add(chunk_key)
            if chunk_key not in scores:
                scores[chunk_key] = 0.0
                best_rank[chunk_key] = rank
                first_seen[chunk_key] = sequence
                sources[chunk_key] = []
                sequence += 1
            scores[chunk_key] += 1.0 / (k + rank)
            if rank < best_rank[chunk_key]:
                best_rank[chunk_key] = rank
            sources[chunk_key].append(source_name)

    ordered = sorted(
        scores,
        key=lambda key: (-scores[key], best_rank[key], first_seen[key]),
    )
    return [
        FusedHit(
            chunk_key=chunk_key,
            score=scores[chunk_key],
            rank=rank,
            sources=tuple(sources[chunk_key]),
        )
        for rank, chunk_key in enumerate(ordered, start=1)
    ]
