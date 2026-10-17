"""查询改写：四态、降级规则、prompt 组装与版本。"""

from __future__ import annotations

import pytest

from omniread.domain.models import HistoryMessage, QueryRequest, RealmLevel
from omniread.infrastructure.providers.base import (
    ChatChunk,
    ChatMessage,
    ChatOptions,
    ChatResponse,
)
from omniread.infrastructure.providers.errors import ProviderTimeoutError
from omniread.pipelines.rewriting import (
    FakeQueryRewriter,
    QueryRewriter,
    RewriteStatus,
    build_rewrite_messages,
    load_rewrite_prompt,
    parse_rewrite_prompt,
    prompt_version,
    read_rewrite_template,
    rewrite_prompt_version,
)

HISTORY = (
    HistoryMessage(role="user", content="政近为什么离开周防家？"),
    HistoryMessage(role="assistant", content="因为家里出了事[C17]。"),
)

QUESTION = "那她后来呢？"


class StubChat:
    """只回一句话的假模型；记录每次收到的消息与选项。"""

    model = "stub-model"

    def __init__(self, text: str = "", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[tuple[list[ChatMessage], ChatOptions | None]] = []

    async def complete(
        self, messages, options: ChatOptions | None = None
    ) -> ChatResponse:
        self.calls.append((list(messages), options))
        if self.error is not None:
            raise self.error
        return ChatResponse(text=self.text, model=self.model)

    async def stream(self, messages, options: ChatOptions | None = None):
        yield ChatChunk(text=self.text)


def request(
    *,
    question: str = QUESTION,
    rewrite: bool = True,
    history: tuple[HistoryMessage, ...] = HISTORY,
) -> QueryRequest:
    return QueryRequest(
        book_id=1,
        question=question,
        level=RealmLevel.FULL,
        rewrite=rewrite,
        history=history,
    )


# ── 没跑的三种情形都归 skipped ──


@pytest.mark.parametrize(
    "kwargs",
    [
        {"history": ()},  # 没有历史可消解指代
        {"rewrite": False},  # 调用方关掉了
    ],
)
async def test_not_running_is_skipped(kwargs: dict) -> None:
    chat = StubChat(text="改过的")
    result = await QueryRewriter(chat).rewrite(request(**kwargs))

    assert result.status is RewriteStatus.SKIPPED
    assert result.effective == QUESTION
    assert chat.calls == [], "skipped 就不该调用模型"


async def test_missing_model_is_skipped() -> None:
    """缺凭据（没配模型）也是 skipped：对消费方来说都是「这一步不存在」。"""
    result = await QueryRewriter(None).rewrite(request())

    assert result.status is RewriteStatus.SKIPPED
    assert result.effective == QUESTION


# ── 跑了以后的三种结果 ──


async def test_changed_question_is_rewritten() -> None:
    chat = StubChat(text="周防家的女儿后来怎么样了？")
    result = await QueryRewriter(chat).rewrite(request())

    assert result.status is RewriteStatus.REWRITTEN
    assert result.original == QUESTION
    assert result.effective == "周防家的女儿后来怎么样了？"
    # 确定性输出：temperature 显式给 0，不靠 provider 的默认值。
    assert chat.calls[0][1] == ChatOptions(temperature=0.0)


async def test_same_question_is_unchanged() -> None:
    result = await QueryRewriter(StubChat(text=QUESTION)).rewrite(request())

    assert result.status is RewriteStatus.UNCHANGED
    assert result.effective == QUESTION


async def test_provider_failure_degrades_to_failed() -> None:
    chat = StubChat(error=ProviderTimeoutError("改写超时", provider="deepseek"))
    result = await QueryRewriter(chat).rewrite(request())

    assert result.status is RewriteStatus.FAILED
    assert result.effective == QUESTION
    # 降级是允许的，**但不静默**：状态本身留痕，无帧规则也要求 failed 发帧。
    assert result.status is not RewriteStatus.SKIPPED


@pytest.mark.parametrize("text", ["", "   \n  \n", "x" * 2001])
async def test_unusable_output_degrades_to_failed(text: str) -> None:
    result = await QueryRewriter(StubChat(text=text)).rewrite(request())

    assert result.status is RewriteStatus.FAILED
    assert result.effective == QUESTION


async def test_multiline_output_takes_the_first_line() -> None:
    """模型偶尔多给几行；整段判 failed 会丢掉一次可用的改写。"""
    result = await QueryRewriter(StubChat(text="\n改过的问句\n\n说明一句\n")).rewrite(request())

    assert result.status is RewriteStatus.REWRITTEN
    assert result.effective == "改过的问句"


# ── 假实现：联调要验的是「带帧那条路」 ──


async def test_fake_rewriter_reports_unchanged_with_history() -> None:
    result = await FakeQueryRewriter().rewrite(request())

    assert result.status is RewriteStatus.UNCHANGED
    assert result.effective == QUESTION


async def test_fake_rewriter_skips_without_history() -> None:
    result = await FakeQueryRewriter().rewrite(request(history=()))

    assert result.status is RewriteStatus.SKIPPED


# ── prompt ──


def test_history_and_question_land_in_the_user_message() -> None:
    messages = build_rewrite_messages(HISTORY, QUESTION)
    system, user = messages

    assert system.role == "system"
    assert user.role == "user"
    assert "【用户】政近为什么离开周防家？" in user.content
    assert "【助手】因为家里出了事[C17]。" in user.content
    assert QUESTION in user.content
    assert "{{HISTORY}}" not in user.content
    assert "{{QUESTION}}" not in user.content
    # 历史按时间顺序：先问后答。
    assert user.content.index("政近为什么") < user.content.index("因为家里出了事")


def test_system_message_carries_the_disciplines() -> None:
    system = load_rewrite_prompt().system

    assert "保留用户当前问题的核心意图" in system
    assert "不得擅自增加用户没有提出的要求" in system
    assert "不得补充历史中不存在的事实" in system


def test_prompt_version_is_the_short_hash_of_the_template() -> None:
    assert rewrite_prompt_version() == prompt_version(read_rewrite_template())
    assert len(rewrite_prompt_version()) == 12


def test_parse_rejects_missing_section_or_placeholder() -> None:
    with pytest.raises(ValueError):
        parse_rewrite_prompt("<user>\n{{HISTORY}} {{QUESTION}}\n</user>")
    with pytest.raises(ValueError):
        parse_rewrite_prompt("<system>规则</system>\n<user>只有历史没有占位符</user>")
