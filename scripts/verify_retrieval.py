#!/usr/bin/env python
"""M0-4 检索链确定性验证：真库语料 + 假 provider，全程不发真实 API 调用。

覆盖 M0-03 §2 的 M0-4 验收里可在本机跑的部分：

1. 未嵌入行显式报告：`chunks.embedding` 为 NULL 的行不会被 dense 召回，若全库尚未
   嵌入则 dense 一路 0 条。脚本把这件事报出来，不拿它冒充通过。
2. **in-realm 排名同源**：同一 query 在 `full` 与 `past progress=N` 下，BM25 打分域
   都是全书（统计量一次构建），realm 只过滤候选；in-realm 的排名与分数逐条一致。
3. **leak 硬门禁**：`past` 模式下逐阶段的越界章节数必须为 0。
4. **装配 cap 三项都能被触发**：章上限、每章段数、最终段数各找到一个真实样例。
5. **邻块补位**：prev 优先、固定一跳、不跨章、不从邻块递归。

用法（仓库根执行，凭据只从环境变量读）：
    keymgr run omniread bash scripts/verify-retrieval.sh
或先导出 POSTGRES_PASSWORD 后：
    bash scripts/verify-retrieval.sh
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from omniread.domain.models import QueryRequest, RealmLevel
from omniread.infrastructure.db.models import Chunk
from omniread.infrastructure.db.session import create_engine_from_env
from omniread.infrastructure.objectstore.corpus import read_corpus
from omniread.infrastructure.providers.base import RerankResult
from omniread.infrastructure.providers.fake import FakeEmbeddingModel
from omniread.pipelines.assembly import (
    REASON_CHAPTER_CAP,
    REASON_CHAPTER_CHUNK_CAP,
    REASON_TOP_K_CAP,
)
from omniread.pipelines.importing import ChunkPlan, build_import_plan
from omniread.pipelines.params import M0_PARAMS
from omniread.pipelines.retrieval.bm25 import Bm25Index, tokenize
from omniread.pipelines.retrieval.dense import PgVectorDenseIndex
from omniread.pipelines.retrieval.pipeline import RetrievalPipeline
from omniread.pipelines.retrieval.query import normalize_query
from omniread.pipelines.retrieval.store import PgChunkStore
from omniread.pipelines.retrieval.types import ChunkRecord, RetrievalOutcome

DEFAULT_CORPUS_ROOT = (
    Path(__file__).resolve().parent.parent / "asset" / "《不时轻声地以俄语遮羞的邻座艾莉同学》"
)

# 固定候选查询：覆盖常见名词与随语料确定的「同章多次出现」词。
FALLBACK_QUERIES = [
    "艾莉",
    "俄语",
    "学生会长",
    "政近",
    "妹妹",
    "考试",
    "文化祭",
    "学生会",
    "同级生",
    "转校生",
    "暑假",
    "圣诞",
    "泳池",
    "教室",
]


@dataclass(slots=True)
class Checker:
    passed: int = 0
    failed: int = 0

    def ok(self, message: str) -> None:
        print(f"  OK   {message}")
        self.passed += 1

    def bad(self, message: str, detail: str) -> None:
        print(f"  FAIL {message}\n       {detail}")
        self.failed += 1


class OrderPreservingReranker:
    """假 rerank：按入参顺序给递减分数，从而原样保留 RRF 序。

    假 provider 只用于离线验证；真实路径走百炼适配器，本脚本不触及。
    """

    model = "stub-order-preserving"

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int | None = None
    ) -> list[RerankResult]:
        ranked = [
            RerankResult(index=index, score=1.0 - index / max(len(documents), 1))
            for index in range(len(documents))
        ]
        return ranked[:top_n] if top_n is not None else ranked


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def concentrated_queries(records: Sequence[ChunkRecord], limit: int = 12) -> list[str]:
    """按「单章出现次数」挑词：某词在一章里出现的 chunk 数越多，越可能触发每章段数上限。"""
    per_token: dict[str, Counter[int]] = defaultdict(Counter)
    for record in records:
        for token in set(tokenize(record.content)):
            per_token[token][record.chapter_index] += 1
    usable = [token for token in per_token if len(token) >= 2 and not token.isdigit()]
    usable.sort(key=lambda token: (-max(per_token[token].values()), token))
    return usable[:limit]


def load_records_from_corpus(corpus_root: Path, book_id: int) -> list[ChunkRecord]:
    """无库路径：从仓库内语料直接分块，重建与 `chunks` 表同形的检索视图。

    prev/next 按导入回填的同一条规则重建（同章内 lag/lead），从而语料模式下装配行为
    与真库一致。供没有 `POSTGRES_PASSWORD` 时验证检索链本身。
    """
    plan = build_import_plan(read_corpus(corpus_root, book_id=book_id))
    by_chapter: dict[str, list[ChunkPlan]] = defaultdict(list)
    for chunk in plan.chunks:
        by_chapter[chunk.chapter_id].append(chunk)
    records: list[ChunkRecord] = []
    for chapter_chunks in by_chapter.values():
        ordered = sorted(chapter_chunks, key=lambda chunk: chunk.chunk_index)
        for position, chunk in enumerate(ordered):
            records.append(
                ChunkRecord(
                    chunk_key=chunk.chunk_key,
                    chapter_index=chunk.chapter_index,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    prev_chunk_key=ordered[position - 1].chunk_key if position > 0 else None,
                    next_chunk_key=(
                        ordered[position + 1].chunk_key
                        if position + 1 < len(ordered)
                        else None
                    ),
                )
            )
    records.sort(key=lambda record: (record.chapter_index, record.chunk_index))
    return records


class _CorpusStore:
    """语料模式下的 ChunkStore 替身（与 PgChunkStore 同契约）。"""

    def __init__(self, records: Sequence[ChunkRecord]) -> None:
        self._records = list(records)

    def book_chapter_range(self, book_id: int) -> tuple[int, int] | None:
        if not self._records:
            return None
        chapters = [record.chapter_index for record in self._records]
        return min(chapters), max(chapters)

    def load_chunks(self, book_id: int) -> Sequence[ChunkRecord]:
        return list(self._records)


class _EmptyDenseIndex:
    """语料模式没有向量列，dense 一路如实返回 0 条。"""

    def search(
        self, query_vector: Sequence[float], *, book_id: int, lo: int, hi: int, k: int
    ) -> Sequence[object]:
        return []


def build_pipeline(store: object, dense: object) -> RetrievalPipeline:
    return RetrievalPipeline(
        store=store,  # type: ignore[arg-type]
        dense=dense,  # type: ignore[arg-type]
        embedder=FakeEmbeddingModel(),
        reranker=OrderPreservingReranker(),
    )


async def check_dense_recall(
    session_factory: sessionmaker[Session],
    records: Sequence[ChunkRecord],
    book_id: int,
    checker: Checker,
) -> None:
    section("1 向量可检索行：embedding IS NOT NULL 的现状")
    with session_factory() as session:
        total, embedded = session.execute(
            select(
                func.count(Chunk.chunk_key),
                func.count(Chunk.embedding),
            ).where(Chunk.book_id == book_id)
        ).one()
    print(
        f"  语料：book_id={book_id} chunk 总数 {total}，"
        f"已嵌入 {embedded}，NULL {total - embedded}"
    )

    vector = await FakeEmbeddingModel().embed_query("艾莉 俄语")
    hits = PgVectorDenseIndex(session_factory).search(
        vector, book_id=book_id, lo=1, hi=10**9, k=M0_PARAMS.dense_k
    )
    if embedded == 0:
        # 全库尚未嵌入时 dense 必然 0 条：这不是通过项，必须显式报出，避免误判「召回变少」。
        print(
            f"  NOTE dense 召回 {len(hits)} 条：库中向量全为 NULL，"
            "dense 一路按预期召回 0 条（非通过项，回填向量前检测不到该路）"
        )
    elif len(hits) == 0:
        checker.bad("dense 有已嵌入行却召回 0 条", "检查 HNSW 索引与会话 GUC")
    else:
        checker.ok(f"dense 召回 {len(hits)} 条（库中已嵌入 {embedded} 行）")
    if hits and len(hits) != min(embedded, M0_PARAMS.dense_k):
        checker.bad(
            "dense 召回数与可检索行不匹配",
            f"期望 {min(embedded, M0_PARAMS.dense_k)}，实际 {len(hits)}",
        )

    # 迭代索引扫描 + ef_search：realm 过滤无法下推进 HNSW 索引，窄域时靠这两项补召回。
    expected_gucs = {
        "iterative_scan": "relaxed_order",
        "max_scan_tuples": "20000",
        "ef_search": "100",
    }
    with session_factory() as session:
        actual_gucs = {
            name: str(session.execute(text(f"SHOW hnsw.{name}")).scalar())
            for name in expected_gucs
        }
    if actual_gucs == expected_gucs:
        checker.ok(f"HNSW 会话 GUC 已下发：{actual_gucs}")
    else:
        checker.bad(
            "HNSW 会话 GUC 与 M0-00 §5 不一致",
            f"期望 {expected_gucs}，实际 {actual_gucs}",
        )


def skip_dense_check(checker: Checker) -> None:
    section("1 向量可检索行：embedding IS NOT NULL 的现状")
    print(
        "  NOTE corpus 模式没有库连接：dense 的 SQL 过滤、NULL 统计与 HNSW 会话 GUC 未验证；"
        "这三项需要 POSTGRES_PASSWORD，用默认 --source db 跑。"
    )


def check_bm25_realm_equivalence(
    index: Bm25Index,
    records: Sequence[ChunkRecord],
    progress: int,
    query: str,
    checker: Checker,
) -> None:
    section("2 in-realm 排名同源：full 与 past 下 BM25 排名一致")
    chapter_of = {record.chunk_key: record.chapter_index for record in records}
    full = index.search(query, k=M0_PARAMS.kw_k, allowed_keys=None)
    in_realm_keys = {key for key, chapter in chapter_of.items() if chapter <= progress}
    past = index.search(query, k=M0_PARAMS.kw_k, allowed_keys=in_realm_keys)

    full_in_realm = [hit for hit in full if chapter_of[hit.chunk_key] <= progress]
    print(
        f"  query={query!r} progress={progress}："
        f"full 命中 {len(full)}（其中 in-realm {len(full_in_realm)}），past 命中 {len(past)}"
    )
    if not full_in_realm:
        checker.bad("full 下没有 in-realm 命中", "换一个 query 或调大 progress")
        return

    prefix = past[: len(full_in_realm)]
    same_order = [hit.chunk_key for hit in full_in_realm] == [hit.chunk_key for hit in prefix]
    same_scores = all(
        left.score == right.score for left, right in zip(full_in_realm, prefix, strict=True)
    )
    if same_order and same_scores:
        checker.ok(
            "in-realm 排名与分数逐条一致"
            f"（共享 {len(full_in_realm)} 条；full 的 in-realm 是 past 的前缀）"
        )
    else:
        checker.bad(
            "BM25 统计量随 realm 漂移",
            "同一 chunk 在 full / past 下名次或分数不同；索引必须在全书上构建，realm 只过滤候选",
        )


async def collect_outcomes(
    pipeline: RetrievalPipeline,
    queries: Sequence[str],
    *,
    level: RealmLevel,
    progress: int | None,
    limit: int = 40,
) -> list[tuple[str, RetrievalOutcome]]:
    outcomes: list[tuple[str, RetrievalOutcome]] = []
    for query in queries[:limit]:
        request = QueryRequest(book_id=1, question=query, level=level, progress=progress)
        try:
            outcomes.append((query, await pipeline.retrieve(request)))
        except Exception as exc:  # 验证脚本要把任何失败原因打出来，不因单条查询中断
            print(f"  query={query!r} 跳过：{exc}")
    return outcomes


def find_cap_sample(
    outcomes: Sequence[tuple[str, RetrievalOutcome]], reason: str, checker: Checker, label: str
) -> None:
    for query, outcome in outcomes:
        matches = [item for item in outcome.dropped if item.reason == reason]
        if matches:
            sample = matches[0]
            checker.ok(
                f"{label}被触发：query={query!r}，{sample.chunk_key} 记 {reason}"
                f"（该原因共 {len(matches)} 条）"
            )
            return
    checker.bad(f"{label}未被任何候选查询触发", f"固定候选里没有出现 reason={reason}")


def check_neighbors(
    records: Sequence[ChunkRecord],
    outcomes: Sequence[tuple[str, RetrievalOutcome]],
    checker: Checker,
) -> None:
    section("4 邻块补位：prev 优先、固定一跳、不跨章、不递归")
    by_key = {record.chunk_key: record for record in records}
    sample: tuple[str, RetrievalOutcome] | None = None
    for query, outcome in outcomes:
        if any(item.source == "neighbor" for item in outcome.assembled):
            sample = (query, outcome)
            break
    if sample is None:
        checker.bad("没有找到含邻块补位的装配样例", "换一个 query 或核对 neighbor_expand")
        return

    query, outcome = sample
    hits = {item.chunk_key for item in outcome.assembled if item.source == "hit"}
    neighbors = [item for item in outcome.assembled if item.source == "neighbor"]

    direction_ok = True
    chapter_ok = True
    hop_ok = True
    for item in neighbors:
        anchor = by_key[item.from_hit_chunk_key]
        target = by_key[item.chunk_key]
        chapter_ok &= target.chapter_index == anchor.chapter_index
        hop_ok &= abs(target.chunk_index - anchor.chunk_index) == 1
        expected = (
            anchor.prev_chunk_key if anchor.prev_chunk_key is not None else anchor.next_chunk_key
        )
        direction_ok &= item.chunk_key == expected

    recursive_ok = all(item.from_hit_chunk_key in hits for item in neighbors)
    recursive_ok &= not any(
        other.from_hit_chunk_key == item.chunk_key
        for item in neighbors
        for other in outcome.assembled
    )

    print(f"  样例 query={query!r}：邻块 {len(neighbors)} 条")
    if direction_ok and hop_ok and chapter_ok:
        checker.ok("邻块为直接 prev（无 prev 时取 next），且不跨章、固定一跳")
    else:
        checker.bad(
            "邻块方向 / 跳数 / 同章校验失败",
            f"direction={direction_ok} hop={hop_ok} chapter={chapter_ok}",
        )
    if recursive_ok:
        checker.ok("邻块不回指其它邻块（不递归、不形成链）")
    else:
        checker.bad("邻块出现递归或 from_hit 悬空", "from_hit_chunk_key 必须指向入选的 hit")


def check_leak(outcome: RetrievalOutcome, progress: int, checker: Checker) -> None:
    section("5 leak 硬门禁：past 模式逐阶段越界章节数")
    stages = {
        "dense": outcome.dense,
        "kw": outcome.kw,
        "fused": outcome.fused,
        "rerank": outcome.reranked,
        "assembled": outcome.assembled,
    }
    total_leaks = 0
    for name, hits in stages.items():
        leaks = [hit.chunk_key for hit in hits if hit.chapter_index > progress]
        total_leaks += len(leaks)
        print(f"  {name}: {len(hits)} 条，越界 {len(leaks)}")
    if total_leaks == 0:
        checker.ok(f"progress={progress} 下所有阶段越界章节数 = 0")
    else:
        checker.bad("past 模式泄漏 progress 之后的章节", f"越界 {total_leaks} 条")


async def main() -> int:
    parser = argparse.ArgumentParser(description="M0-4 检索链确定性验证")
    parser.add_argument("--book-id", type=int, default=1)
    parser.add_argument("--progress", type=int, default=100, help="leak / realm 同源用例的进度")
    parser.add_argument(
        "--source",
        choices=["db", "corpus"],
        default="db",
        help="db=读真库 chunks（默认）；corpus=直接从仓库内语料分块，免库凭据",
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=DEFAULT_CORPUS_ROOT,
        help="corpus 模式下的语料根目录",
    )
    args = parser.parse_args()

    checker = Checker()

    if args.source == "db":
        session_factory = sessionmaker(create_engine_from_env(), expire_on_commit=False)
        records: Sequence[ChunkRecord] = PgChunkStore(session_factory).load_chunks(args.book_id)
        source_label = "真库 chunks"
        missing_hint = "先跑 bash scripts/import-corpus.sh"

        async def run_dense_check() -> None:
            await check_dense_recall(session_factory, records, args.book_id, checker)

        pipeline = build_pipeline(
            PgChunkStore(session_factory), PgVectorDenseIndex(session_factory)
        )
    else:
        records = load_records_from_corpus(args.corpus_root, args.book_id)
        source_label = f"语料分块（{args.corpus_root}，无库连接）"
        missing_hint = "检查 --corpus-root 是否指向含 index.jsonl 的语料目录"

        async def run_dense_check() -> None:
            skip_dense_check(checker)

        pipeline = build_pipeline(_CorpusStore(records), _EmptyDenseIndex())

    if not records:
        print(f"失败：book_id={args.book_id} 没有 chunk，{missing_hint}", file=sys.stderr)
        return 2
    chapter_max = max(record.chapter_index for record in records)
    progress = min(args.progress, chapter_max)

    section("0 语料与检索链装配")
    print(
        f"  {source_label}：book_id={args.book_id}，chunk {len(records)} 个，"
        f"章节 1..{chapter_max}，progress={progress}"
    )
    print("  provider：FakeEmbeddingModel + 保序假 rerank（无真实 API 调用）")

    await run_dense_check()

    index = Bm25Index(
        [record.chunk_key for record in records],
        [record.content for record in records],
    )
    # BM25 索引一次构建、统计量取自全书：full 与 past 共用同一个索引实例。
    query = FALLBACK_QUERIES[0]
    check_bm25_realm_equivalence(index, records, progress, normalize_query(query), checker)

    candidates = [
        *FALLBACK_QUERIES,
        *concentrated_queries(records),
    ]
    outcomes = await collect_outcomes(
        pipeline, candidates, level=RealmLevel.FULL, progress=None
    )

    section("3 装配 cap 三项")
    find_cap_sample(outcomes, REASON_CHAPTER_CAP, checker, "章上限（ask_max_chapters=8）")
    find_cap_sample(
        outcomes, REASON_CHAPTER_CHUNK_CAP, checker, "每章段数（ask_chunks_per_chapter=2）"
    )
    find_cap_sample(outcomes, REASON_TOP_K_CAP, checker, "最终段数（ask_top_k=8）")

    check_neighbors(records, outcomes, checker)

    past_outcomes = await collect_outcomes(
        pipeline,
        [query, *concentrated_queries(records, limit=3)],
        level=RealmLevel.PAST,
        progress=progress,
        limit=4,
    )
    if not past_outcomes:
        checker.bad("past 模式没有可用样例", "换 query 或调 progress")
    else:
        check_leak(past_outcomes[0][1], progress, checker)

    print(f"\n=== 汇总：{checker.passed} 项通过，{checker.failed} 项失败 ===")
    if checker.failed == 0:
        print("M0-4 检索链确定性验证通过（dense 现状已在 §1 显式报出）。")
    return 1 if checker.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
