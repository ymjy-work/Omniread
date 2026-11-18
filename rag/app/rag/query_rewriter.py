import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    trim_messages,
)

from app.config.settings import settings
from app.schemas import HistoryMessage

logger = logging.getLogger(__name__)

QUERY_REWRITE_PLACEHOLDER = "[QUERY_REWRITE_PROMPT_PLACEHOLDER]"


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item
            if isinstance(item, str)
            else item.get("text", "")
            if isinstance(item, dict)
            else ""
            for item in content
        )
    return str(content)


class QueryRewriter:
    def __init__(self, model: Any | None = None) -> None:
        self._model = model

    def _get_model(self) -> Any:
        if self._model is None:
            from langchain_openai import ChatOpenAI

            self._model = ChatOpenAI(
                base_url=settings.bailian_base_url,
                api_key=settings.bailian_api_key,
                model=settings.chat_model,
                temperature=0,
            )
        return self._model

    async def rewrite(
        self, question: str, history: list[HistoryMessage]
    ) -> str:
        if not history:
            return question
        if not settings.bailian_api_key and self._model is None:
            logger.warning("BAILIAN_API_KEY is not configured; using original question")
            return question

        history_messages: list[BaseMessage] = [
            HumanMessage(content=item.content)
            if item.role == "user"
            else AIMessage(content=item.content)
            for item in history
        ]
        trimmed = trim_messages(
            history_messages,
            max_tokens=2000,
            token_counter="approximate",
            strategy="last",
            include_system=False,
            allow_partial=False,
        )
        prompt = (
            f"{QUERY_REWRITE_PLACEHOLDER}\n\n"
            f"问题：{question}\n"
            "输出："
        )
        try:
            response = await self._get_model().ainvoke(
                [*trimmed, HumanMessage(content=prompt)]
            )
            rewritten = _content_to_text(response.content).strip()
            return rewritten or question
        except Exception as exc:  # noqa: BLE001
            logger.warning("query rewrite failed; using original question: %s", exc)
            return question
