"""BM25 关键词检索（M0-01 §4.1 / §4.2）。

`bm25s` + `jieba`：jieba 的分词结果直接作为 token 序列交给 `BM25.index`，
不走 `bm25s.tokenize` 的默认英文正则与英文停用词表——中文语料上那套分词会把
整句切成一个词。分词只丢弃纯空白 token，保留标点与大小写：标点折叠会改变 BM25 的
匹配面，属于检索行为变更（M0-01 §4.1）。

**统计量全局、realm 只过滤候选**：索引一次构建，IDF 与平均文档长度取自全书；
`search(..., allowed_keys=...)` 在选取与排序前把候选收窄到 realm 允许的 chunk。
「全局统计 + 过滤候选」与「先过滤再打分」等价——BM25 单文档得分只取决于该文档自身
与全量统计量，与候选集合无关。按 realm 子集重建索引则会得到不同的 IDF 与平均长度，
同一 chunk 在不同 progress 下排名漂移，融合结果不可复现。
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

import bm25s
import jieba

# jieba 首次装载词表会直接往 stderr 打印进度，绕过本服务的 logging 配置；
# 服务日志统一走 logging，把 jieba 自己的输出压到 WARNING 以上。
jieba.setLogLevel(logging.WARNING)

# 关键词召回的候选数（M0-00 §5）。这里给默认值，实际值由管线显式传入。
DEFAULT_KW_K = 60


def tokenize(text: str) -> list[str]:
    """jieba 精确分词，丢弃纯空白 token。空文本返回空列表。"""
    return [token for token in jieba.lcut(text) if token.strip()]


@dataclass(frozen=True, slots=True)
class KeywordHit:
    """一条关键词命中。`rank` 从 1 起。"""

    chunk_key: str
    score: float
    rank: int


class Bm25Index:
    """全书 chunk 的 BM25 索引，进程内常驻。

    索引一次构建、跨查询复用；调用方按 realm 传 `allowed_keys` 收窄候选，
    本类不感知 realm 语义（level 与 progress 的解释属于检索管线）。
    """

    __slots__ = ("_bm25", "_keys", "_position")

    def __init__(self, chunk_keys: Sequence[str], contents: Sequence[str]) -> None:
        if len(chunk_keys) != len(contents):
            raise ValueError("chunk_keys 与 contents 长度必须一致")
        if len(set(chunk_keys)) != len(chunk_keys):
            raise ValueError("chunk_keys 必须唯一：chunk_key 是 chunks 表主键")
        self._keys = list(chunk_keys)
        self._position = {key: index for index, key in enumerate(self._keys)}
        self._bm25 = bm25s.BM25()
        # 索引一次构建，统计量（IDF / 平均文档长度）取自全书，realm 不动它。
        self._bm25.index([tokenize(content) for content in contents], show_progress=False)

    def __len__(self) -> int:
        return len(self._keys)

    def search(
        self,
        query: str,
        k: int = DEFAULT_KW_K,
        *,
        allowed_keys: Collection[str] | None = None,
    ) -> list[KeywordHit]:
        """按 BM25 分数取前 `k` 条；`allowed_keys` 非空时只在其中选取。

        `allowed_keys=None` 表示全域候选；传空集合表示无候选，直接返回空列表
        ——这与 `None` 是两件事，不能合并。

        零分文档不入选：零分表示没有任何查询词命中，其排序只由 chunk_key 决定，
        放进候选等于给 RRF 注入与查询无关的名次。
        """
        if k <= 0:
            raise ValueError("k 必须为正整数")
        if allowed_keys is not None and not allowed_keys:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        candidates: Iterable[int]
        if allowed_keys is None:
            candidates = range(len(self._keys))
        else:
            allowed = set(allowed_keys)
            candidates = (
                position for key, position in self._position.items() if key in allowed
            )
        ranked = sorted(
            (position for position in candidates if scores[position] > 0),
            key=lambda position: (-float(scores[position]), self._keys[position]),
        )
        return [
            KeywordHit(chunk_key=self._keys[position], score=float(scores[position]), rank=rank)
            for rank, position in enumerate(ranked[:k], start=1)
        ]


__all__ = ["DEFAULT_KW_K", "Bm25Index", "KeywordHit", "tokenize"]
