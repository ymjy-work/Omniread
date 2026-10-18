"""裁判 prompt：模板资源、消息组装与 `prompt_version`。

**这是第四份提示词资产，且是唯一不在请求路径上的一份**：回答、改写、摘要都挂在
线上链路里，裁判只在评测里跑。它补的是确定性指标
看不到的那一类错——两段引用都在装配集内、各自都不假，错在语义关系（把第 9 章的
备品采买与第 18 章的买饮料焊成一条时间线）。

规则与 `answering/prompt.py` 同一套：模板是仓库内文件 `prompts/judge.md`，
两个标记行切成 system / user 两段，`{{CONTEXT}}` / `{{QUESTION}}` / `{{ANSWER}}`
是仅有的替换点；`prompt_version` = 模板原文**与渲染格式常量**一起取 sha256 前 12 位。

材料段的渲染**复用 `answering` 的定义**（`render_context` 与
`render_format_constants`），不另写一份：裁判判的是「模型当时看到的材料」，
段头格式各写一份就会漂，漂了之后判定不再描述当时那个 prompt。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from omniread.domain.text import sha256_hex
from omniread.infrastructure.providers.base import ChatMessage
from omniread.pipelines.answering.prompt import (
    ContextPassage,
    render_context,
    render_format_constants,
)
from omniread.pipelines.prompting import VERSION_INPUT_SEPARATOR

# 与另外三份文件型模板同一个口径（sha256 前 12 位）。
PROMPT_VERSION_LENGTH = 12

_RESOURCE_PACKAGE = "omniread.pipelines.judging"
_RESOURCE_NAME = "prompts/judge.md"

SECTION_SYSTEM = "system"
SECTION_USER = "user"

#: user 段必须同时带这三个占位符：裁判要判「这个答案有没有被这些材料支持」，
#: 少任何一个，判据就不再是「对照材料」。
_REQUIRED_PLACEHOLDERS = ("{{CONTEXT}}", "{{QUESTION}}", "{{ANSWER}}")


@dataclass(frozen=True, slots=True)
class JudgePrompt:
    """一份解析后的裁判 prompt 模板。`text` 是模板文件原文，版本由它派生。"""

    text: str
    system: str
    user_template: str

    @property
    def version(self) -> str:
        return prompt_version(self.text)

    def render_user(
        self, question: str, passages: Sequence[ContextPassage], answer: str
    ) -> str:
        """渲染 user 消息：材料 → 问题 → 待评估答案。

        `{{ANSWER}}` 放在最后替换：答案本身是模型输出，若先替换它，答案里出现的
        `{{QUESTION}}` 这类字面量会被后一趟再替换一遍。
        """
        return (
            self.user_template.replace("{{CONTEXT}}", render_context(passages))
            .replace("{{QUESTION}}", question)
            .replace("{{ANSWER}}", answer)
        )

    def build_messages(
        self, question: str, passages: Sequence[ContextPassage], answer: str
    ) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content=self.system),
            ChatMessage(role="user", content=self.render_user(question, passages, answer)),
        ]


def prompt_version(template_text: str) -> str:
    """模板原文**与材料段渲染格式常量**一起取 sha256 前 12 位。

    格式常量从 `answering.prompt` 取，与回答那一份**是同一个定义**——裁判看的
    就是回答看过的那批材料段，两份版本必须同进同退。
    """
    payload = VERSION_INPUT_SEPARATOR.join(
        (template_text, *render_format_constants())
    )
    return sha256_hex(payload)[:PROMPT_VERSION_LENGTH]


def parse_judge_prompt(text: str) -> JudgePrompt:
    """按标记行切分模板；缺段或缺占位符即失败，不静默降级。"""
    system = _extract_section(text, SECTION_SYSTEM)
    user_template = _extract_section(text, SECTION_USER)
    missing = [token for token in _REQUIRED_PLACEHOLDERS if token not in user_template]
    if missing:
        raise ValueError(f"裁判 prompt 模板缺少占位符：{'、'.join(missing)}")
    return JudgePrompt(text=text, system=system, user_template=user_template)


def read_judge_template() -> str:
    """读模板文件原文（未缓存）：`prompt_version` 与解析都以它为准。"""
    resource = resources.files(_RESOURCE_PACKAGE).joinpath(_RESOURCE_NAME)
    return resource.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_judge_prompt() -> JudgePrompt:
    """加载并解析模板；进程内只读一次文件。"""
    return parse_judge_prompt(read_judge_template())


def judge_prompt_version() -> str:
    """当前裁判 prompt 的版本。写进评测产物（`rag_runs.judge_*` 之外的旁挂记录）。"""
    return load_judge_prompt().version


def build_judge_messages(
    question: str,
    passages: Sequence[ContextPassage],
    answer: str,
    *,
    prompt: JudgePrompt | None = None,
) -> list[ChatMessage]:
    """组装送给裁判模型的 system / user 两条消息。"""
    return (prompt or load_judge_prompt()).build_messages(question, passages, answer)


def _extract_section(text: str, name: str) -> str:
    opening = f"<{name}>"
    closing = f"</{name}>"
    start = text.find(opening)
    if start < 0:
        raise ValueError(f"裁判 prompt 模板缺少 {opening} 段")
    end = text.find(closing, start + len(opening))
    if end < 0:
        raise ValueError(f"裁判 prompt 模板缺少 {closing} 段")
    return text[start + len(opening) : end].strip()


__all__ = [
    "PROMPT_VERSION_LENGTH",
    "JudgePrompt",
    "build_judge_messages",
    "judge_prompt_version",
    "load_judge_prompt",
    "parse_judge_prompt",
    "prompt_version",
    "read_judge_template",
]
