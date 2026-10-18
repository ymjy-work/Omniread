"""查询改写：把带指代的一问改写成能独立成句的一句。

**改写是增强步骤，任何失败都不能阻断问答**：provider 故障、超时、输出不可用一律降级成
原问题，只把 `status` 记成 `failed` 留痕。检索与回答用的都是 `effective`。

四态与契约 `RewriteOutcome.status` 逐字对应，`effective` 无论哪种状态都有值：

- `skipped` —— **没跑**：没开改写、没有历史可消解，或者**根本没配模型**（缺凭据）。
  「没配」与「没历史」在这里归同一态是有理由的：对消费方来说都是「这一步不存在」，
  而「有帧 ⟺ 跑了」这条规则要求 skipped 不发帧——没跑却发一帧说「我没跑」是自相矛盾。
- `unchanged` —— 跑了，模型判定原问题已能独立成句。
- `rewritten` —— 跑了并改了。
- `failed` —— 跑了但坏了，已降级成原问题。**不静默吞掉**：降级是允许的，但要留痕。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from omniread.domain.models import QueryRequest
from omniread.infrastructure.providers.base import ChatModel, ChatOptions
from omniread.infrastructure.providers.errors import ProviderError
from omniread.pipelines.rewriting.prompt import (
    RewritePrompt,
    build_rewrite_messages,
    rewrite_prompt_version,
)

logger = logging.getLogger(__name__)

# 改写要的是**尽量确定**的输出：同一段历史同一个问题，两次跑应当得到同一句。
REWRITE_TEMPERATURE = 0.0

# 输出的长度上界。用契约里 `question` 的上界（2000）：一句比「问题」还长的东西
# 已经不是问题了，拿它去检索只会把召回带偏。
MAX_REWRITE_LENGTH = 2000


class RewriteStatus(StrEnum):
    """与契约 `RewriteOutcome.status` 的四态逐字对应。"""

    REWRITTEN = "rewritten"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RewriteResult:
    """一次改写的结果。字段与契约的 `RewriteOutcome` 一一对应。"""

    status: RewriteStatus
    original: str
    effective: str


def skipped(question: str) -> RewriteResult:
    """没跑：`effective` 就是原问题，不是空串。"""
    return RewriteResult(RewriteStatus.SKIPPED, question, question)


class QueryRewriter:
    """改写器。`chat=None` 表示没配模型（缺凭据），此时一切都落 `skipped`。"""

    def __init__(
        self,
        chat: ChatModel | None,
        *,
        prompt: RewritePrompt | None = None,
        max_length: int = MAX_REWRITE_LENGTH,
    ) -> None:
        self._chat = chat
        self._prompt = prompt
        self._max_length = max_length

    async def rewrite(self, request: QueryRequest) -> RewriteResult:
        original = request.question
        if self._chat is None or not request.rewrite or not request.history:
            return skipped(original)

        try:
            response = await self._chat.complete(
                build_rewrite_messages(request.history, original, prompt=self._prompt),
                ChatOptions(temperature=REWRITE_TEMPERATURE),
            )
        except ProviderError as exc:
            # 降级但不静默：日志里只记结论与原因，**不记问题原文**（审计口径不记问答全文）。
            logger.warning("查询改写降级为原问题：%s", exc)
            return RewriteResult(RewriteStatus.FAILED, original, original)

        effective = _first_nonempty_line(response.text)
        if not effective or len(effective) > self._max_length:
            logger.warning(
                "查询改写输出不可用，降级为原问题：长度 %d（模板版本 %s）",
                len(response.text),
                rewrite_prompt_version(),
            )
            return RewriteResult(RewriteStatus.FAILED, original, original)

        if effective == original:
            return RewriteResult(RewriteStatus.UNCHANGED, original, original)
        logger.info(
            "查询改写完成：%d 字 -> %d 字（模板版本 %s）",
            len(original),
            len(effective),
            rewrite_prompt_version(),
        )
        return RewriteResult(RewriteStatus.REWRITTEN, original, effective)


class FakeQueryRewriter(QueryRewriter):
    """联调/测试专用：**永远返回 `unchanged`**（原问题原样，但状态是「跑了」）。

    为什么不让它走 `FakeChatModel`：那会把一句固定的假回答当成 standalone 问题送进检索，
    排名是确定性噪声（同「假 provider 有毒」那条）。为什么不是 `skipped`：
    联调要验的正是**带帧那条路**——skipped 不发帧，拿它联调等于没接。
    """

    def __init__(self) -> None:
        super().__init__(chat=None)

    async def rewrite(self, request: QueryRequest) -> RewriteResult:
        if not request.rewrite or not request.history:
            return skipped(request.question)
        return RewriteResult(RewriteStatus.UNCHANGED, request.question, request.question)


def _first_nonempty_line(text: str) -> str:
    """取第一行非空内容并去掉首尾空白。

    prompt 要求只输出一句，但模型偶尔会多给几行——多行直接判 `failed` 会把一次可用的
    改写丢掉，而取第一行最坏也只是带上一句多余的修饰（那在 meta 里看得见）。
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


__all__ = [
    "MAX_REWRITE_LENGTH",
    "REWRITE_TEMPERATURE",
    "FakeQueryRewriter",
    "QueryRewriter",
    "RewriteResult",
    "RewriteStatus",
    "skipped",
]
