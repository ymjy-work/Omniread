"""答案 prompt：模板资源、消息组装与 `prompt_version`（M0-01 §5.5）。

模板以**仓库内文件** `prompts/answer.md` 存在，不是代码里的字符串。文件用两个标记行切成
两段，标记行本身不进模型可见文本：

```text
<system> ... </system>    → system 消息
<user>   ... </user>      → user 消息模板
```

两段里的 `{{CONTEXT}}` / `{{QUESTION}}` 是仅有的替换点。

组装规则：

- **system**：只放纪律——只依据材料作答、禁止材料外知识、引用写法 `[C{chapter_index}]`、
  材料不足时明确表示答不了。
- **user**：先材料后问题。每段材料渲染成 `【第 {chapter_index} 章】\\n{text}`，段间空行
  分隔，顺序由调用方给定（装配阶段已按章与 chunk 定序）；材料为空时渲染成固定占位句。

`prompt_version` = 模板文件内容的 sha256 前 12 位，随内容自动变化。语义变更（改变模型
可见文本或判据）即新基线；模板文件里没有注释，因此不存在「注释也 bump」的问题。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from omniread.domain.text import sha256_hex
from omniread.infrastructure.providers.base import ChatMessage

# `rag_runs.prompt_version` 用的短串长度：与语料版本号口径一致（sha256 前 12 位）。
PROMPT_VERSION_LENGTH = 12

_RESOURCE_PACKAGE = "omniread.pipelines.answering"
_RESOURCE_NAME = "prompts/answer.md"

SECTION_SYSTEM = "system"
SECTION_USER = "user"

# 材料段在模型可见文本里的渲染格式。它不属于模板文件，但同样是模型看到的内容，
# 所以必须一起进 `prompt_version` 的输入（见本模块末尾的 `prompt_version`）。
_PASSAGE_HEADER = "【第 {chapter_index} 章】"
_PASSAGE_SEPARATOR = "\n\n"
# 材料为空时的固定占位句：正常路径上检索为空即拒答、不会走到生成，这里是防御性渲染。
_EMPTY_CONTEXT = "（本次没有可用材料）"

# 拼接版本输入用 NUL 分隔：避免「模板尾 + 格式头」凑出与另一组合相同的字节串。
_VERSION_INPUT_SEPARATOR = "\x00"


@dataclass(frozen=True, slots=True)
class ContextPassage:
    """进入 prompt 的一段材料。`chapter_index` 决定它可以被引用的编号。"""

    chapter_index: int
    text: str


@dataclass(frozen=True, slots=True)
class AnswerPrompt:
    """一份解析后的答案 prompt 模板。`text` 是模板文件原文，版本由它派生。"""

    text: str
    system: str
    user_template: str

    @property
    def version(self) -> str:
        return prompt_version(self.text)

    def render_user(
        self, question: str, passages: Sequence[ContextPassage]
    ) -> str:
        """渲染 user 消息：材料块在前，用户问题在后。"""
        return self.user_template.replace(
            "{{CONTEXT}}", render_context(passages)
        ).replace("{{QUESTION}}", question)

    def build_messages(
        self, question: str, passages: Sequence[ContextPassage]
    ) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content=self.system),
            ChatMessage(role="user", content=self.render_user(question, passages)),
        ]


def prompt_version(template_text: str) -> str:
    """模板原文**与渲染格式常量**一起取 sha256 前 12 位。

    不能只算模板文件：材料段的标题格式、段间分隔与空材料占位句都写在代码里，
    它们同样是模型可见文本。只算模板会让「改了格式却不换版本」成立，
    于是两份不同的 prompt 在 run 记录里并列成同一个版本（M0-01 §5.5 的判据是
    「是否改变模型可见文本或判据」，不是「模板文件是否变化」）。
    """
    payload = _VERSION_INPUT_SEPARATOR.join(
        (template_text, _PASSAGE_HEADER, _PASSAGE_SEPARATOR, _EMPTY_CONTEXT)
    )
    return sha256_hex(payload)[:PROMPT_VERSION_LENGTH]


def render_context(passages: Sequence[ContextPassage]) -> str:
    """把材料渲染成模型可见文本；每条以章节号标注，段间空行分隔。"""
    if not passages:
        return _EMPTY_CONTEXT
    return _PASSAGE_SEPARATOR.join(
        f"{_PASSAGE_HEADER.format(chapter_index=passage.chapter_index)}\n{passage.text}"
        for passage in passages
    )


def parse_answer_prompt(text: str) -> AnswerPrompt:
    """按标记行切分模板；缺段或缺占位符即失败，不静默降级。"""
    system = _extract_section(text, SECTION_SYSTEM)
    user_template = _extract_section(text, SECTION_USER)
    if "{{CONTEXT}}" not in user_template or "{{QUESTION}}" not in user_template:
        raise ValueError("答案 prompt 模板缺少 {{CONTEXT}} 或 {{QUESTION}} 占位符")
    return AnswerPrompt(text=text, system=system, user_template=user_template)


def read_answer_template() -> str:
    """读模板文件原文（未缓存）：`prompt_version` 与解析都以它为准。"""
    resource = resources.files(_RESOURCE_PACKAGE).joinpath(_RESOURCE_NAME)
    return resource.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_answer_prompt() -> AnswerPrompt:
    """加载并解析模板；进程内只读一次文件。"""
    return parse_answer_prompt(read_answer_template())


def answer_prompt_version() -> str:
    """当前答案 prompt 的版本，写入 `generation_started.prompt_version` 与 run 记录。"""
    return load_answer_prompt().version


def build_answer_messages(
    question: str,
    passages: Sequence[ContextPassage],
    *,
    prompt: AnswerPrompt | None = None,
) -> list[ChatMessage]:
    """组装送给回答模型的 system / user 两条消息。"""
    return (prompt or load_answer_prompt()).build_messages(question, passages)


def _extract_section(text: str, name: str) -> str:
    opening = f"<{name}>"
    closing = f"</{name}>"
    start = text.find(opening)
    if start < 0:
        raise ValueError(f"答案 prompt 模板缺少 {opening} 段")
    end = text.find(closing, start + len(opening))
    if end < 0:
        raise ValueError(f"答案 prompt 模板缺少 {closing} 段")
    return text[start + len(opening) : end].strip()


__all__ = [
    "PROMPT_VERSION_LENGTH",
    "AnswerPrompt",
    "ContextPassage",
    "answer_prompt_version",
    "build_answer_messages",
    "load_answer_prompt",
    "parse_answer_prompt",
    "prompt_version",
    "read_answer_template",
    "render_context",
]
