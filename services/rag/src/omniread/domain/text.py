"""正文规范化与哈希口径（P-3）。

口径定死在这里，导入、`checksums.json`、`chunk_mappings.evidence_hash` 三处共用同一函数：
口径一旦分叉，「同一章」在不同产物里的 hash 就对不上，重算也无法对齐。

P-3 最小规范化：统一换行为 `\\n`、去行尾空白；`[插图NNN]` 占位符保留；
全半角与标点不动（动标点会改变 BM25 的匹配面，那属于检索行为变更）。
"""

from __future__ import annotations

import hashlib


def normalize_minimal(text: str) -> str:
    """P-3 最小规范化：CRLF / CR 统一为 LF，逐行去行尾空白。"""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in unified.split("\n"))


def sha256_hex(text: str) -> str:
    """UTF-8 编码后的 sha256 小写十六进制（64 字符）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chapter_content_hash(raw_text: str) -> str:
    """章节正文 hash：对最小规范化后的正文取 sha256。

    与 `checksums.json` 的逐章 hash 必须一致——两处都调用本函数，不各自实现。
    """
    return sha256_hex(normalize_minimal(raw_text))


def evidence_hash(chapter_id: str, raw_content: str) -> str:
    """`chunk_mappings.evidence_hash`：`sha256(chapter_id + "\\n" + content)`。

    content 同样走最小规范化；chapter_id 是标识符，不参与规范化。
    """
    return sha256_hex(f"{chapter_id}\n{normalize_minimal(raw_content)}")
