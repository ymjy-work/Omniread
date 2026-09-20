"""正文规范化与 hash 口径的单测。

这两个口径是跨产物契约（`chapters.content_hash` 与 `checksums.json`、
`chunk_mappings.evidence_hash`），钉住具体输出值，改动即测试失败。
"""

from __future__ import annotations

import hashlib

from omniread.domain.text import (
    chapter_content_hash,
    evidence_hash,
    normalize_minimal,
    sha256_hex,
)


def test_normalize_unifies_newlines_and_strips_line_trailing_whitespace() -> None:
    assert normalize_minimal("a\r\nb\r\nc  \r\n") == "a\nb\nc\n"
    assert normalize_minimal("a\t \nb") == "a\nb"


def test_normalize_keeps_illustration_marker_and_leading_space() -> None:
    assert normalize_minimal("  缩进保留\n[插图007]") == "  缩进保留\n[插图007]"


def test_sha256_hex_is_utf8_hexdigest() -> None:
    assert sha256_hex("艾莉") == hashlib.sha256("艾莉".encode()).hexdigest()


def test_chapter_content_hash_ignores_crlf_and_trailing_whitespace() -> None:
    # 同正文的两种换行 / 行尾空白写法必须是同一个 hash。
    assert chapter_content_hash("第一段  \r\n\r\n第二段\r\n") == chapter_content_hash(
        "第一段\n\n第二段\n"
    )


def test_evidence_hash_pins_chapter_id_and_normalized_content() -> None:
    # content 无行尾空白时规范化是恒等变换，hash 直接由 `chapter_id + "\n" + content` 得到。
    expected = hashlib.sha256("book:1:chapter:17\n证据原文".encode()).hexdigest()
    assert evidence_hash("book:1:chapter:17", "证据原文") == expected
