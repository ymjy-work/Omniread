"""查询归一化口径与 realm 区间解析（M0-01 §4.1 / §4.2）。"""

from __future__ import annotations

import pytest

from omniread.domain.errors import RagInvalidRealm
from omniread.domain.models import RealmLevel
from omniread.pipelines.retrieval.query import RealmBounds, normalize_query, resolve_realm


def test_normalize_collapses_unicode_whitespace_to_single_space() -> None:
    assert normalize_query("  艾莉　俄语\t是\n 什么 ") == "艾莉 俄语 是 什么"


def test_normalize_does_not_fold_width_case_or_punctuation() -> None:
    # 折叠标点 / 全半角会改变 BM25 的匹配面，属于检索行为变更，不在归一化里做。
    assert normalize_query("ＡＢC，艾莉。") == "ＡＢC，艾莉。"
    assert normalize_query("ABC") == "ABC"


def test_realm_bounds_membership_is_closed() -> None:
    bounds = RealmBounds(lo=2, hi=4)

    assert bounds.contains(2) and bounds.contains(4)
    assert not bounds.contains(1) and not bounds.contains(5)


def test_full_realm_spans_book_chapter_range() -> None:
    assert resolve_realm(RealmLevel.FULL, None, chapter_min=1, chapter_max=193) == RealmBounds(
        1, 193
    )


def test_past_realm_stops_at_progress() -> None:
    assert resolve_realm(RealmLevel.PAST, 45, chapter_min=1, chapter_max=193) == RealmBounds(
        1, 45
    )


def test_past_requires_progress() -> None:
    with pytest.raises(RagInvalidRealm):
        resolve_realm(RealmLevel.PAST, None, chapter_min=1, chapter_max=193)


def test_past_rejects_progress_outside_the_book_range() -> None:
    with pytest.raises(RagInvalidRealm):
        resolve_realm(RealmLevel.PAST, 0, chapter_min=1, chapter_max=193)
    with pytest.raises(RagInvalidRealm):
        resolve_realm(RealmLevel.PAST, 194, chapter_min=1, chapter_max=193)
