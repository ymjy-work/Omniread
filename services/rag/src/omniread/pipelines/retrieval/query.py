"""查询归一化与 realm 解析（M0-01 §4.1 / §4.2）。

归一化：Unicode NFC → trim → 连续空白折叠为单空格。**不折叠全半角、大小写与标点**——
折叠标点会改变 BM25 的匹配面，那属于检索行为变更，不该藏在「归一化」里；模型改写同理由
M0 不接（`options.rewrite` 字段保留，不接模型）。

realm：`past` → `chapter_index <= progress`；`full` → 全书章节。区间下界取书中最小
`chapter_index`，上界在 `past` 下取 progress、`full` 下取最大 `chapter_index`；越界即
`RAG_INVALID_REALM`。查询链与装配都拿同一个 `RealmBounds` 判成员。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from omniread.domain.errors import RagInvalidRealm
from omniread.domain.models import RealmLevel


def normalize_query(text: str) -> str:
    """NFC → trim → 连续空白折叠为单空格。

    `str.split()` 按 Unicode 空白切分并丢弃，等价于「trim + 折叠为单空格」；
    首尾与中间的空白一律收敛成一个半角空格。字符本身不做任何宽度 / 大小写 / 标点改写。
    """
    return " ".join(unicodedata.normalize("NFC", text).split())


@dataclass(frozen=True, slots=True)
class RealmBounds:
    """闭区间 `[lo, hi]`，两端都含。"""

    lo: int
    hi: int

    def contains(self, chapter_index: int) -> bool:
        return self.lo <= chapter_index <= self.hi


def resolve_realm(
    level: RealmLevel,
    progress: int | None,
    *,
    chapter_min: int,
    chapter_max: int,
) -> RealmBounds:
    """把 level / progress 解析成章节闭区间。

    `chapter_min` / `chapter_max` 取自库里的章节范围：区间不能凭空假定从 1 开始或到 193 结束。
    `past` 必须带 progress，且 progress 必须落在真实章节范围内——超界意味着调用方给的进度
    与语料对不上，静默夹到边界会让防剧透过滤悄悄失效。
    """
    if level is RealmLevel.FULL:
        return RealmBounds(lo=chapter_min, hi=chapter_max)
    if progress is None:
        raise RagInvalidRealm("level=past 必须带 progress")
    if not chapter_min <= progress <= chapter_max:
        raise RagInvalidRealm("progress 超出本书章节范围")
    return RealmBounds(lo=chapter_min, hi=progress)


__all__ = ["RealmBounds", "normalize_query", "resolve_realm"]
