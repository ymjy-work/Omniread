"""改写 prompt：模板资源、消息组装与 `prompt_version`。

规则与 `answering/prompt.py` 同一套：模板是**仓库内文件** `prompts/rewrite.md`，
两个标记行切成 system / user 两段，`{{HISTORY}}` / `{{QUESTION}}` 是仅有的替换点；
`prompt_version` = 模板原文**与渲染格式常量**一起取 sha256 前 12 位——历史那几行
（说话人标签、行分隔）同样是模型可见文本，只算模板会让「改了格式却不换版本」成立。

**这个版本号目前没有上报通道**：契约的 `RewriteOutcome` 只有
`status` / `original` / `effective` 三个字段，没有地方放它。所以它只用于日志与
「模板一改版本就变」这条不变量测试。要真正上报得改契约（走单向门），本阶段不做。
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

_RESOURCE_PACKAGE = "omniread.pipelines.rewriting"
_RESOURCE_NAME = "prompts/rewrite.md"

SECTION_SYSTEM = "system"
SECTION_USER = "user"


@dataclass(frozen=True, slots=True)
class RewritePrompt:
    """一份解析后的改写 prompt 模板。`text` 是模板文件原文，版本由它派生。"""

    text: str
    system: str
    user_template: str

    @property
    def version(self) -> str:
        return prompt_version(self.text)

    def render_user(self, history: Sequence[HistoryMessage], question: str) -> str:
        return self.user_template.replace("{{HISTORY}}", render_history(history)).replace(
            "{{QUESTION}}", question
        )

    def build_messages(
        self, history: Sequence[HistoryMessage], question: str
    ) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content=self.system),
            ChatMessage(role="user", content=self.render_user(history, question)),
        ]


def prompt_version(template_text: str) -> str:
    """模板原文**与渲染格式常量**一起取 sha256 前 12 位（判据同 answering）。

    渲染常量来自 `pipelines/prompting`——与摘要共用同一份，所以那个格式变了两个版本一起变。
    """
    payload = VERSION_INPUT_SEPARATOR.join(
        (
            template_text,
            DIALOGUE_LINE,
            SPEAKER_USER,
            SPEAKER_ASSISTANT,
            DIALOGUE_SEPARATOR,
            EMPTY_DIALOGUE,
        )
    )
    return sha256_hex(payload)[:PROMPT_VERSION_LENGTH]


def render_history(history: Sequence[HistoryMessage]) -> str:
    """按时间顺序渲染历史（共用实现，见 `pipelines/prompting`）。"""
    return render_dialogue(history)


def parse_rewrite_prompt(text: str) -> RewritePrompt:
    """按标记行切分模板；缺段或缺占位符即失败，不静默降级。"""
    system = _extract_section(text, SECTION_SYSTEM)
    user_template = _extract_section(text, SECTION_USER)
    if "{{HISTORY}}" not in user_template or "{{QUESTION}}" not in user_template:
        raise ValueError("改写 prompt 模板缺少 {{HISTORY}} 或 {{QUESTION}} 占位符")
    return RewritePrompt(text=text, system=system, user_template=user_template)


def read_rewrite_template() -> str:
    """读模板文件原文（未缓存）：`prompt_version` 与解析都以它为准。"""
    resource = resources.files(_RESOURCE_PACKAGE).joinpath(_RESOURCE_NAME)
    return resource.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_rewrite_prompt() -> RewritePrompt:
    """加载并解析模板；进程内只读一次文件。"""
    return parse_rewrite_prompt(read_rewrite_template())


def rewrite_prompt_version() -> str:
    """当前改写 prompt 的版本。**暂无上报通道**，见模块 docstring。"""
    return load_rewrite_prompt().version


def build_rewrite_messages(
    history: Sequence[HistoryMessage],
    question: str,
    *,
    prompt: RewritePrompt | None = None,
) -> list[ChatMessage]:
    """组装送给改写模型的 system / user 两条消息。"""
    return (prompt or load_rewrite_prompt()).build_messages(history, question)


def _extract_section(text: str, name: str) -> str:
    opening = f"<{name}>"
    closing = f"</{name}>"
    start = text.find(opening)
    if start < 0:
        raise ValueError(f"改写 prompt 模板缺少 {opening} 段")
    end = text.find(closing, start + len(opening))
    if end < 0:
        raise ValueError(f"改写 prompt 模板缺少 {closing} 段")
    return text[start + len(opening) : end].strip()


__all__ = [
    "PROMPT_VERSION_LENGTH",
    "RewritePrompt",
    "build_rewrite_messages",
    "load_rewrite_prompt",
    "parse_rewrite_prompt",
    "prompt_version",
    "read_rewrite_template",
    "render_history",
    "rewrite_prompt_version",
]
