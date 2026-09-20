#!/usr/bin/env python
"""M0-5 回答链冒烟：检索 → 装配 → prompt → 流式生成 → 引用 → 两个适配器。

默认全程用假 provider、直接从仓库内语料分块，不发真实 API 调用、不连库；`--real` 才把
回答模型换成 GLM 适配器（需 `GLM_API_KEY`，经 `keymgr run glm-rag` 注入，由用户单独批准）。

脚本跑的是同一条真实 `AnsweringRunner` 事件流，因此它验证的不只是 GLM 适配器：

1. **事件顺序不变量**：`query_started` 第一、`query_done` 最后、`answer_delta` 只在
   `generation_started` 之后。
2. **两个适配器表达同一件事**：同一份事件流，JSON 折叠体的 answer / status /
   context_chapters / usage 与 SSE 帧逐项对齐，SSE 以 `data: [DONE]` 终止。
3. **拒答**：装配集为空 → `insufficient_evidence`、`answer` 是服务端固定话术、模型未被调用。
4. **provider 故障不降级成拒答**：生成中途超时 → `query_error` 为 `RAG_TIMEOUT`，JSON 折叠
   抛出 504，且事件流里不出现 `insufficient_evidence`。

用法（仓库根执行）：
    bash scripts/verify-answering.sh
    # 真实回答模型（需先批准并注入凭据）：
    keymgr run glm-rag bash scripts/verify-answering.sh --real
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from omniread.api.adapters import JsonResponseAdapter, SseResponseAdapter
from omniread.application.query_service import REFUSAL_ANSWER, AnsweringRunner
from omniread.domain.errors import RagTimeout
from omniread.domain.events import EventName, RagEvent
from omniread.domain.models import ContextChunk, QueryRequest, RealmLevel
from omniread.infrastructure.objectstore.corpus import read_corpus
from omniread.infrastructure.providers import (
    ChatChunk,
    ChatMessage,
    ChatModel,
    ChatOptions,
    FakeChatModel,
    FakeEmbeddingModel,
    FakeRerankModel,
    GlmChatAdapter,
    ProviderConfigError,
    ProviderTimeoutError,
)
from omniread.pipelines.importing import ChunkPlan, build_import_plan
from omniread.pipelines.retrieval.pipeline import RetrievalPipeline
from omniread.pipelines.retrieval.query import RealmBounds
from omniread.pipelines.retrieval.types import ChunkRecord, RetrievalOutcome

DEFAULT_CORPUS_ROOT = (
    Path(__file__).resolve().parent.parent / "asset" / "《不时轻声地以俄语遮羞的邻座艾莉同学》"
)

# 语料里高频出现的词，BM25 一定能召回到；语料换了要跟着换。
QUESTION = "艾莉 俄语"
REQUEST_ID = "req_0123456789abcdef0123456789abcdef"


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

    def check(self, condition: bool, message: str, detail: str = "") -> None:
        if condition:
            self.ok(message)
        else:
            self.bad(message, detail)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


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


class _ContextMap:
    """`ContextSource` 的内存替身：按 chunk_key 取正文与章标题。"""

    def __init__(self, chunks: Sequence[ContextChunk]) -> None:
        self._by_key = {chunk.chunk_key: chunk for chunk in chunks}

    def load(self, book_id: int, chunk_keys: Sequence[str]) -> Sequence[ContextChunk]:
        return [self._by_key[key] for key in chunk_keys if key in self._by_key]


class _EmptyRetrieval:
    """装配集为空的一次检索：复现「检索为空导致的拒答」。"""

    async def retrieve(self, request: QueryRequest) -> RetrievalOutcome:
        realm = RealmBounds(lo=1, hi=1)
        return RetrievalOutcome(
            query="",
            realm=realm,
            dense=(),
            kw=(),
            fused=(),
            reranked=(),
            assembled=(),
            dropped=(),
            token_estimate=0,
        )


class _TimeoutChat:
    """产出开头后抛 provider 超时，模拟生成中途故障。"""

    model = "glm-5.3-flash"

    async def stream(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncIterator[ChatChunk]:
        yield ChatChunk(text="开了个头")
        raise ProviderTimeoutError("provider 超时", provider="glm")


def load_corpus_chunks(
    corpus_root: Path, book_id: int
) -> tuple[list[ChunkRecord], list[ContextChunk]]:
    """从仓库内语料重建检索视图与上下文视图；prev/next 按导入同一条规则回填。"""
    plan = build_import_plan(read_corpus(corpus_root, book_id=book_id))
    title_of = {chapter.chapter_index: chapter.title for chapter in plan.chapters}
    by_chapter: dict[str, list[ChunkPlan]] = {}
    for chunk in plan.chunks:
        by_chapter.setdefault(chunk.chapter_id, []).append(chunk)

    records: list[ChunkRecord] = []
    contexts: list[ContextChunk] = []
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
                    prev_chunk_key=(
                        ordered[position - 1].chunk_key if position > 0 else None
                    ),
                    next_chunk_key=(
                        ordered[position + 1].chunk_key
                        if position + 1 < len(ordered)
                        else None
                    ),
                )
            )
            contexts.append(
                ContextChunk(
                    chunk_key=chunk.chunk_key,
                    chapter_index=chunk.chapter_index,
                    chapter_title=title_of.get(chunk.chapter_index, ""),
                    text=chunk.content,
                )
            )
    records.sort(key=lambda record: (record.chapter_index, record.chunk_index))
    return records, contexts


def parse_sse_frames(raw: str) -> list[tuple[str | None, str]]:
    """把 SSE 全文拆成 (event, data)；`[DONE]` 帧没有 event 行。"""
    frames: list[tuple[str | None, str]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event: str | None = None
        data = ""
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        frames.append((event, data))
    return frames


async def _replay(events: Sequence[RagEvent]) -> AsyncIterator[RagEvent]:
    for event in events:
        yield event


async def collect(runner: AnsweringRunner, request: QueryRequest) -> list[RagEvent]:
    return [event async for event in runner.run(request, REQUEST_ID)]


def check_order(events: Sequence[RagEvent], checker: Checker, *, label: str) -> None:
    names = [event.name for event in events]
    checker.check(names[0] is EventName.QUERY_STARTED, f"{label}：query_started 第一")
    checker.check(
        names[-1] in (EventName.QUERY_DONE, EventName.QUERY_ERROR),
        f"{label}：终止事件最后",
    )
    if EventName.ANSWER_DELTA in names:
        first = names.index(EventName.ANSWER_DELTA)
        has_generation = EventName.GENERATION_STARTED in names
        checker.check(
            has_generation and names.index(EventName.GENERATION_STARTED) < first,
            f"{label}：answer_delta 都在 generation_started 之后",
        )


async def check_answered(
    pipeline: RetrievalPipeline,
    contexts: Sequence[ContextChunk],
    chat: ChatModel,
    checker: Checker,
    *,
    provider: str,
) -> str:
    runner = AnsweringRunner(
        retrieval=pipeline,
        context=_ContextMap(contexts),
        chat=chat,
        answer_provider=provider,
    )
    request = QueryRequest(book_id=1, question=QUESTION, level=RealmLevel.FULL)
    events = await collect(runner, request)

    check_order(events, checker, label="作答")

    response = await JsonResponseAdapter.fold(_replay(events), request_id=REQUEST_ID)
    frames = [
        frame async for frame in SseResponseAdapter.stream(_replay(events), request_id=REQUEST_ID)
    ]
    parsed = parse_sse_frames("".join(frames))
    deltas = [
        event.payload["text"] for event in events if event.name is EventName.ANSWER_DELTA
    ]
    generation = next(event for event in events if event.name is EventName.GENERATION_STARTED)

    print(
        f"  prompt_version={generation.payload['prompt_version']} "
        f"answer_model={generation.payload['answer_model']}"
    )
    print(f"  context_chapters={[c.chapter_index for c in response.context_chapters]}")
    checker.check(response.status == "answered", "作答：status=answered")
    checker.check(
        bool(response.context_chapters), "作答：context_chapters 非空（检索到了上下文）"
    )
    checker.check(
        response.answer == "".join(deltas),
        "作答：JSON 折叠的 answer 等于流式增量拼接",
    )
    checker.check(
        [name for name, _ in parsed] == [*(event.name.value for event in events), None],
        "作答：SSE 帧顺序与事件流逐条一致",
    )
    checker.check(
        parsed[-1][1] == "[DONE]", "作答：SSE 以 data: [DONE] 终止"
    )
    done = json.loads(parsed[-2][1])
    checker.check(
        done["status"] == response.status
        and done["context_chapters"]
        == [chapter.model_dump() for chapter in response.context_chapters]
        and done["usage"] == response.usage.model_dump(),
        "作答：两个适配器表达同一件事（status / context_chapters / usage）",
    )
    return response.answer


async def check_refusal(contexts: Sequence[ContextChunk], checker: Checker) -> None:
    chat = FakeChatModel(answer="模型不该被调用")
    runner = AnsweringRunner(
        retrieval=_EmptyRetrieval(),
        context=_ContextMap(contexts),
        chat=chat,
        answer_provider="fake",
    )
    request = QueryRequest(book_id=1, question=QUESTION, level=RealmLevel.FULL)
    events = await collect(runner, request)

    check_order(events, checker, label="拒答")
    response = await JsonResponseAdapter.fold(_replay(events), request_id=REQUEST_ID)
    deltas = [
        event.payload["text"] for event in events if event.name is EventName.ANSWER_DELTA
    ]

    print(f"  拒答 answer={response.answer!r}")
    checker.check(
        response.status == "insufficient_evidence",
        "拒答：status=insufficient_evidence（HTTP 200 的正常业务结果）",
    )
    checker.check(
        deltas == [REFUSAL_ANSWER] and response.answer == REFUSAL_ANSWER,
        "拒答：answer 是服务端固定话术",
    )
    checker.check(response.context_chapters == [], "拒答：检索为空 → context_chapters=[]")
    checker.check(chat.calls == [], "拒答：模型未被调用")


async def check_provider_fault(
    pipeline: RetrievalPipeline, contexts: Sequence[ContextChunk], checker: Checker
) -> None:
    runner = AnsweringRunner(
        retrieval=pipeline,
        context=_ContextMap(contexts),
        chat=_TimeoutChat(),
        answer_provider="glm",
    )
    request = QueryRequest(book_id=1, question=QUESTION, level=RealmLevel.FULL)
    events = await collect(runner, request)
    names = [event.name for event in events]
    payload_dump = json.dumps([event.payload for event in events], ensure_ascii=False)

    checker.check(names[-1] is EventName.QUERY_ERROR, "故障：末事件是 query_error")
    checker.check(
        EventName.QUERY_DONE not in names, "故障：没有 query_done（不伪装成正常结束）"
    )
    checker.check(
        "insufficient_evidence" not in payload_dump and "answered" not in payload_dump,
        "故障：事件流里没有拒答 / 作答状态（不降级成拒答）",
    )
    checker.check(
        events[-1].payload["code"] == "RAG_TIMEOUT", "故障：code=RAG_TIMEOUT（超时 504）"
    )
    try:
        await JsonResponseAdapter.fold(_replay(events), request_id=REQUEST_ID)
    except RagTimeout as exc:
        checker.check(exc.http_status == 504, "故障：JSON 适配器抛 504")
    else:
        checker.bad("故障：JSON 适配器没有抛错", "超时必须以 5xx 收尾")


async def real_run(
    pipeline: RetrievalPipeline, contexts: Sequence[ContextChunk], checker: Checker
) -> int:
    try:
        adapter = GlmChatAdapter()
    except ProviderConfigError as exc:
        print(f"失败：{exc.message}", file=sys.stderr)
        print("真实冒烟需要 GLM_API_KEY：用 keymgr run glm-rag 注入后重试。", file=sys.stderr)
        return 2
    print(f"[real] 真实调用 {adapter.model}（会消耗额度）")
    try:
        answer = await check_answered(
            pipeline, contexts, adapter, checker, provider="glm"
        )
        print(f"[real] answer={answer}")
    finally:
        await adapter.aclose()
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="M0-5 回答链冒烟（默认假 provider）")
    parser.add_argument(
        "--real",
        action="store_true",
        help="回答模型换成真实 GLM（需 GLM_API_KEY，且需用户明确批准）",
    )
    parser.add_argument("--book-id", type=int, default=1)
    parser.add_argument(
        "--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT
    )
    args = parser.parse_args()

    records, contexts = load_corpus_chunks(args.corpus_root, args.book_id)
    if not records:
        print(
            f"失败：{args.corpus_root} 没有可用语料，检查 --corpus-root 是否含 index.jsonl",
            file=sys.stderr,
        )
        return 2

    checker = Checker()
    pipeline = RetrievalPipeline(
        store=_CorpusStore(records),
        dense=_EmptyDenseIndex(),
        embedder=FakeEmbeddingModel(),
        reranker=FakeRerankModel(),
    )

    section("0 语料与链路装配")
    print(
        f"  语料分块：book_id={args.book_id}，chunk {len(records)} 个，"
        f"章节 1..{max(record.chapter_index for record in records)}"
    )
    print("  provider：FakeEmbeddingModel + FakeRerankModel + 假 chat（无真实 API 调用）")

    if args.real:
        return await real_run(pipeline, contexts, checker)

    section("1 作答路径：事件流 → 两个适配器")
    probe = await pipeline.retrieve(
        QueryRequest(book_id=1, question=QUESTION, level=RealmLevel.FULL)
    )
    if not probe.assembled:
        print(f"失败：query={QUESTION!r} 没有装配出上下文，换一个候选词", file=sys.stderr)
        return 2
    chapters = sorted({item.chapter_index for item in probe.assembled})
    answer = (
        f"根据材料，第 {chapters[0]} 章给出了相关信息 [C{chapters[0]}]，"
        f"另一处见 [C{chapters[-1]}]。"
    )
    await check_answered(
        pipeline, contexts, FakeChatModel(answer=answer, chunk_size=5), checker, provider="fake"
    )

    section("2 拒答路径")
    await check_refusal(contexts, checker)

    section("3 provider 故障路径")
    await check_provider_fault(pipeline, contexts, checker)

    print(f"\n=== 汇总：{checker.passed} 项通过，{checker.failed} 项失败 ===")
    if checker.failed == 0:
        print("M0-5 回答链冒烟通过（假 provider，未发真实调用）。")
    return 1 if checker.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
