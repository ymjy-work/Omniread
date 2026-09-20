"""重排：融合结果入 24、出 24（M0-01 §4.1，M0-00 §5）。

适配器只认 `documents` 的下标（`RerankResult.index`），chunk 标识由这里回填——
provider 不接触 chunk_key，换 provider 不影响链路语义。

返回顺序在本地再排一次（分数降序、下标升序）：适配器协议已承诺有序，但确定性不能靠
对端兑现，否则同一输入两次运行可能给出不同上下文。越界下标直接报错：那说明 provider
返回的候选与入参对不上，静默丢弃会把「对端坏了」伪装成「召回变少」。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from omniread.infrastructure.providers.base import RerankModel


@dataclass(frozen=True, slots=True)
class RerankHit:
    """一条重排命中；`score` 是 provider 给的相关性分。"""

    chunk_key: str
    score: float


async def rerank_candidates(
    reranker: RerankModel,
    query: str,
    documents: Sequence[tuple[str, str]],
    *,
    top_n: int,
) -> list[RerankHit]:
    """对 `(chunk_key, content)` 列表重排，返回前 `top_n` 条。

    空入参不调用 provider：没有候选时发请求只会把「无可召回」变成一个网络故障点。
    """
    if not documents:
        return []
    if top_n <= 0:
        raise ValueError("top_n 必须为正整数")

    results = await reranker.rerank(query, [content for _, content in documents], top_n=top_n)
    ranked = sorted(results, key=lambda result: (-result.score, result.index))

    hits: list[RerankHit] = []
    seen: set[int] = set()
    for result in ranked:
        if not 0 <= result.index < len(documents):
            raise ValueError(f"rerank 返回的下标越界：{result.index}")
        if result.index in seen:
            continue
        seen.add(result.index)
        hits.append(RerankHit(chunk_key=documents[result.index][0], score=result.score))
        if len(hits) >= top_n:
            break
    return hits


__all__ = ["RerankHit", "rerank_candidates"]
