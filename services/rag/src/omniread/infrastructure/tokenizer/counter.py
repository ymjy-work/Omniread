"""TokenCounter：token 计数与硬切，口径绑定 Qwen 248k 词表（M0-01 §3）。

`tokenizer_id` 承载词表身份、进 chunk 标识，更换实现即全量 chunk 重算；
运行期实现用 `qwen-tokenizer==0.3.0`（词表内嵌、只依赖已有 `tiktoken`）。
该包返回的是 tiktoken 风格对象：`encode` 给 `list[int]`，不是 HF `tokenizers` 的 `Encoding`。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from qwen_tokenizer import get_tokenizer

# 词表身份，不是实现库版本：`实现名:编码/模型名:版本`（M0-01 §3.2），不掺误差值。
TOKENIZER_ID = "tokenizers:Qwen/Qwen3.6-27B:6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"

# qwen-tokenizer 内置词表别名，对应 TOKENIZER_ID 里的 revision。
_QWEN_VARIANT = "qwen3.6-27b"


@lru_cache(maxsize=1)
def _load_tokenizer() -> Any:
    """加载并缓存 tokenizer：要读内嵌词表，进程内只做一次。"""
    return get_tokenizer(_QWEN_VARIANT)


class TokenCounter:
    """token 计数与硬切，口径绑定 `TOKENIZER_ID`。"""

    __slots__ = ("_tokenizer", "tokenizer_id")

    def __init__(self) -> None:
        self.tokenizer_id = TOKENIZER_ID
        self._tokenizer = _load_tokenizer()

    def count(self, text: str) -> int:
        """文本的 token 数。"""
        return len(self._tokenizer.encode(text))

    def split_to_limit(self, text: str, limit: int) -> list[str]:
        """把文本硬切成若干片。

        保证 `"".join(pieces) == text`（不丢字）且每片 `count(piece) <= limit`。
        按字符窗口切、不按 token 边界解码：token 边界可能落在多字节字符中间，
        直接 decode 会产生替换字符而丢字。窗口用二分定位「最长且不超 limit」的边界。
        """
        if limit <= 0:
            raise ValueError("limit 必须为正整数")
        if not text:
            return []
        if self.count(text) <= limit:
            return [text]
        pieces: list[str] = []
        text_end = len(text)
        start = 0
        while start < text_end:
            if self.count(text[start:]) <= limit:
                pieces.append(text[start:])
                break
            low, high = start + 1, text_end
            while low < high:
                middle = (low + high + 1) // 2
                if self.count(text[start:middle]) <= limit:
                    low = middle
                else:
                    high = middle - 1
            pieces.append(text[start:low])
            start = low
        return pieces

    def tail(self, text: str, tokens: int) -> str:
        """文本末尾「最多 tokens 个 token」的窗口；不足 tokens 时返回全文。

        同样按字符边界取整，避免多字节字符被切坏。
        """
        if tokens <= 0 or not text:
            return ""
        if self.count(text) <= tokens:
            return text
        low, high = 1, len(text)
        while low < high:
            middle = (low + high) // 2
            if self.count(text[middle:]) <= tokens:
                high = middle
            else:
                low = middle + 1
        return text[low:]


@lru_cache(maxsize=1)
def get_token_counter() -> TokenCounter:
    """进程内单例：tokenizer 构造代价高，重复构造没有收益。"""
    return TokenCounter()
