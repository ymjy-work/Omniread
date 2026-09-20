"""`rag_runs` 落库（M0-02 §7.1「与 run 目录的分工」）。

DB 存**可查询的元数据**（供 baseline diff 与「哪次跑用了什么」），run 目录存逐题明细。
两者记的是同一件事的两面，所以这里只接 `EvalRunConfig`——它已经是白名单字段集，
不接受任意字典，避免有人顺手把 `Settings.model_dump()` 塞进来（那是凭据落库）。

`rag_runs` 的 21 列全部 `NOT NULL` 且无列默认值，漏一列即插入失败——这是有意的，
它逼调用方把「这次跑用了什么」说全。检索层 run 用不到回答模型与 judge，
按规格里的实际语义写 `NOT_EXERCISED` 而不是留空或编一个型号。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from omniread.infrastructure.db.models import RagRun
from omniread.pipelines.evaluation.artifacts import EvalRunConfig

# 本 run 没有经过这一层。写明确的值而不是空串：空串在库里看起来像「漏填」，
# 而它是确定结论——这一层没跑。
NOT_EXERCISED = "not-exercised"


def build_run_row(
    config: EvalRunConfig,
    *,
    artifact_dir: str,
    started_at: datetime,
    finished_at: datetime,
    answer_provider: str = NOT_EXERCISED,
    answer_model: str = NOT_EXERCISED,
    judge_provider: str = NOT_EXERCISED,
    judge_model: str = NOT_EXERCISED,
    prompt_version: str = NOT_EXERCISED,
) -> dict[str, object]:
    """把 run 配置折成一行 `rag_runs`；参数与列一一对应。"""
    return {
        "run_id": config.run_id,
        "kind": config.kind,
        "dataset_hash": config.dataset_hash,
        "dataset_version": config.dataset_version,
        "corpus_manifest_hash": config.corpus_manifest_hash,
        "chunking_version": config.chunking_version,
        "tokenizer_id": config.tokenizer_id,
        "answer_provider": answer_provider,
        "answer_model": answer_model,
        "judge_provider": judge_provider,
        "judge_model": judge_model,
        "embedding_provider": config.embedding_provider,
        "embedding_model": config.embedding_model,
        "embedding_dim": config.embedding_dim,
        "rerank_provider": config.rerank_provider,
        "rerank_model": config.rerank_model,
        "prompt_version": prompt_version,
        "retrieval_params": dict(config.retrieval_params),
        "artifact_dir": artifact_dir,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def write_run(
    session_factory: sessionmaker[Session],
    row: dict[str, object],
) -> None:
    """按主键 upsert 一行 run 记录。

    同一 run_id 重跑必然撞主键（`run_id` 是 PK），撞键即更新——run 目录那侧也是重写，
    两边行为一致。不换 run_id：换 ID 会让「同一次评测跑了两次」看起来像两次不同的评测。
    """
    statement = insert(RagRun).values([row])
    update_columns = {
        column: statement.excluded[column]
        for column in row
        if column != "run_id"
    }
    statement = statement.on_conflict_do_update(
        index_elements=["run_id"], set_=update_columns
    )
    with session_factory() as session:
        session.execute(statement)
        session.commit()


def utc_now() -> datetime:
    return datetime.now(UTC)
