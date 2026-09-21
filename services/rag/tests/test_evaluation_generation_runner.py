"""生成层编排：失败隔离、断点续跑、以及「正文只落 temp/」这条红线。

全部用内存替身与假 provider，不发真实调用、不连库。这里不测模型答得好不好
（那是 judge 的事，M0-8 才做），只测**编排**：故障会不会吃掉整轮、续跑会不会
重复花钱、正文会不会漏进 `eval/`。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from omniread.application.query_service import REFUSAL_ANSWER, AnsweringRunner
from omniread.domain.models import ContextChunk, QueryRequest
from omniread.infrastructure.providers.base import ChatChunk, ChatMessage, ChatOptions
from omniread.infrastructure.providers.errors import ProviderTimeoutError
from omniread.infrastructure.providers.fake import FakeChatModel
from omniread.pipelines.assembly import AssembledChunk
from omniread.pipelines.evaluation.artifacts import (
    MIXED_ACROSS_QUESTIONS,
    NOT_EXERCISED,
)
from omniread.pipelines.evaluation.generation_runner import (
    TRANSCRIPT_FILENAME,
    CapturingContextSource,
    load_transcripts,
    record_from_transcript,
    run_generation_eval,
)
from omniread.pipelines.evaluation.types import (
    STATUS_ANSWERED,
    STATUS_GENERATION_FAILED,
    STATUS_INSUFFICIENT_EVIDENCE,
)
from omniread.pipelines.retrieval.query import RealmBounds
from omniread.pipelines.retrieval.types import RetrievalOutcome, StageHit

REALM = RealmBounds(lo=1, hi=193)
MATERIAL = "第十七章的正文内容，这段只能进 temp/。"


def _key(chapter: int) -> str:
    return f"book:1:chapter:{chapter}#c0"


def _hit(key: str, chapter: int) -> StageHit:
    return StageHit(chunk_key=key, chapter_index=chapter, score=0.9, rank=1)


def _assembled(chapter: int) -> AssembledChunk:
    return AssembledChunk(
        chunk_key=_key(chapter),
        chapter_index=chapter,
        chunk_index=0,
        source="hit",
        from_hit_chunk_key=_key(chapter),
        token_count=100,
        rank=1,
    )


def _chunk(chapter: int) -> ContextChunk:
    return ContextChunk(
        chunk_key=_key(chapter),
        chapter_index=chapter,
        chapter_title=f"第{chapter}章 标题",
        text=MATERIAL,
    )


class StubRetrieval:
    def __init__(self, chapters: Sequence[int], error: Exception | None = None) -> None:
        self._chapters = chapters
        self._error = error

    async def retrieve(self, request: QueryRequest) -> RetrievalOutcome:
        if self._error is not None:
            raise self._error
        assembled = tuple(_assembled(c) for c in self._chapters)
        hits = tuple(_hit(item.chunk_key, item.chapter_index) for item in assembled)
        return RetrievalOutcome(
            query=request.question,
            realm=REALM,
            dense=hits,
            kw=hits,
            fused=hits,
            reranked=hits,
            assembled=assembled,
            dropped=(),
            token_estimate=sum(item.token_count for item in assembled),
        )


class StubContext:
    """按 chunk_key 给出材料；键不在集合里就返回空（模拟库与检索视图不一致之外的情形）。"""

    def __init__(self, chapters: Sequence[int]) -> None:
        self._by_key = {_key(c): _chunk(c) for c in chapters}

    def load(self, book_id: int, chunk_keys: Sequence[str]) -> Sequence[ContextChunk]:
        return [self._by_key[key] for key in chunk_keys if key in self._by_key]


class ExplodingChat:
    """生成到一半就抛 provider 超时。"""

    model = "fake-chat"

    async def stream(
        self, messages: Sequence[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncIterator[ChatChunk]:
        yield ChatChunk(text="开了个头")
        raise ProviderTimeoutError("provider 超时", provider="fake")


def _question(**overrides: object) -> dict:
    base = {
        "id": "fact-001",
        "type": "fact",
        "difficulty": "easy",
        "level": "past",
        "progress": 100,
        "expect_refusal": False,
        "question": "政近为什么离开周家？",
    }
    base.update(overrides)
    return base


def _build(
    chapters: Sequence[int] = (17,),
    *,
    chat: object | None = None,
    retrieval_error: Exception | None = None,
) -> tuple[AnsweringRunner, CapturingContextSource]:
    context = CapturingContextSource(StubContext(chapters))
    runner = AnsweringRunner(
        retrieval=StubRetrieval(chapters, retrieval_error),
        context=context,
        chat=chat or FakeChatModel(answer="政近是因家族安排离开的 [C17]。"),  # type: ignore[arg-type]
        answer_provider="fake",
    )
    return runner, context


async def _run(
    tmp_path: Path,
    questions: Sequence[dict],
    *,
    chapters: Sequence[int] = (17,),
    chat: object | None = None,
    retrieval_error: Exception | None = None,
    resume: bool = False,
    run_id: str = "run-gen",
):
    runner, context = _build(chapters, chat=chat, retrieval_error=retrieval_error)
    return await run_generation_eval(
        run_id=run_id,
        questions=questions,
        runner=runner,
        context=context,
        transcript_path=tmp_path / TRANSCRIPT_FILENAME,
        dataset_hash="h",
        dataset_version="m0.1.0",
        corpus_manifest_hash="c",
        chunking_version="m0-placeholder-v1",
        tokenizer_id="t",
        answer_provider="fake",
        retrieval_provider="fake",
        embedding_provider="fake",
        embedding_model="fake-embed",
        embedding_dim=1024,
        rerank_provider="fake",
        rerank_model="fake-rerank",
        retrieval_params={"ask_top_k": 8},
        resume=resume,
    )


class TestHappyPath:
    async def test_answer_is_recorded_and_material_lands_in_temp(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, [_question()])
        record = result.records[0]

        assert record.status == STATUS_ANSWERED
        assert record.citation_count == 1
        assert record.citation_membership_ok is True
        assert record.answer_provider == "fake"
        assert record.answer_model == "fake-chat"
        assert record.judge_model == NOT_EXERCISED  # judge 还没接

        # 材料与回答正文只落 temp/，且就在那一行里
        row = load_transcripts(tmp_path / TRANSCRIPT_FILENAME)["fact-001"]
        assert MATERIAL in json.dumps(row, ensure_ascii=False)
        assert "政近是因家族安排离开的" in str(row["answer"])

    async def test_retrieval_params_and_models_reach_the_config(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, [_question()])
        assert result.config.phase == "generation"
        assert result.config.retrieval_params == {"ask_top_k": 8}
        assert result.config.judge_provider == NOT_EXERCISED


class TestRedline:
    """`eval/` 的载体是记录本身——这组用例钉的就是「记录里没有正文的位置」。"""

    async def test_no_field_of_the_record_can_hold_the_answer(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, [_question()])
        payload = json.dumps(_asdict(result), ensure_ascii=False)
        assert MATERIAL not in payload
        assert "政近是因家族安排离开的" not in payload

    async def test_transcript_is_the_only_place_with_text(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, [_question()])
        on_disk = (tmp_path / TRANSCRIPT_FILENAME).read_text(encoding="utf-8")
        assert MATERIAL in on_disk
        # 记录序列化后不含正文
        assert MATERIAL not in json.dumps(_asdict(result), ensure_ascii=False)


class TestFailureIsolation:
    async def test_retrieval_failure_marks_one_question_not_the_run(self, tmp_path: Path) -> None:
        """一题炸掉不该让整轮作废——86 次真实调用串行跑，这条是前提。"""
        questions = [_question(id="fact-001"), _question(id="fact-002")]
        result = await _run(tmp_path, questions, retrieval_error=RuntimeError("库挂了"))

        assert [r.status for r in result.records] == [STATUS_GENERATION_FAILED] * 2
        assert all(not r.citation_membership_ok for r in result.records)
        assert result.summary["generation_failed"] == 2
        # 失败题留在分母里，门禁该红就红
        assert result.summary["citation_membership_denominator"] == 2

    async def test_midstream_provider_failure_is_not_a_refusal(self, tmp_path: Path) -> None:
        """生成到一半超时 → `generation_failed`，**绝不能**记成拒答。

        记成拒答会让 `refusal_correct` 与引用门禁同时失真（M0-02 §8.3）。
        """
        result = await _run(tmp_path, [_question()], chat=ExplodingChat())
        record = result.records[0]
        assert record.status == STATUS_GENERATION_FAILED
        assert record.status != STATUS_INSUFFICIENT_EVIDENCE
        assert record.citation_membership_ok is False

        row = load_transcripts(tmp_path / TRANSCRIPT_FILENAME)["fact-001"]
        # 折的是 `query_error` 事件里的错误码，不是异常类名——provider 超时由
        # `AnsweringRunner` 转成事件（`RAG_TIMEOUT`），不是抛到这里来。
        assert row["error"] == "RAG_TIMEOUT: provider 超时"
        # 已经产出的半截正文留在 temp/ 供排查，但它不参与判定
        assert "开了个头" in str(row["answer"])

    async def test_failure_stage_says_generation_not_content(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, [_question()], chat=ExplodingChat())
        assert result.failures[0]["stage"] == "generation"


class TestCitationFailures:
    async def test_out_of_range_citation_is_its_own_stage(self, tmp_path: Path) -> None:
        result = await _run(tmp_path, [_question()], chat=FakeChatModel(answer="见 [C99]。"))
        record = result.records[0]
        assert record.citation_membership_ok is False
        assert record.citation_out_of_range == ("[C99]",)
        assert result.failures[0]["stage"] == "citation"

    async def test_uncited_answer_is_its_own_stage(self, tmp_path: Path) -> None:
        """「一条引用都没标」与「引了不许引的章」修法不同，失败阶段要分开。"""
        result = await _run(tmp_path, [_question()], chat=FakeChatModel(answer="就这样。"))
        assert result.failures[0]["stage"] == "uncited"

    async def test_refusal_question_without_citation_passes_membership(
        self, tmp_path: Path
    ) -> None:
        result = await _run(
            tmp_path,
            [_question(id="spoiler-001", type="spoiler", expect_refusal=True)],
            chapters=(),  # 装配集为空 → 走固定话术拒答，模型不被调用
        )
        record = result.records[0]
        assert record.status == STATUS_INSUFFICIENT_EVIDENCE
        assert record.citation_membership_ok is True
        row = load_transcripts(tmp_path / TRANSCRIPT_FILENAME)["spoiler-001"]
        assert row["answer"] == REFUSAL_ANSWER


class TestResume:
    async def test_resume_skips_questions_already_in_the_transcript(self, tmp_path: Path) -> None:
        """续跑不重花已经付过费的调用；记录由中间产物重建。"""
        first = await _run(tmp_path, [_question(id="fact-001")])
        assert first.records[0].citation_membership_ok is True

        # 第二题是新的，第一题应被跳过
        questions = [_question(id="fact-001"), _question(id="fact-002")]
        result = await _run(tmp_path, questions, resume=True)
        assert [r.question_id for r in result.records] == ["fact-001", "fact-002"]

        rows = (tmp_path / TRANSCRIPT_FILENAME).read_text(encoding="utf-8").splitlines()
        assert len(rows) == 2, "跳过的那题不该被重复追加"

    async def test_without_resume_everything_runs_again(self, tmp_path: Path) -> None:
        await _run(tmp_path, [_question(id="fact-001")])
        await _run(tmp_path, [_question(id="fact-001")])
        rows = (tmp_path / TRANSCRIPT_FILENAME).read_text(encoding="utf-8").splitlines()
        assert len(rows) == 2

    async def test_rebuilt_record_matches_the_live_one(self, tmp_path: Path) -> None:
        """重建是确定性函数——续跑拿到的记录与当场跑出来的必须一模一样。"""
        live = (await _run(tmp_path, [_question()])).records[0]
        row = load_transcripts(tmp_path / TRANSCRIPT_FILENAME)["fact-001"]
        rebuilt = record_from_transcript(row, _question())
        assert rebuilt == live


class TestResumeRefusesStaleAnswers:
    """只按 `question_id` 匹配是不够的——题号不变而题面被改写时，旧答案会冒充新题的结果。

    而那份产物从外面看完全自洽：逐题记录里没有题面，中间产物又不进 git。
    """

    async def test_rewritten_question_under_the_same_id_is_re_answered(
        self, tmp_path: Path
    ) -> None:
        await _run(tmp_path, [_question(question="旧问法，材料里有答案吗？")])
        await _run(
            tmp_path,
            [_question(question="新问法，材料里有答案吗？")],
            resume=True,
        )
        rows = (tmp_path / TRANSCRIPT_FILENAME).read_text(encoding="utf-8").splitlines()
        assert len(rows) == 2, "题面变了就必须重新答一次，不能复用旧答案"

    async def test_identical_question_is_still_skipped(self, tmp_path: Path) -> None:
        await _run(tmp_path, [_question()])
        await _run(tmp_path, [_question()], resume=True)
        rows = (tmp_path / TRANSCRIPT_FILENAME).read_text(encoding="utf-8").splitlines()
        assert len(rows) == 1


class TestResumeRetriesFailures:
    async def test_generation_failed_is_retried_not_skipped(self, tmp_path: Path) -> None:
        """失败行是「没答出来」，不是「答过了」。

        把它算作已完成，会让带 provider 故障的 run **永远修不好**——而 `--resume`
        恰恰是唯一不重花整轮调用的修复方式。`summary.md` 自己写着「`generation_failed` > 0
        说明这次 run 带故障，应重跑」。
        """
        first = await _run(tmp_path, [_question()], chat=ExplodingChat())
        assert first.records[0].status == STATUS_GENERATION_FAILED

        recovered = FakeChatModel(answer="这次答上了 [C17]。")
        second = await _run(tmp_path, [_question()], chat=recovered, resume=True)
        assert recovered.calls, "provider 已经恢复，失败题却没有被重试"
        assert second.records[0].status == STATUS_ANSWERED
        assert second.summary["generation_failed"] == 0


class TestMixedVersions:
    def test_mixed_prompt_versions_are_not_reported_as_not_exercised(self) -> None:
        """混版不能回落成 `not-exercised`——那表示「这一层没跑」，与事实相反。"""
        from omniread.pipelines.evaluation.generation_runner import _common_prompt_version

        mixed = [{"prompt_version": "aaaa"}, {"prompt_version": "bbbb"}]
        assert (
            _common_prompt_version(mixed, fallback=MIXED_ACROSS_QUESTIONS)
            == MIXED_ACROSS_QUESTIONS
        )
        same = [{"prompt_version": "aaaa"}, {"prompt_version": "aaaa"}]
        assert _common_prompt_version(same, fallback=MIXED_ACROSS_QUESTIONS) == "aaaa"
        assert (
            _common_prompt_version([], fallback=MIXED_ACROSS_QUESTIONS)
            == MIXED_ACROSS_QUESTIONS
        )


class TestEvidenceOfFailure:
    def test_failed_generation_is_none_not_empty_string(self) -> None:
        """失败题的回答按 `None` 判，不按空串——两者走的是不同的失败路径。

        空串会走「非拒答题零引用」，看起来像答案不合规；真相是压根没有答案。
        """
        row = {
            "status": STATUS_GENERATION_FAILED,
            "answer": "",
            "context_chapters": [],
            "request_id": "req_x",
        }
        record = record_from_transcript(row, _question())
        assert record.status == STATUS_GENERATION_FAILED
        assert record.citation_membership_ok is False

    async def test_transcript_is_written_incrementally(self, tmp_path: Path) -> None:
        """每题一有结果就追加，而不是攒到跑完再写。

        攒着写的话，第 80 题炸了，前 79 次已经付过费的调用就全没了。
        """
        path = tmp_path / TRANSCRIPT_FILENAME
        assert not path.exists()

        seen: list[int] = []
        runner, context = _build()
        await run_generation_eval(
            run_id="run-gen",
            questions=[_question(id="fact-001"), _question(id="fact-002")],
            runner=runner,
            context=context,
            transcript_path=path,
            dataset_hash="h",
            dataset_version="m0.1.0",
            corpus_manifest_hash="c",
            chunking_version="m0-placeholder-v1",
            tokenizer_id="t",
            answer_provider="fake",
            retrieval_provider="fake",
            embedding_provider="fake",
            embedding_model="fake-embed",
            embedding_dim=1024,
            rerank_provider="fake",
            rerank_model="fake-rerank",
            retrieval_params={},
            on_progress=lambda done, total, note: seen.append(
                len(path.read_text(encoding="utf-8").splitlines())
            ),
        )
        # 每次进度回调时，文件里已经有对应数量的行——即写入发生在回调之前
        assert seen == [1, 2]


def _asdict(result: object) -> dict:
    """把结果折成可序列化的字典，用来断言「正文没混进去」。"""
    from dataclasses import asdict

    return {
        "records": [asdict(r) for r in result.records],  # type: ignore[attr-defined]
        "summary": result.summary,  # type: ignore[attr-defined]
        "failures": list(result.failures),  # type: ignore[attr-defined]
        "config": asdict(result.config),  # type: ignore[attr-defined]
    }
