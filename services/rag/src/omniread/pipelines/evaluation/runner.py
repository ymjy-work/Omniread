"""检索层评测编排（M0-04 §5.1，M0-9）。

**离线跑得出的数字不能进 baseline** —— 这条写在配置里、也写在这里，因为它反直觉：

`retrieval_provider=fake` 只把 embedder 与 reranker 换成假的，`dense` 仍然是
`PgVectorDenseIndex`，指向真库中用真实 embedding 写入的向量列。于是 dense 会拿
**假查询向量**去比对**真文档向量**——两个向量空间不匹配，余弦值是确定性噪声，
排名看似正常却无语义（`api/app.py` 的启动日志自己承认了这一点）。噪声随
`fused → rerank → assembled` 一路传下去，`evidence_recall` 也跟着失真。

所以离线的可信子集只有：KW（BM25，纯本地）、装配 cap 的结构约束、以及各阶段的
`leak` 结构检查。凡是要看 `evidence_recall` 的结论，必须用真 embedding + rerank。
本模块不阻止你离线跑，但会把这件事写进 run 配置的 `trust_note`，免得日后有人
把一次假 provider 的产物当成 baseline。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from omniread.domain.models import QueryRequest, RealmLevel
from omniread.pipelines.evaluation.artifacts import EvalRunConfig
from omniread.pipelines.evaluation.metrics import (
    aggregate,
    matched_keys_from_records,
    score_question,
    summarize_counts,
)
from omniread.pipelines.evaluation.types import RetrievalScoreRecord
from omniread.pipelines.retrieval.pipeline import RetrievalPipeline

_NON_QUESTION_FILES = frozenset({"schema.json", "example.json"})

# 离线跑的产物可以看，但不能当基线。这句话会进 config.json。
FAKE_TRUST_NOTE = (
    "本次跑用假 embedding/rerank：dense 以假查询向量对真库向量，排名无语义，"
    "噪声随 fused/rerank/assembled 传下去。本产物的 evidence_recall 不可作为基线，"
    "只能用于验证链路结构与 KW/leak 的结构约束。"
)


class EvalError(ValueError):
    """评测不可继续：Golden 不可用或题目与检索链对不上。"""


@dataclass(frozen=True, slots=True)
class RetrievalEvalResult:
    config: EvalRunConfig
    records: tuple[RetrievalScoreRecord, ...]
    summary: dict[str, object]
    failures: tuple[dict[str, object], ...]


def load_golden_questions(golden_dir: Path) -> list[dict]:
    """按 id 升序读入全部题目（原始字典，逐字段取用）。

    不另建 dataclass：评测要读的字段（含 `must_cite_groups` 与 `progress`）
    就是 Golden 的 schema 本身，多一层映射只会多一处与 schema 分叉的地方。
    """
    if not golden_dir.is_dir():
        raise EvalError(f"Golden 目录不存在：{golden_dir}")
    questions = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(golden_dir.glob("*.json"))
        if path.name not in _NON_QUESTION_FILES
    ]
    if not questions:
        raise EvalError(f"{golden_dir} 下没有题目文件")
    return sorted(questions, key=lambda item: item["id"])


async def run_retrieval_eval(
    *,
    run_id: str,
    questions: Sequence[dict],
    pipeline: RetrievalPipeline,
    mapping_lookup: Mapping[str, str | None],
    dataset_hash: str,
    dataset_version: str,
    corpus_manifest_hash: str,
    chunk_source: str,
    chunking_version: str,
    tokenizer_id: str,
    retrieval_provider: str,
    embedding_provider: str,
    embedding_model: str,
    embedding_dim: int,
    rerank_provider: str,
    rerank_model: str,
    retrieval_params: Mapping[str, object],
    book_id: int = 1,
    trust_note: str = "",
    neighbor_expand: bool = True,
) -> RetrievalEvalResult:
    """逐题跑检索链并打分。题目顺序即 Golden 的 id 序，结果与顺序无关。

    `neighbor_expand` 是 `QueryRequest` 的既有字段、默认开。关掉它只改装配会不会补邻块，
    不改任何上限——用来把「邻块占用名额」与「每章上限」两种效应分开（见
    `docs/M1-装配瓶颈测评方案.md` 第三节）。它会随 `retrieval_params` 记进 config.json。
    """
    records: list[RetrievalScoreRecord] = []
    for question in questions:
        request = QueryRequest(
            book_id=book_id,
            question=question["question"],
            level=RealmLevel(question["level"]),
            progress=question.get("progress"),
            neighbor_expand=neighbor_expand,
        )
        outcome = await pipeline.retrieve(request)
        records.append(score_question(question, outcome, mapping_lookup))

    config = EvalRunConfig(
        run_id=run_id,
        kind="retrieval",
        phase="retrieval",
        dataset_hash=dataset_hash,
        dataset_version=dataset_version,
        corpus_manifest_hash=corpus_manifest_hash,
        chunking_version=chunking_version,
        tokenizer_id=tokenizer_id,
        chunk_source=chunk_source,
        retrieval_provider=retrieval_provider,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dim=embedding_dim,
        rerank_provider=rerank_provider,
        rerank_model=rerank_model,
        retrieval_params=dict(retrieval_params),
        trust_note=trust_note,
    )
    summary = aggregate(records)
    summary["failure_counts"] = summarize_counts(records)
    return RetrievalEvalResult(
        config=config,
        records=tuple(records),
        summary=summary,
        failures=failure_rows(records),
    )


def failure_rows(
    records: Sequence[RetrievalScoreRecord],
) -> tuple[dict[str, object], ...]:
    """失败清单：只从逐题记录生成，不回读题面。

    题面里用得上的字段（`type`）逐题记录里本来就有；少一路输入就少一处
    「产物重算不出来」的地方——而改口径时恰恰只能靠逐题记录重算，
    重跑要再花一遍真实调用，还会把同一个 run_id 换成另一次采样的结果。
    """
    return tuple(_failure_row(record) for record in records if _is_failure(record))


def _is_failure(record: RetrievalScoreRecord) -> bool:
    """这一题算不算失败：证据没召全，或任一阶段越界。

    用 `evidence_hit < evidence_total` 而不是「有没有命中某个组」：单条口径下
    「漏了哪几条」才是能直接指到修法的信息，而聚合口径会把「差一条」与
    「差一整组」抹成同一个布尔值。
    """
    return record.evidence_hit < record.evidence_total or record.leak_total > 0


def _failure_row(record: RetrievalScoreRecord) -> dict[str, object]:
    """失败清单的一行：只写指针、阶段与指标快照（M0-02 §7.1 的字段白名单）。

    `stage` 是判定失败**卡在哪一层**，用来分辨修检索还是修装配：

    - `leak`：任一阶段越界，先修 realm 过滤，别的都排后面；
    - `mapping`：有证据压根没映射上，属 Golden 或映射问题，不是检索的问题；
    - `retrieval`：映射到了但连 rerank 都没召回到，属召回问题；
    - `assembly`：rerank 召回到了、被装配裁掉，属装配 cap 问题。
    """
    return {
        "question_id": record.question_id,
        "difficulty": record.difficulty,
        "stage": _failure_stage(record),
        "chunk_key": (
            record.mapped_not_assembled_keys[0] if record.mapped_not_assembled_keys else ""
        ),
        "metrics": (
            f"evidence {record.evidence_hit}/{record.evidence_total} "
            f"mapped {record.evidence_mapped}/{record.evidence_total} "
            f"leak {record.leak_total}"
        ),
        "question_form": record.question_type,
    }


def _failure_stage(record: RetrievalScoreRecord) -> str:
    if record.leak_total > 0:
        return "leak"
    if record.evidence_mapped < record.evidence_total:
        return "mapping"
    reranked = set(record.rerank_keys)
    if any(key not in reranked for key in record.mapped_not_assembled_keys):
        return "retrieval"
    return "assembly"


__all__ = [
    "FAKE_TRUST_NOTE",
    "EvalError",
    "RetrievalEvalResult",
    "failure_rows",
    "load_golden_questions",
    "matched_keys_from_records",
    "run_retrieval_eval",
]
