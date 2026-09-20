"""引用标记 `[C{chapter_index}]` 的扫描口径（Python 侧实现）。

权威定义在仓库根 `citation-format.json`：正则、语义与样本都只有那一份。
两语言无法共用同一个文件，所以这里复制一份实现，TS 侧在 `web/src/citation.ts`，
两侧由 `services/rag/tests/test_citation_equivalence.py` 用同一批样本断言等价。

三条口径：

- 大小写敏感：`[c17]` 不是引用。
- 捕获组必须无前导零：`[C017]` 不是引用。
- 只用于扫描与渲染，不是净化规则：回答正文原样保留，越界引用与违规写法都不改写。

`re.ASCII` 不是可选装饰：Python 的 `\\d` 默认匹配 Unicode 十进制数字，而 JS 的 `\\d`
只匹配 ASCII 0-9。不加这个标志，`[C１７]`（全角）之类会在两侧得出不同结论。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: 规范引用正则源码，与 citation-format.json 的 `pattern` 逐字一致
CITATION_PATTERN = r"\[C(\d{1,3})\]"

#: 非规范写法的候选扫描正则源码，与 citation-format.json 的 `candidate_pattern` 逐字一致
CANDIDATE_PATTERN = r"\[[Cc]\d[^\]]*\]"

_CANDIDATE_RE = re.compile(CANDIDATE_PATTERN, re.ASCII)
_CITATION_FULL_RE = re.compile(CITATION_PATTERN, re.ASCII)


@dataclass(frozen=True)
class CitationHit:
    """一条规范引用：章序号与它在原文中的位置。"""

    chapter_index: int
    #: 命中的原文片段（含方括号）
    text: str
    #: 在原文中的起止下标（Python 字符串按码点计）
    start: int
    end: int


def is_canonical_number(digits: str) -> bool:
    """前导零（`017`）不算规范写法；`0` 本身没有前导零，仍是规范数字。"""
    if digits == "":
        return False
    return not (len(digits) > 1 and digits.startswith("0"))


def find_citations(text: str) -> list[CitationHit]:
    """扫描正文中全部规范引用，按出现顺序返回。"""
    hits: list[CitationHit] = []
    for candidate in _CANDIDATE_RE.finditer(text):
        raw = candidate.group(0)
        canonical = _CITATION_FULL_RE.fullmatch(raw)
        if canonical is None or not is_canonical_number(canonical.group(1)):
            continue
        hits.append(
            CitationHit(
                chapter_index=int(canonical.group(1)),
                text=raw,
                start=candidate.start(),
                end=candidate.end(),
            )
        )
    return hits


def find_violations(text: str) -> list[str]:
    """扫描正文中全部非规范写法（计违规，不忽略），按出现顺序返回原文片段。"""
    citation_starts = {hit.start for hit in find_citations(text)}
    return [
        candidate.group(0)
        for candidate in _CANDIDATE_RE.finditer(text)
        if candidate.start() not in citation_starts
    ]
