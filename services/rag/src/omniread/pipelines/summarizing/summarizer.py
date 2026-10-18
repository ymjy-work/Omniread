"""会话摘要：把一段对话压成能替代原文的一段话。

**失败即抛，不吞**。与改写不同，摘要没有「降级」这个选项——契约把它的响应定成
`{summary, prompt_version}`，两个字段都 required，没有「这次不摘要」的取值。
所以 provider 故障、超时、输出不可用一律往上抛，由端点写成 502 / 504；
Java 那边收到失败就**什么都不动**（不推进 `summary_upto`），下次可重试且不会重复压缩。

**不在用户请求链路上**：由 Java 按阈值在后台触发，慢几秒不影响用户等待。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from omniread.domain.models import HistoryMessage
from omniread.infrastructure.providers.base import ChatModel, ChatOptions
from omniread.infrastructure.providers.errors import ProviderResponseError
from omniread.pipelines.summarizing.prompt import (
    SummarizePrompt,
    build_summarize_messages,
    summarize_prompt_version,
)

logger = logging.getLogger(__name__)

# 摘要要的是**稳定**的输出：同一段对话压两次应当得到同一份摘要。
# 与改写同理（`rewriting.REWRITE_TEMPERATURE`），但这里更硬：摘要是长期留在会话里的状态，
# 两次跑出两份不同的摘要会让「同一段历史」的说法在库里对不上。
SUMMARIZE_TEMPERATURE = 0.0

_PROVIDER_NAME = "deepseek"


class SessionSummarizer:
    """摘要器。`chat=None` 表示没配模型——这条链上那是**未接线**（503），不是降级。"""

    def __init__(self, chat: ChatModel | None, *, prompt: SummarizePrompt | None = None) -> None:
        self._chat = chat
        self._prompt = prompt

    @property
    def configured(self) -> bool:
        return self._chat is not None

    async def summarize(
        self, previous_summary: str | None, messages: Sequence[HistoryMessage]
    ) -> tuple[str, str]:
        """返回 `(摘要正文, 模板版本)`。失败抛 `ProviderError` 子类。"""
        if self._chat is None:
            # 组装处不会造出这种实例（未接线时 app.state 上是 None，端点直接 503），
            # 走到这里说明有人绕过了那条路——当场说清楚，别让它变成一次空摘要。
            raise ProviderResponseError("摘要模型未接线", provider=_PROVIDER_NAME)

        response = await self._chat.complete(
            build_summarize_messages(previous_summary, messages, prompt=self._prompt),
            ChatOptions(temperature=SUMMARIZE_TEMPERATURE),
        )
        summary = response.text.strip()
        if not summary:
            # 契约的 `summary` 有 `minLength: 1`：回一个空串会撞 FastAPI 的响应校验变成 500
            # （契约没声明 500），而静默把空串写进会话会让「关键事实探针」无声失败。
            # 按 provider 响应错误处理——与「provider 故障走 5xx，不伪装成业务结果」同一条口径。
            raise ProviderResponseError("摘要模型返回了空内容", provider=_PROVIDER_NAME)
        return summary, summarize_prompt_version()


class FakeSessionSummarizer(SessionSummarizer):
    """联调/测试专用：返回一段**确定性**文本，不调用任何模型。

    确定性是刻意的：摘要会写进会话、影响后续每一轮的上下文，假实现要是随机的话
    联调时看到的每一次行为都不一样。
    """

    def __init__(self) -> None:
        super().__init__(chat=None)

    @property
    def configured(self) -> bool:
        return True

    async def summarize(
        self, previous_summary: str | None, messages: Sequence[HistoryMessage]
    ) -> tuple[str, str]:
        carried = len(messages) + (1 if previous_summary else 0)
        logger.warning("联调/测试模式：摘要由假实现生成，不调用 DeepSeek")
        return f"（联调摘要）已压缩 {carried} 段内容", summarize_prompt_version()


__all__ = [
    "SUMMARIZE_TEMPERATURE",
    "FakeSessionSummarizer",
    "SessionSummarizer",
]
