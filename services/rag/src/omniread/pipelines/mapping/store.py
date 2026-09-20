"""`chunk_mappings` 的写入、失效与读时校验（M0-02 §3.6）。

**五元组主键覆盖不到什么**（这是本模块存在的另一半理由）。主键是
`(evidence_hash, chunking_version, tokenizer_id, mapper_model, mapper_prompt_version)`，
后四项全是**人工维护的标签**：`chunking_version` 是字面常量 `m0-placeholder-v1`，
不派生自 chunker 代码；`tokenizer_id` 带的是词表 revision，不含分词库版本。
改了 `chunker.py` 的切分正则、或升级 `qwen-tokenizer`，chunk 边界会移动，
而这两项一字不变——同一 evidence 直接命中缓存，拿回一个指向**另一段正文**的 `#cN`。

标签能补多少补多少（改算法就改常量），但「靠人记得改」不是机制。所以读时再验一次：
把库里每条映射拿回当前切片**重放**一遍，确认它指向的 chunk 仍然完整包含该证据。
验不过即视为过期，`purge` 掉再重映射。这条校验是这套缓存唯一的机制性保障。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from omniread.domain.text import evidence_hash, normalize_minimal
from omniread.infrastructure.db.models import ChunkMapping
from omniread.pipelines.mapping.artifacts import MappingRecord
from omniread.pipelines.mapping.sources import ChapterSlices


@dataclass(frozen=True, slots=True)
class StaleMapping:
    """一条读时校验未通过的缓存行；`reason` 说明它为什么不再成立。"""

    evidence_hash: str
    matched_chunk_key: str | None
    chapter_id: str
    reason: str


def build_mapping_rows(
    records: Sequence[MappingRecord],
    chunking_version: str,
    tokenizer_id: str,
) -> list[dict[str, object]]:
    """把 run 产物行折成 `chunk_mappings` 的待写行，**按五元组主键去重**。

    去重不是优化，是正确性要求：同一段 evidence 会被多道题复用（本 Golden 357 条
    evidence 只对应 347 个唯一 hash）。不去重的话，一条 INSERT 里会出现重复主键，
    Postgres 整批拒绝并报
    `ON CONFLICT DO UPDATE command cannot affect row a second time`。

    折叠是无损的：主键相同意味着同章、同文、同算法，映射结果必然一致。
    单独成函数是为了能脱离数据库测——这条规则一旦退回批量写入就会重新炸掉。
    """
    deduped: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
    for record in records:
        key = (
            record.evidence_hash,
            chunking_version,
            tokenizer_id,
            record.mapper_model,
            record.mapper_prompt_version,
        )
        deduped[key] = {
            "evidence_hash": record.evidence_hash,
            "chunking_version": chunking_version,
            "tokenizer_id": tokenizer_id,
            "mapper_model": record.mapper_model,
            "mapper_prompt_version": record.mapper_prompt_version,
            "match_status": record.match_status,
            "matched_chunk_key": record.matched_chunk_key,
            "confidence": record.confidence,
            "overlap_reason": record.overlap_reason,
            "alternative_chunk_key": record.alternative_chunk_key,
        }
    return list(deduped.values())


def write_mappings(
    session_factory: sessionmaker[Session],
    records: Sequence[MappingRecord],
    *,
    chunking_version: str,
    tokenizer_id: str,
) -> int:
    """按五元组主键 upsert 映射行；返回**去重后**写入的行数。

    两次去重都是必需的，各挡一类失败：

    - **同批内去重**：同一段 evidence 会被多道题复用（本 Golden 357 条里只有 347 个唯一
      hash，9 组重复）。映射是 evidence 的属性而不是题的属性，所以这些行应当折叠成一行；
      若原样塞进一条 INSERT，Postgres 会整批拒绝——
      `ON CONFLICT DO UPDATE command cannot affect row a second time`。
    - **跨批 upsert**：同一天重跑必然撞上已存在的键，`on_conflict_do_update` 让它变成更新，
      否则第二次跑整批失败。

    `chapter_id` 不是列（它是 `chunk_key` 的前缀），不写。
    """
    rows = build_mapping_rows(records, chunking_version, tokenizer_id)
    if not rows:
        return 0

    statement = insert(ChunkMapping).values(rows)
    update_columns = {
        column: statement.excluded[column]
        for column in (
            "match_status",
            "matched_chunk_key",
            "confidence",
            "overlap_reason",
            "alternative_chunk_key",
        )
    }
    statement = statement.on_conflict_do_update(
        index_elements=[
            "evidence_hash",
            "chunking_version",
            "tokenizer_id",
            "mapper_model",
            "mapper_prompt_version",
        ],
        set_=update_columns,
    )
    with session_factory() as session:
        session.execute(statement)
        session.commit()
    return len(rows)


def purge_mappings(
    session_factory: sessionmaker[Session],
    *,
    chunking_version: str | None = None,
    mapper_model: str | None = None,
    mapper_prompt_version: str | None = None,
) -> int:
    """按维度删除映射行；返回删除行数。

    M0-02 §3.6 要求「改映射 prompt 或换 mapper 模型必须显式 purge，否则旧映射被静默复用」，
    但未给出命令——这就是那条命令。三个维度都可选，不传即整表清空；调用方必须显式说明
    自己在清什么，避免「以为只清了 prompt、其实把模型维度也清了」。
    """
    statement = delete(ChunkMapping)
    if chunking_version is not None:
        statement = statement.where(ChunkMapping.chunking_version == chunking_version)
    if mapper_model is not None:
        statement = statement.where(ChunkMapping.mapper_model == mapper_model)
    if mapper_prompt_version is not None:
        statement = statement.where(
            ChunkMapping.mapper_prompt_version == mapper_prompt_version
        )
    with session_factory() as session:
        # DELETE 走 CursorResult，才带 rowcount；Session.execute 的静态类型是宽泛的 Result。
        cursor = cast(CursorResult[Any], session.execute(statement))
        session.commit()
        return int(cursor.rowcount or 0)


def verify_mappings(
    session_factory: sessionmaker[Session],
    evidence: Sequence[tuple[str, str]],
    slices: Mapping[str, ChapterSlices],
) -> list[StaleMapping]:
    """读时校验：库里每条映射是否仍指向一个**完整包含该证据**的 chunk。

    `evidence` 是 `(chapter_id, content)` 的序列——校验要用原文，因此只有调用方
    （它已经持有 Golden）能给。校验不通过的行即过期缓存；调用方应先 `purge` 再重映射，
    不要让它们参与评测。
    """
    wanted = {
        evidence_hash(chapter_id, content): (chapter_id, content)
        for chapter_id, content in evidence
    }
    with session_factory() as session:
        rows = session.execute(select(ChunkMapping)).scalars().all()

    stale: list[StaleMapping] = []
    for row in rows:
        target = wanted.get(row.evidence_hash)
        if target is None:
            # 库里存着一条当前 Golden 里没有的映射：不是错，但它是噪声，报告出来。
            stale.append(
                StaleMapping(
                    evidence_hash=row.evidence_hash,
                    matched_chunk_key=row.matched_chunk_key,
                    chapter_id="",
                    reason="该 evidence_hash 不在当前 Golden 内（改题后的残留）",
                )
            )
            continue
        chapter_id, content = target
        if row.match_status != "matched" or not row.matched_chunk_key:
            continue
        chapter = slices.get(chapter_id)
        if chapter is None:
            stale.append(
                StaleMapping(
                    evidence_hash=row.evidence_hash,
                    matched_chunk_key=row.matched_chunk_key,
                    chapter_id=chapter_id,
                    reason=f"章节 {chapter_id} 不在当前切片内",
                )
            )
            continue
        if not _still_contains(chapter, row.matched_chunk_key, content):
            stale.append(
                StaleMapping(
                    evidence_hash=row.evidence_hash,
                    matched_chunk_key=row.matched_chunk_key,
                    chapter_id=chapter_id,
                    reason=(
                        f"{row.matched_chunk_key} 不再完整包含该证据"
                        "（chunk 边界已移动，缓存键未变）"
                    ),
                )
            )
    return stale


def _still_contains(chapter: ChapterSlices, chunk_key: str, content: str) -> bool:
    normalized = normalize_minimal(content)
    for span in chapter.spans:
        if span.chunk_key != chunk_key:
            continue
        start = chapter.text.find(normalized)
        if start < 0:
            return False
        return span.start <= start and start + len(normalized) <= span.end
    return False
