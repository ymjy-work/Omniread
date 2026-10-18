"""会话摘要：一段对话 → 能替代原文的一段话。

摘要 prompt 全文在 `prompts/summarize.md`，组装与版本规则见 `prompt.py`；
模型调用与失败口径见 `summarizer.py`。**失败即抛**——这条链没有「降级」这个选项。
"""

from __future__ import annotations

from omniread.pipelines.summarizing.prompt import (
    PROMPT_VERSION_LENGTH,
    SummarizePrompt,
    build_summarize_messages,
    load_summarize_prompt,
    parse_summarize_prompt,
    prompt_version,
    read_summarize_template,
    render_previous,
    summarize_prompt_version,
)
from omniread.pipelines.summarizing.summarizer import (
    SUMMARIZE_TEMPERATURE,
    FakeSessionSummarizer,
    SessionSummarizer,
)

__all__ = [
    "PROMPT_VERSION_LENGTH",
    "SUMMARIZE_TEMPERATURE",
    "FakeSessionSummarizer",
    "SessionSummarizer",
    "SummarizePrompt",
    "build_summarize_messages",
    "load_summarize_prompt",
    "parse_summarize_prompt",
    "prompt_version",
    "read_summarize_template",
    "render_previous",
    "summarize_prompt_version",
]
