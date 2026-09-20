"""TokenCounter 的单测：计数、硬切不丢字、尾窗与确定性。

`tokenizer_id` 与 600/60 口径是单向门（M0-03 §3），这里钉住常量值与切分契约。
"""

from __future__ import annotations

import pytest

from omniread.infrastructure.tokenizer import (
    TOKENIZER_ID,
    TokenCounter,
    get_token_counter,
)

REPEATED_CN = "我们在验证中文分块计数与硬切行为。"


@pytest.fixture(scope="module")
def counter() -> TokenCounter:
    return get_token_counter()


def test_tokenizer_id_is_frozen_identity(counter: TokenCounter) -> None:
    assert TOKENIZER_ID == (
        "tokenizers:Qwen/Qwen3.6-27B:6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"
    )
    assert counter.tokenizer_id == TOKENIZER_ID


def test_get_token_counter_is_singleton() -> None:
    assert get_token_counter() is get_token_counter()


def test_count_is_positive_and_grows_with_text(counter: TokenCounter) -> None:
    assert counter.count("") == 0
    assert counter.count("艾莉") >= 1
    assert counter.count(REPEATED_CN * 4) > counter.count(REPEATED_CN)


def test_split_to_limit_returns_whole_text_when_within_limit(counter: TokenCounter) -> None:
    text = "短句。"
    assert counter.split_to_limit(text, 600) == [text]
    assert counter.split_to_limit("", 600) == []


def test_split_to_limit_rejects_non_positive_limit(counter: TokenCounter) -> None:
    with pytest.raises(ValueError):
        counter.split_to_limit("文本", 0)


def test_split_to_limit_hard_cuts_long_text_without_losing_characters(
    counter: TokenCounter,
) -> None:
    text = (REPEATED_CN + "这是一段用于硬切验证的长文本，片段之间必须首尾相接。\n") * 40
    assert counter.count(text) > 600

    pieces = counter.split_to_limit(text, 600)

    assert len(pieces) > 1
    assert "".join(pieces) == text
    assert all(counter.count(piece) <= 600 for piece in pieces)
    assert all(piece for piece in pieces)


def test_split_to_limit_is_deterministic(counter: TokenCounter) -> None:
    text = REPEATED_CN * 60
    assert counter.split_to_limit(text, 120) == counter.split_to_limit(text, 120)


def test_tail_returns_suffix_within_budget(counter: TokenCounter) -> None:
    text = REPEATED_CN * 10
    assert counter.count(text) > 60

    window = counter.tail(text, 60)

    assert text.endswith(window)
    assert 0 < counter.count(window) <= 60
    assert window != text


def test_tail_returns_whole_text_when_short_enough(counter: TokenCounter) -> None:
    assert counter.tail("短短一句。", 60) == "短短一句。"
    assert counter.tail("", 60) == ""
    assert counter.tail("文本", 0) == ""
