"""查询改写：带指代的一问 → 能独立成句的一句。

改写 prompt 全文在 `prompts/rewrite.md`，组装与版本规则见 `prompt.py`；
四态与降级规则见 `rewriter.py`。**失败一律降级成原问题，不阻断问答。**
"""

from __future__ import annotations

from omniread.pipelines.rewriting.prompt import (
    PROMPT_VERSION_LENGTH,
    RewritePrompt,
    build_rewrite_messages,
    load_rewrite_prompt,
    parse_rewrite_prompt,
    prompt_version,
    read_rewrite_template,
    render_history,
    rewrite_prompt_version,
)
from omniread.pipelines.rewriting.rewriter import (
    MAX_REWRITE_LENGTH,
    REWRITE_TEMPERATURE,
    FakeQueryRewriter,
    QueryRewriter,
    RewriteResult,
    RewriteStatus,
    skipped,
)

__all__ = [
    "MAX_REWRITE_LENGTH",
    "PROMPT_VERSION_LENGTH",
    "REWRITE_TEMPERATURE",
    "FakeQueryRewriter",
    "QueryRewriter",
    "RewritePrompt",
    "RewriteResult",
    "RewriteStatus",
    "build_rewrite_messages",
    "load_rewrite_prompt",
    "parse_rewrite_prompt",
    "prompt_version",
    "read_rewrite_template",
    "render_history",
    "rewrite_prompt_version",
    "skipped",
]
