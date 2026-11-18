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

QUERY_REWRITE_PLACEHOLDER = (
    "你是检索查询改写器。请结合对话历史，把用户的最新问题改写成一条独立、完整、便于检索的查询，"
    "用于在小说原文中查找相关段落。\n\n"
    "要求：\n"
    "1. 补全历史中的指代：把「他」「她」「那个人」「那里」等替换为对话中明确的人名、昵称或对象；"
    "保留原问题中出现的人名、昵称、地名和关键情节词，不要改成同义说法。\n"
    "2. 保持原问题的意图与范围，只补充理解问题所必需的历史信息，不添加历史中不存在的内容。\n"
    "3. 不要回答问题，不要解释，不要输出思考过程、引号、编号或任何前缀。\n"
    "4. 只输出改写后的查询本身，一行即可；如果原问题已经独立完整，就原样输出。"
)


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
