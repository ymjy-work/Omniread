"""评测（M0-9）：检索层指标、run 产物与基线（M0-04）。

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
    AnswerOutcome,
    aggregate_generation,
    fold_answer,
    generation_failure_rows,
    score_answer,
)
from omniread.pipelines.evaluation.generation_runner import (
    FAKE_ANSWER_TRUST_NOTE,
    GenerationEvalResult,
    RecordedRetrieval,
    eval_request_id,
    run_generation_eval,
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
    build_query_request,
    failure_rows,
    load_golden_questions,
    run_retrieval_eval,
)
from omniread.pipelines.evaluation.types import (
    STATUS_ANSWERED,
    STATUS_GENERATION_FAILED,
    STATUS_INSUFFICIENT_EVIDENCE,
    GenerationScoreRecord,
    RetrievalScoreRecord,
)

__all__ = [
    "FAKE_ANSWER_TRUST_NOTE",
    "FAKE_TRUST_NOTE",
    "STATUS_ANSWERED",
    "STATUS_GENERATION_FAILED",
    "STATUS_INSUFFICIENT_EVIDENCE",
    "AnswerOutcome",
    "EvalError",
    "EvalRunConfig",
    "GenerationEvalResult",
    "GenerationScoreRecord",
    "RecordedRetrieval",
    "RetrievalEvalResult",
    "RetrievalScoreRecord",
    "aggregate",
    "aggregate_generation",
    "build_query_request",
    "eval_request_id",
    "failure_rows",
    "fmt_ratio",
    "fold_answer",
    "generation_failure_rows",
    "load_golden_questions",
    "matched_keys_from_records",
    "run_generation_eval",
    "run_retrieval_eval",
    "score_answer",
    "score_question",
    "summarize_counts",
    "write_eval_run_dir",
]
