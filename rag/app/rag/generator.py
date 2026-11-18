from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage

from app.config.settings import settings
from app.db.models import Chunk
from app.rag.citations import extract_citation_ids
from app.rag.prompt_builder import build_messages


@dataclass(frozen=True, slots=True)
class Generation:
    answer: str
    cited_ids: list[int]


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


class Generator:
    def __init__(self, model: Any | None = None) -> None:
        self._model = model

    def _get_model(self) -> Any:
        if self._model is None:
            from langchain_openai import ChatOpenAI

            self._model = ChatOpenAI(
                base_url=settings.bailian_base_url,
                api_key=settings.bailian_api_key,
                model=settings.chat_model,
                temperature=0.2,
                max_tokens=1024,
                extra_body={"enable_thinking": False},
            )
        return self._model

    async def generate(self, question: str, chunks: list[Chunk]) -> Generation:
        messages: list[BaseMessage] = build_messages(question, chunks)
        response = await self._get_model().ainvoke(messages)
        text = _content_to_text(response.content)
        return Generation(answer=text, cited_ids=extract_citation_ids(text))
