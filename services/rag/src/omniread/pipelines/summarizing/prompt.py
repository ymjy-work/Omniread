"""摘要 prompt：模板资源、消息组装与 `prompt_version`。

规则与另外两条 prompt 同一套（见 `pipelines/prompting`）：模板是仓库内文件，
`{{PREVIOUS}}` / `{{MESSAGES}}` 是仅有的替换点，版本 = 模板原文与**渲染格式常量**
一起取 sha256 前 12 位。

这条的版本号**有上报通道**（不像改写）：契约的 `SummarizeResponse.prompt_version` 就是
给它留的，Java 会把它写进 `chat_sessions.summary_prompt_version`——摘要长期留在会话里，
模板改了之后库里的老摘要得能分辨出自哪一版。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from omniread.domain.models import HistoryMessage
from omniread.domain.text import sha256_hex
from omniread.infrastructure.providers.base import ChatMessage
from omniread.pipelines.prompting import (
    DIALOGUE_LINE,
    DIALOGUE_SEPARATOR,
    EMPTY_DIALOGUE,
    SPEAKER_ASSISTANT,
    SPEAKER_USER,
    VERSION_INPUT_SEPARATOR,
    render_dialogue,
)

PROMPT_VERSION_LENGTH = 12

_RESOURCE_PACKAGE = "omniread.pipelines.summarizing"
_RESOURCE_NAME = "prompts/summarize.md"

SECTION_SYSTEM = "system"
SECTION_USER = "user"

# 首次摘要时的占位句，与「已有摘要」的块头。两者都是**模型可见文本**，
# 所以与对话渲染常量一起进 `prompt_version` 的输入。
_NO_PREVIOUS = "（这是第一次摘要，前面没有更早的内容）"
_PREVIOUS_HEADER = "已有摘要（请把它一起吸收进来）："


@dataclass(frozen=True, slots=True)
class SummarizePrompt:
    """一份解析后的摘要 prompt 模板。`text` 是模板文件原文，版本由它派生。"""

    text: str
    system: str
    user_template: str

    @property
    def version(self) -> str:
        return prompt_version(self.text)

    def render_user(
        self, previous_summary: str | None, messages: Sequence[HistoryMessage]
    ) -> str:
        return self.user_template.replace(
            "{{PREVIOUS}}", render_previous(previous_summary)
        ).replace("{{MESSAGES}}", render_dialogue(messages))

    def build_messages(
        self, previous_summary: str | None, messages: Sequence[HistoryMessage]
    ) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content=self.system),
            ChatMessage(
                role="user", content=self.render_user(previous_summary, messages)
            ),
        ]


def prompt_version(template_text: str) -> str:
    """模板原文**与渲染格式常量**一起取 sha256 前 12 位。"""
    payload = VERSION_INPUT_SEPARATOR.join(
        (
            template_text,
            DIALOGUE_LINE,
            SPEAKER_USER,
            SPEAKER_ASSISTANT,
            DIALOGUE_SEPARATOR,
            EMPTY_DIALOGUE,
            _NO_PREVIOUS,
            _PREVIOUS_HEADER,
        )
    )
    return sha256_hex(payload)[:PROMPT_VERSION_LENGTH]


def render_previous(previous_summary: str | None) -> str:
    """渲染「已有摘要」那一段。

    **空串按「没有」处理**：契约说首次摘要传 null、不要传空串，但真收到空串时
    渲染成一个空的「已有摘要：」块会让模型以为前面有一段空白历史——按「没有」处理更安全。
    """
    if not previous_summary:
        return _NO_PREVIOUS
    return f"{_PREVIOUS_HEADER}\n{previous_summary}"


def parse_summarize_prompt(text: str) -> SummarizePrompt:
    """按标记行切分模板；缺段或缺占位符即失败，不静默降级。"""
    system = _extract_section(text, SECTION_SYSTEM)
    user_template = _extract_section(text, SECTION_USER)
    if "{{PREVIOUS}}" not in user_template or "{{MESSAGES}}" not in user_template:
        raise ValueError("摘要 prompt 模板缺少 {{PREVIOUS}} 或 {{MESSAGES}} 占位符")
    return SummarizePrompt(text=text, system=system, user_template=user_template)


def read_summarize_template() -> str:
    """读模板文件原文（未缓存）：`prompt_version` 与解析都以它为准。"""
    resource = resources.files(_RESOURCE_PACKAGE).joinpath(_RESOURCE_NAME)
    return resource.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_summarize_prompt() -> SummarizePrompt:
    """加载并解析模板；进程内只读一次文件。"""
    return parse_summarize_prompt(read_summarize_template())


def summarize_prompt_version() -> str:
    """当前摘要 prompt 的版本，写进 `SummarizeResponse.prompt_version`。"""
    return load_summarize_prompt().version


def build_summarize_messages(
    previous_summary: str | None,
    messages: Sequence[HistoryMessage],
    *,
    prompt: SummarizePrompt | None = None,
) -> list[ChatMessage]:
    """组装送给摘要模型的 system / user 两条消息。"""
    return (prompt or load_summarize_prompt()).build_messages(previous_summary, messages)


def _extract_section(text: str, name: str) -> str:
    opening = f"<{name}>"
    closing = f"</{name}>"
    start = text.find(opening)
    if start < 0:
        raise ValueError(f"摘要 prompt 模板缺少 {opening} 段")
    end = text.find(closing, start + len(opening))
    if end < 0:
        raise ValueError(f"摘要 prompt 模板缺少 {closing} 段")
    return text[start + len(opening) : end].strip()


__all__ = [
    "PROMPT_VERSION_LENGTH",
    "SummarizePrompt",
    "build_summarize_messages",
    "load_summarize_prompt",
    "parse_summarize_prompt",
    "prompt_version",
    "read_summarize_template",
    "render_previous",
    "summarize_prompt_version",
]
