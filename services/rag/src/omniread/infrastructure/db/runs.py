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


def build_run_row(
    config: EvalRunConfig,
    *,
    artifact_dir: str,
    started_at: datetime,
    finished_at: datetime,
) -> dict[str, object]:
    """把 run 配置折成一行 `rag_runs`；参数与列一一对应。

    `answer_*` / `judge_*` / `prompt_version` **取自 config 本身**，不再另立参数：
    那五个值本来就在 `EvalRunConfig` 里，多一路传参就多一处两边可以不一致的地方
    （传了 A、config 里记着 B，事后看产物根本分不出来）。
    """
    return {
        "run_id": config.run_id,
        "kind": config.kind,
        "dataset_hash": config.dataset_hash,
        "dataset_version": config.dataset_version,
        "corpus_manifest_hash": config.corpus_manifest_hash,
        "chunking_version": config.chunking_version,
        "tokenizer_id": config.tokenizer_id,
        "answer_provider": config.answer_provider,
        "answer_model": config.answer_model,
        "judge_provider": config.judge_provider,
        "judge_model": config.judge_model,
        "embedding_provider": config.embedding_provider,
        "embedding_model": config.embedding_model,
        "embedding_dim": config.embedding_dim,
        "rerank_provider": config.rerank_provider,
        "rerank_model": config.rerank_model,
        "prompt_version": config.prompt_version,
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
