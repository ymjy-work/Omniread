"""答案层评测编排：逐题作答 → 折叠事件流 → 逐题记录 → 汇总 → 产物。

全用内存替身与假 provider，不发真实调用、不连库。这里要验的是**编排**：
每题拿到的是不是那一题的装配集、允许引用的章号是不是取自运行时自报的 `context_chapters`、
以及产物落盘时有没有夹带正文的位置。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from omniread.application.query_service import REFUSAL_ANSWER, AnsweringRunner
from omniread.domain.models import ContextChunk, QueryRequest, RealmLevel
from omniread.infrastructure.providers.base import (
    ChatChunk,
    ChatMessage,
    ChatOptions,
    ChatResponse,
)
from omniread.pipelines.answering import REFUSAL_MARKER
from omniread.pipelines.assembly import AssembledChunk
from omniread.pipelines.evaluation.artifacts import (
    EvalRunConfig,
    write_eval_run_dir,
)
from omniread.pipelines.evaluation.generation_runner import (
    RecordedRetrieval,
    eval_request_id,
    run_generation_eval,
)
from omniread.pipelines.evaluation.types import (
    STATUS_ANSWERED,
    STATUS_INSUFFICIENT_EVIDENCE,
)
from omniread.pipelines.mapping.artifacts import check_run_dir
from omniread.pipelines.retrieval.query import RealmBounds
from omniread.pipelines.retrieval.types import RetrievalOutcome, StageHit

REALM = RealmBounds(lo=1, hi=193)
PROMPT_VERSION = "deadbeef1234"


def _key(chapter: int, index: int = 0) -> str:
    return f"book:1:chapter:{chapter}#c{index}"


def _assembled(chapter: int) -> AssembledChunk:
    return AssembledChunk(
        chunk_key=_key(chapter),
        chapter_index=chapter,
        chunk_index=0,
        source="hit",
        from_hit_chunk_key=_key(chapter),
        token_count=100,
        rank=chapter,
    )


def _outcome(chapters: Sequence[int]) -> RetrievalOutcome:
    assembled = tuple(_assembled(chapter) for chapter in chapters)
    hits = tuple(
        StageHit(
            chunk_key=item.chunk_key,
            chapter_index=item.chapter_index,
            score=0.9,
            rank=item.rank,
        )
        for item in assembled
    )
    return RetrievalOutcome(
        query="问题",
        realm=REALM,
        dense=hits,
        kw=hits,
        fused=hits,
        reranked=hits,
        assembled=assembled,
        dropped=(),
        token_estimate=100 * len(assembled),
    )


class StubContext:
    def load(self, book_id: int, chunk_keys: Sequence[str]) -> Sequence[ContextChunk]:
        return [
            ContextChunk(
                chunk_key=key,
                chapter_index=int(key.split(":")[3].split("#")[0]),
                chapter_title="标题",
                text="正文内容",
            )
            for key in chunk_keys
        ]


class StubRetrieval:
    def __init__(self, by_question: dict[str, RetrievalOutcome]) -> None:
        self._by_question = by_question

    async def retrieve(self, request: QueryRequest) -> RetrievalOutcome:
        return self._by_question[request.question]


def _question(
    question_id: str,
    question: str,
    *,
    expect_refusal: bool = False,
    qtype: str = "fact",
) -> dict:
    return {
        "id": question_id,
        "type": qtype,
        "difficulty": "easy",
        "level": "past",
        "progress": 50,
        "question": question,
        "expect_refusal": expect_refusal,
    }


class PerQuestionChat:
    """按题面返回不同答案的假回答模型：本文件要验的是逐题编排，不是模型行为。

    `chunk_size` 默认 1，让标记与引用都被切成多个分片——判定跨块的路径才是真跑的那条。
    """

    model = "per-question-chat"

    def __init__(self, answers: dict[str, str], *, chunk_size: int = 1) -> None:
        self._answers = answers
        self._chunk_size = chunk_size
        self.calls: list[tuple[ChatMessage, ...]] = []

    def _answer_for(self, messages: Sequence[ChatMessage]) -> str:
        user = messages[-1].content
        for question, answer in self._answers.items():
            if question in user:
                return answer
        raise AssertionError(f"没有为这条提问准备答案：{user[:80]!r}")

    async def stream(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncIterator[ChatChunk]:
        self.calls.append(tuple(messages))
        answer = self._answer_for(messages)
        for start in range(0, len(answer), self._chunk_size):
            yield ChatChunk(text=answer[start : start + self._chunk_size])

    async def complete(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> ChatResponse:  # pragma: no cover - 问答链只走流式
        raise NotImplementedError


async def test_each_question_is_answered_against_its_own_assembled_set() -> None:
    questions = [_question("fact-001", "甲问"), _question("fact-002", "乙问")]
    chat = PerQuestionChat({"甲问": "见 [C17]。", "乙问": "见 [C45]。"})
    runner = AnsweringRunner(
        retrieval=StubRetrieval(
            {"甲问": _outcome([17]), "乙问": _outcome([45])}
        ),
        context=StubContext(),
        chat=chat,
        answer_provider="fake",
    )

    result = await run_generation_eval(
        questions=questions,
        runner=runner,
        answer_provider="fake",
        answer_model=chat.model,
        prompt_version=PROMPT_VERSION,
    )

    assert [r.question_id for r in result.records] == ["fact-001", "fact-002"]
    # 引用的都是**自己那题**的章：交叉喂装配集会让两条都变成越界。
    assert all(r.citation_in_set for r in result.records)
    assert all(r.status == STATUS_ANSWERED for r in result.records)
    assert result.summary["citation_in_set"] == 1.0
    assert result.summary["citation_in_set_denominator"] == 2


async def test_out_of_range_citation_lands_in_the_record_and_the_summary() -> None:
    questions = [_question("fact-001", "甲问")]
    chat = PerQuestionChat({"甲问": "见 [C99]。"})
    runner = AnsweringRunner(
        retrieval=StubRetrieval({"甲问": _outcome([17])}),
        context=StubContext(),
        chat=chat,
        answer_provider="fake",
    )

    result = await run_generation_eval(
        questions=questions,
        runner=runner,
        answer_provider="fake",
        answer_model=chat.model,
        prompt_version=PROMPT_VERSION,
    )

    record = result.records[0]
    assert record.citation_in_set is False
    assert record.citation_out_of_range == ("[C99]",)
    assert result.summary["citation_in_set"] == 0.0
    assert result.summary["citation_out_of_range_total"] == 1


async def test_refusal_question_that_refuses_counts_as_correct() -> None:
    questions = [
        _question("spoiler-001", "甲问", expect_refusal=True, qtype="spoiler"),
        _question("fact-001", "乙问"),
    ]
    chat = PerQuestionChat({"甲问": REFUSAL_MARKER, "乙问": "见 [C17]。"})
    runner = AnsweringRunner(
        retrieval=StubRetrieval({"甲问": _outcome([17]), "乙问": _outcome([17])}),
        context=StubContext(),
        chat=chat,
        answer_provider="fake",
    )

    result = await run_generation_eval(
        questions=questions,
        runner=runner,
        answer_provider="fake",
        answer_model=chat.model,
        prompt_version=PROMPT_VERSION,
    )

    refusals = {r.question_id: r for r in result.records}
    assert refusals["spoiler-001"].status == STATUS_INSUFFICIENT_EVIDENCE
    assert result.summary["refusal_correct"] == 1.0
    assert result.summary["refusal_denominator"] == 1
    assert result.summary["refusal_false_positive"] == 0


async def test_request_ids_are_derived_from_question_ids() -> None:
    # 随机 id 会让同一个 run 两次跑出不同产物，重算就对不上了。
    questions = [_question("fact-001", "甲问")]
    chat = PerQuestionChat({"甲问": "见 [C17]。"})
    runner = AnsweringRunner(
        retrieval=StubRetrieval({"甲问": _outcome([17])}),
        context=StubContext(),
        chat=chat,
        answer_provider="fake",
    )

    result = await run_generation_eval(
        questions=questions,
        runner=runner,
        answer_provider="fake",
        answer_model=chat.model,
        prompt_version=PROMPT_VERSION,
    )

    assert eval_request_id("fact-001") == "eval-fact-001"
    assert result.records[0].request_id == "eval-fact-001"


# ---- 检索结果回放 ----------------------------------------------------------


async def test_recorded_retrieval_replays_instead_of_re_running() -> None:
    request = QueryRequest(book_id=1, question="甲问", level=RealmLevel.PAST, progress=50)
    outcome = _outcome([17])
    replay = RecordedRetrieval({request: outcome})

    assert await replay.retrieve(request) is outcome


async def test_recorded_retrieval_fails_loudly_on_a_missing_request() -> None:
    # 静默退回空上下文会把「检索结果丢了」伪装成「模型拒答」，两个指标同时失真。
    replay = RecordedRetrieval({})
    request = QueryRequest(book_id=1, question="甲问", level=RealmLevel.PAST, progress=50)

    with pytest.raises(LookupError, match="甲问"):
        await replay.retrieve(request)


# ---- 产物 ------------------------------------------------------------------


def _config() -> EvalRunConfig:
    return EvalRunConfig(
        run_id="test-run",
        kind="full",
        phase="retrieval+generation",
        dataset_hash="d" * 12,
        dataset_version="m0.1.0",
        corpus_manifest_hash="c" * 12,
        chunking_version="m0-placeholder-v1",
        tokenizer_id="tokenizers:test",
        chunk_source="db",
        retrieval_provider="fake",
        embedding_provider="fake",
        embedding_model="fake-embedding",
        embedding_dim=1024,
        rerank_provider="fake",
        rerank_model="fake-rerank",
        answer_provider="fake",
        answer_model="fake-chat",
        prompt_version=PROMPT_VERSION,
    )


async def test_run_dir_carries_generation_scores_and_stays_within_the_redline(
    tmp_path: Path,
) -> None:
    questions = [_question("fact-001", "甲问")]
    chat = PerQuestionChat({"甲问": "见 [C99]。"})
    runner = AnsweringRunner(
        retrieval=StubRetrieval({"甲问": _outcome([17])}),
        context=StubContext(),
        chat=chat,
        answer_provider="fake",
    )
    result = await run_generation_eval(
        questions=questions,
        runner=runner,
        answer_provider="fake",
        answer_model=chat.model,
        prompt_version=PROMPT_VERSION,
    )

    run_dir = tmp_path / "run"
    write_eval_run_dir(
        run_dir,
        config=_config(),
        generation_records=result.records,
        summary={"question_count": 1, "generation": result.summary},
        failures=result.failures,
    )

    assert check_run_dir(run_dir) == []
    row = json.loads(
        (run_dir / "generation.scores.jsonl").read_text(encoding="utf-8").strip()
    )
    # 字段集就是入库白名单：回答原文没有地方可放。
    assert "answer" not in row
    assert row["citation_out_of_range"] == ["[C99]"]
    assert row["status"] == STATUS_ANSWERED


async def test_summary_markdown_renders_the_answer_section(tmp_path: Path) -> None:
    questions = [_question("fact-001", "甲问")]
    chat = PerQuestionChat({"甲问": REFUSAL_MARKER})
    runner = AnsweringRunner(
        retrieval=StubRetrieval({"甲问": _outcome([17])}),
        context=StubContext(),
        chat=chat,
        answer_provider="fake",
    )
    result = await run_generation_eval(
        questions=questions,
        runner=runner,
        answer_provider="fake",
        answer_model=chat.model,
        prompt_version=PROMPT_VERSION,
    )

    run_dir = tmp_path / "run"
    write_eval_run_dir(
        run_dir,
        config=_config(),
        generation_records=result.records,
        summary={"question_count": 1, "generation": result.summary},
        failures=result.failures,
    )

    report = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "## 答案层" in report
    assert "refusal_false_positive" in report
    # 报告只有计数与比率：拒答话术是服务端文本，但它同样是「回答正文」，不进产物。
    assert REFUSAL_ANSWER not in report
