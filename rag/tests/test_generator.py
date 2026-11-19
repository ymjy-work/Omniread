import logging
from typing import Any

import numpy as np
import pytest
from langchain_core.messages import AIMessage

from app.db.models import Chunk
from app.rag.generator import GenerationError, Generator, extract_usage
from app.rag.providers import ChatTarget


def make_chunk() -> Chunk:
    return Chunk(
        id=1,
        book_id=1,
        chapter_id="book:1:chapter:1",
        chapter_index=1,
        title="第一章",
        text="证据",
        vector=np.zeros(2, dtype=np.float32),
    )


class FakeChatModel:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.messages: list[Any] | None = None

    async def ainvoke(self, messages: list[Any]) -> Any:
        self.messages = messages
        return self._response


@pytest.mark.asyncio
async def test_generator_passes_provider_model_and_key() -> None:
    captured: dict[str, str] = {}
    model = FakeChatModel(
        AIMessage(
            content="答案。[[chunk:1]]",
            usage_metadata={
                "input_tokens": 11,
                "output_tokens": 22,
                "total_tokens": 33,
            },
        )
    )

    def factory(**kwargs: str) -> FakeChatModel:
        captured.update(kwargs)
        return model

    generator = Generator(model_factory=factory)
    generation = await generator.generate(
        "问题", [make_chunk()], ChatTarget("openai", "gpt-4o-mini", "sk-user")
    )

    assert captured == {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-user",
    }
    assert generation.answer == "答案。[[chunk:1]]"
    assert generation.cited_ids == [1]
    assert generation.prompt_tokens == 11
    assert generation.completion_tokens == 22
    assert model.messages is not None


@pytest.mark.asyncio
async def test_generator_error_does_not_leak_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def factory(**kwargs: str) -> Any:
        class BrokenModel:
            async def ainvoke(self, messages: list[Any]) -> Any:
                raise RuntimeError(f"auth failed for {kwargs['api_key']}")

        return BrokenModel()

    generator = Generator(model_factory=factory)

    with caplog.at_level(logging.WARNING), pytest.raises(GenerationError) as info:
        await generator.generate(
            "问题",
            [make_chunk()],
            ChatTarget("openai", "gpt-4o-mini", "sk-secret"),
        )

    assert "sk-secret" not in caplog.text
    assert "sk-secret" not in str(info.value)
    assert "[redacted]" in caplog.text


def test_extract_usage_falls_back_to_response_metadata() -> None:
    response = AIMessage(
        content="答案",
        response_metadata={
            "token_usage": {"prompt_tokens": 3, "completion_tokens": 4}
        },
    )

    assert extract_usage(response) == (3, 4)


def test_extract_usage_defaults_to_zero() -> None:
    assert extract_usage(AIMessage(content="答案")) == (0, 0)