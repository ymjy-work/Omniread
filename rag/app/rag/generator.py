import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage

from app.db.models import Chunk
from app.rag.citations import extract_citation_ids
from app.rag.prompt_builder import build_messages
from app.rag.providers import ChatTarget, build_chat_model, redact_secrets

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Generation:
    answer: str
    cited_ids: list[int]
    prompt_tokens: int = 0
    completion_tokens: int = 0


class GenerationError(RuntimeError):
    pass


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return str(content)


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def extract_usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage_metadata", None) or {}
    prompt_tokens = usage.get("input_tokens")
    completion_tokens = usage.get("output_tokens")
    if prompt_tokens is None or completion_tokens is None:
        metadata = getattr(response, "response_metadata", None) or {}
        token_usage = metadata.get("token_usage") or metadata.get("usage") or {}
        if prompt_tokens is None:
            prompt_tokens = token_usage.get("prompt_tokens")
        if completion_tokens is None:
            completion_tokens = token_usage.get("completion_tokens")
    return _to_int(prompt_tokens), _to_int(completion_tokens)


class Generator:
    def __init__(
        self,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._model_factory = model_factory or build_chat_model

    async def generate(
        self, question: str, chunks: list[Chunk], target: ChatTarget
    ) -> Generation:
        messages: list[BaseMessage] = build_messages(question, chunks)
        try:
            model = self._model_factory(
                provider=target.provider,
                model=target.model,
                api_key=target.api_key,
            )
            response = await model.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "generation failed provider=%s model=%s: %s",
                target.provider,
                target.model,
                redact_secrets(str(exc), target.api_key),
            )
            raise GenerationError(
                f"generation failed: {target.provider}/{target.model}"
            ) from None

        text = _content_to_text(response.content)
        prompt_tokens, completion_tokens = extract_usage(response)
        return Generation(
            answer=text,
            cited_ids=extract_citation_ids(text),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )