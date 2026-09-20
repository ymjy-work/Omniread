"""Golden evidence → chunk 映射（M0-7b，口径见 M0-02 §6）。

主路径是**确定性区间包含**：evidence 按 `M0-04` §2.2 必须是原文片段，是原文就由区间精确
给出归属，不经过模型判断（`deterministic`）。模型只在 evidence 不是精确子串时兜底
（`fallback`），本项目当前 357 条全部由主路径解决。

产物分两处落：`chunk_mappings`（跨 run 复用的缓存，主键五元组）与 run 目录（审计副本）。
run 目录进 git，因此只带指针与指标值；需要看正文的人工复核产物落 `temp/`（`review`）。
"""

from __future__ import annotations

from omniread.pipelines.mapping.artifacts import (
    ALLOWED_RUN_FILES,
    MAX_STRING_FIELD,
    ArtifactRedlineError,
    MappingRecord,
    RunConfig,
    check_run_dir,
    write_run_dir,
)
from omniread.pipelines.mapping.deterministic import (
    TIER_INTRODUCER,
    TIER_MAX_COVERAGE,
    TIER_NONE,
    TIER_PARTIAL,
    TIER_UNIQUE_COVER,
    map_evidence_deterministic,
)
from omniread.pipelines.mapping.prompt import (
    MAPPING_PROMPT_VERSION,
    render_mapping_prompt,
)
from omniread.pipelines.mapping.sources import ChapterSlices, slices_from_corpus
from omniread.pipelines.mapping.spans import ChunkSpanError, spans_from_contents
from omniread.pipelines.mapping.types import (
    DETERMINISTIC_MAPPER_MODEL,
    MATCH_LOW_CONF,
    MATCH_MATCHED,
    MATCH_UNMATCHED,
    NO_PROMPT_VERSION,
    ChunkSpan,
    MappingOutcome,
)

__all__ = [
    "ALLOWED_RUN_FILES",
    "DETERMINISTIC_MAPPER_MODEL",
    "MAPPING_PROMPT_VERSION",
    "MATCH_LOW_CONF",
    "MATCH_MATCHED",
    "MATCH_UNMATCHED",
    "MAX_STRING_FIELD",
    "NO_PROMPT_VERSION",
    "TIER_INTRODUCER",
    "TIER_MAX_COVERAGE",
    "TIER_NONE",
    "TIER_PARTIAL",
    "TIER_UNIQUE_COVER",
    "ArtifactRedlineError",
    "ChapterSlices",
    "ChunkSpan",
    "ChunkSpanError",
    "MappingOutcome",
    "MappingRecord",
    "RunConfig",
    "check_run_dir",
    "map_evidence_deterministic",
    "render_mapping_prompt",
    "slices_from_corpus",
    "spans_from_contents",
    "write_run_dir",
]
