"""回答与引用（M0-5）：prompt 组装、GLM 流式生成、`[C{chapter_index}]` 引用。

引用是纯文本且服务端不改写模型输出，见 M0-01 §6.4。
回答 prompt 全文在 `prompts/answer.md`，组装与版本规则见 `prompt.py`。
"""

from __future__ import annotations

from omniread.pipelines.answering.prompt import (
    PROMPT_VERSION_LENGTH,
    AnswerPrompt,
    ContextPassage,
    answer_prompt_version,
    build_answer_messages,
    load_answer_prompt,
    parse_answer_prompt,
    prompt_version,
    read_answer_template,
    render_context,
)

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

