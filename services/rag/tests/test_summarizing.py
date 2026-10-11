"""会话摘要：模板组装、版本、失败口径与端点行为。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import build_client_with_summarizer
from helpers import REQUEST_ID
from omniread.domain.models import HistoryMessage
from omniread.infrastructure.providers.base import (
    ChatChunk,
    ChatMessage,
    ChatOptions,
    ChatResponse,
)
from omniread.infrastructure.providers.errors import (
    ProviderResponseError,
    ProviderTimeoutError,
)
from omniread.pipelines.summarizing import (
    FakeSessionSummarizer,
    SessionSummarizer,
    build_summarize_messages,
    load_summarize_prompt,
    parse_summarize_prompt,
    prompt_version,
    read_summarize_template,
    render_previous,
    summarize_prompt_version,
)

MESSAGES = (
    HistoryMessage(role="user", content="政近为什么离开周防家？"),
    HistoryMessage(role="assistant", content="因为家里出了事[C17]。"),
)

SUMMARY = "政近因家中变故而离开周防家 [C17]。"


class StubChat:
    model = "stub-model"

    def __init__(self, text: str = SUMMARY, error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[tuple[list[ChatMessage], ChatOptions | None]] = []

    async def complete(self, messages, options: ChatOptions | None = None) -> ChatResponse:
        self.calls.append((list(messages), options))
        if self.error is not None:
            raise self.error
        return ChatResponse(text=self.text, model=self.model)

    async def stream(self, messages, options: ChatOptions | None = None):
        yield ChatChunk(text=self.text)


# ── 正常路径 ──


async def test_summarize_returns_text_and_prompt_version() -> None:
    chat = StubChat()
    summary, version = await SessionSummarizer(chat).summarize(None, MESSAGES)

    assert summary == SUMMARY
    assert version == summarize_prompt_version()
    # 确定性：摘要是长期留在会话里的状态，两次跑出两份不同的摘要会让
    # 「同一段历史」的说法在库里对不上。
    assert chat.calls[0][1] == ChatOptions(temperature=0.0)


async def test_previous_summary_is_absorbed_not_appended() -> None:
    chat = StubChat()
    await SessionSummarizer(chat).summarize("上一次的摘要。", MESSAGES)

    user_message = chat.calls[0][0][1].content
    assert "上一次的摘要。" in user_message
    assert "已有摘要" in user_message
    assert "【用户】政近为什么离开周防家？" in user_message


# ── 失败口径：这条链**没有降级** ──


async def test_empty_output_is_a_provider_error() -> None:
    """契约的 `summary` 有 `minLength: 1`。

    原样回空串会撞 FastAPI 的响应校验变成 500（契约没声明 500），而静默写进会话
    会让「关键事实探针」无声失败。按 provider 响应错误处理。
    """
    with pytest.raises(ProviderResponseError):
        await SessionSummarizer(StubChat(text="   \n  ")).summarize(None, MESSAGES)


async def test_provider_failure_propagates() -> None:
    with pytest.raises(ProviderTimeoutError):
        await SessionSummarizer(
            StubChat(error=ProviderTimeoutError("摘要超时", provider="deepseek"))
        ).summarize(None, MESSAGES)


async def test_unconfigured_summarizer_raises_instead_of_returning_empty() -> None:
    with pytest.raises(ProviderResponseError):
        await SessionSummarizer(None).summarize(None, MESSAGES)


# ── 假实现 ──


async def test_fake_summarizer_is_deterministic() -> None:
    fake = FakeSessionSummarizer()

    first, _ = await fake.summarize(None, MESSAGES)
    second, _ = await fake.summarize(None, MESSAGES)

    assert first == second
    assert fake.configured


# ── prompt ──


def test_render_previous_treats_empty_string_as_absent() -> None:
    """契约说首次摘要传 null、不要传空串；真收到空串也不能渲染成一段空白的「已有摘要」。"""
    assert render_previous(None) == render_previous("")
    assert "已有摘要" not in render_previous("")
    assert "已有摘要" in render_previous("上一次的。")


def test_messages_and_question_land_in_the_user_message() -> None:
    system, user = build_summarize_messages(None, MESSAGES)

    assert system.role == "system"
    assert "【用户】政近为什么离开周防家？" in user.content
    assert "【助手】因为家里出了事[C17]。" in user.content
    assert "{{MESSAGES}}" not in user.content
    assert "{{PREVIOUS}}" not in user.content


def test_system_message_carries_the_disciplines() -> None:
    system = load_summarize_prompt().system

    assert "保留事实与约束" in system
    assert "不得引入输入里没有出现过" in system


def test_prompt_version_is_the_short_hash_of_the_template() -> None:
    assert summarize_prompt_version() == prompt_version(read_summarize_template())
    assert len(summarize_prompt_version()) == 12


def test_parse_rejects_missing_section_or_placeholder() -> None:
    with pytest.raises(ValueError):
        parse_summarize_prompt("<user>\n{{PREVIOUS}} {{MESSAGES}}\n</user>")
    with pytest.raises(ValueError):
        parse_summarize_prompt("<system>规则</system>\n<user>只有历史没有占位符</user>")


# ── 端点 ──


def test_endpoint_returns_summary_and_version(image_root: Path) -> None:
    client: TestClient = build_client_with_summarizer(image_root, SessionSummarizer(StubChat()))

    response = client.post(
        "/internal/v1/summarize",
        json={
            "previous_summary": None,
            "messages": [
                {"role": "user", "content": "政近为什么离开周防家？"},
                {"role": "assistant", "content": "因为家里出了事[C17]。"},
            ],
        },
        headers={"X-Request-Id": REQUEST_ID},
    )

    assert response.status_code == 200
    assert response.json() == {"summary": SUMMARY, "prompt_version": summarize_prompt_version()}


def test_endpoint_rejects_empty_messages(image_root: Path) -> None:
    """契约的 `messages` 有 `minItems: 1`：没有待压缩的内容时不该调模型。"""
    client: TestClient = build_client_with_summarizer(image_root, SessionSummarizer(StubChat()))

    response = client.post("/internal/v1/summarize", json={"messages": []})

    assert response.status_code == 400
    assert response.json()["code"] == "RAG_INVALID_REQUEST"


def test_endpoint_maps_provider_timeout_to_504(image_root: Path) -> None:
    failing = SessionSummarizer(
        StubChat(error=ProviderTimeoutError("超时", provider="deepseek"))
    )
    client: TestClient = build_client_with_summarizer(image_root, failing)

    response = client.post(
        "/internal/v1/summarize",
        json={"messages": [{"role": "user", "content": "问"}]},
    )

    assert response.status_code == 504
    assert response.json()["code"] == "RAG_TIMEOUT"


def test_error_body_is_the_flat_shape(image_root: Path) -> None:
    client: TestClient = build_client_with_summarizer(image_root, SessionSummarizer(StubChat()))

    body = client.post("/internal/v1/summarize", json={"messages": []}).json()

    assert set(body) == {"request_id", "code", "message"}
    assert json.dumps(body, ensure_ascii=False)
