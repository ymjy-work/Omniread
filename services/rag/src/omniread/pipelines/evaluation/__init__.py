"""评测（M0-8 / M0-9）：检索层指标、run 产物与基线（M0-04）。

**分两层且必须分开**（`M0-04` §1）：检索层只调 embedding + rerank，生成层调生成模型 + judge。
混测会让失败无法归因——「检索没找到」与「检索到了但答案错」的修法完全不同。

**离线数字不能进 baseline**：`retrieval_provider=fake` 只换 embedder 与 reranker，
`dense` 仍拿假查询向量去比对真库向量，排名是确定性噪声。详见 `runner.FAKE_TRUST_NOTE`。
"""

from __future__ import annotations

from omniread.pipelines.evaluation.artifacts import (
    EvalRunConfig,
    fmt_ratio,
    write_eval_run_dir,
)
from omniread.pipelines.evaluation.generation import (
    MEMBERSHIP_KEY,
    CitationVerdict,
    aggregate_generation,
    judge_citation_membership,
)
from omniread.pipelines.evaluation.metrics import (
    aggregate,
    matched_keys_from_records,
    score_question,
    summarize_counts,
)
from omniread.pipelines.evaluation.runner import (
    FAKE_TRUST_NOTE,
    EvalError,
    RetrievalEvalResult,
    failure_rows,
    load_golden_questions,
    run_retrieval_eval,
)
from omniread.pipelines.evaluation.types import (
    GenerationScoreRecord,
    RetrievalScoreRecord,
)

__all__ = [
    "FAKE_TRUST_NOTE",
    "MEMBERSHIP_KEY",
    "CitationVerdict",
    "EvalError",
    "EvalRunConfig",
    "GenerationScoreRecord",
    "RetrievalEvalResult",
    "RetrievalScoreRecord",
    "aggregate",
    "aggregate_generation",
    "failure_rows",
    "fmt_ratio",
    "judge_citation_membership",
    "load_golden_questions",
    "matched_keys_from_records",
    "run_retrieval_eval",
    "score_question",
    "summarize_counts",
    "write_eval_run_dir",
]
