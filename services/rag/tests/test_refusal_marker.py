"""模型级拒答标记的首部判定（M0-02 §8.3）。

`scan_prefix` 是流式路径上的判定核心，所以这里按「结论」把边界逐条钉死：
什么算还没法判、什么一定不是、什么已经确定是。判定错一个方向的代价不对称——
误判成拒答会丢掉一条正常回答，漏判则让 §8.3 的 `context_chapters` 区分失效。
"""

from __future__ import annotations

import pytest

from omniread.domain.citation import find_citations, find_violations
from omniread.pipelines.answering.refusal import (
    MAX_LEADING_WHITESPACE,
    PREFIX_ANSWER,
    PREFIX_PENDING,
    PREFIX_REFUSAL,
    REFUSAL_MARKER,
    scan_prefix,
)


@pytest.mark.parametrize(
    ("pending", "expected"),
    [
        ("", PREFIX_PENDING),
        ("\n", PREFIX_PENDING),
        (" " * MAX_LEADING_WHITESPACE, PREFIX_PENDING),
        ("[", PREFIX_PENDING),
        ("[INSUF", PREFIX_PENDING),
        # 少了收尾方括号仍是前缀，不能提前放行。
        (REFUSAL_MARKER[:-1], PREFIX_PENDING),
        ("\n\n  " + REFUSAL_MARKER, PREFIX_REFUSAL),
        (REFUSAL_MARKER, PREFIX_REFUSAL),
        # 标记之后还有正文也算拒答：服务端会用一个固定话术整体替换（§8.3）。
        (REFUSAL_MARKER + "\n当前进度内……", PREFIX_REFUSAL),
        # 空白上限只在**还没匹配上**时决定「不再等了」；已经匹配上的不受它影响——
        # 上限管的是缓冲别无限涨，不是「空白太多就不算拒答」。
        (" " * (MAX_LEADING_WHITESPACE + 1), PREFIX_ANSWER),
        (" " * (MAX_LEADING_WHITESPACE + 1) + REFUSAL_MARKER, PREFIX_REFUSAL),
        ("[INSUFFICIENTX", PREFIX_ANSWER),
        ("[X", PREFIX_ANSWER),
        ("艾莉", PREFIX_ANSWER),
        ("[C17]", PREFIX_ANSWER),
        ("[c17]", PREFIX_ANSWER),
    ],
)
def test_prefix_verdicts(pending: str, expected: str) -> None:
    assert scan_prefix(pending) == expected


def test_verdict_never_flips_back_to_pending_once_decided() -> None:
    """已判定的前缀再加字符，结论不许退回 `PENDING`。

    流式路径是单向的：一旦放行过，后面的分片就直接转发，回头再说「还在判定」
    没有地方可以挽回。
    """
    for decided in (REFUSAL_MARKER, "艾莉开始说俄语"):
        assert scan_prefix(decided) != PREFIX_PENDING
        assert scan_prefix(decided) == scan_prefix(decided + "后面还有字")


def test_marker_is_invisible_to_the_citation_scanner() -> None:
    """标记既不能被算成引用，也不能被算成非规范写法。

    两边共用一段正文：`CANDIDATE_PATTERN` 是 `\\[[Cc]\\d[^\\]]*\\]`——要求 `[C`/`[c]`
    后紧跟数字。标记以 `[I` 开头，天然不入选；这条断言把「天然」变成钉住的。
    """
    text = f"{REFUSAL_MARKER} 以及 [C17]"

    assert [hit.text for hit in find_citations(text)] == ["[C17]"]
    assert find_violations(text) == []
