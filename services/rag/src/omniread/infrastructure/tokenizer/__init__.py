"""TokenCounter：`count(text)` 与 `split_to_limit(text, limit)`。

口径见 M0-01 §3.2——实现与版本一次定死，`tokenizer_id` 进入 chunk 标识，
更换实现即全量 chunk 重算。
"""

from __future__ import annotations

from omniread.infrastructure.tokenizer.counter import (
    TOKENIZER_ID,
    TokenCounter,
    get_token_counter,
)

__all__ = ["TOKENIZER_ID", "TokenCounter", "get_token_counter"]
