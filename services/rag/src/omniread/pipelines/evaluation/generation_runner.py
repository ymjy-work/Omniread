"""生成层评测编排（M0-04 §5.2）。

管线是规格给定的一条链：

```text
RAG runner → temp/run.gen.jsonl → DeepEval → judge → eval/runs/<run>/generation.scores.jsonl
```

本模块负责**前两段**：逐题跑完整问答链、把中间产物落 `temp/`、把标量判定落 `eval/`。
judge 那一段（DeepEval sidecar 与校准）还没接，所以记录里五个 judge 指标恒为 `None`
——「未执行」，不是「得 0 分」。

**两条产物分家，这是本模块的核心约束**：

- `temp/run.gen.jsonl` 放**模型看到与写出的全部文本**（回答正文、材料正文）。`temp/`
  不进 git，这是全仓唯一允许放这些东西的地方。
- `eval/runs/<id>/generation.scores.jsonl` 只放指针与标量，字段集由
  `GenerationScoreRecord` 定死，没有任何放过正文的位置。

**记录是 `(status, 回答正文, 允许集合)` 的确定性函数**，所以断点续跑只靠 `temp/` 的
中间产物就能重建逐题记录，不必把 `eval/` 的产物写一半——那样一旦中断，留下的是一份
题数不全的 `generation.scores.jsonl`，而它看起来和跑完的一样。

**失败隔离**：任一题抛错只把那一题记为 `generation_failed`，循环继续，且那条已经
写进 `temp/`。86 次真实调用串行跑，中途一发瞬时故障不该让前面全部作废。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from omniread.application.ports import ContextSource
from omniread.application.query_service import AnsweringRunner
from omniread.domain.events import EventName
from omniread.domain.models import ContextChunk, QueryRequest, RealmLevel
from omniread.pipelines.evaluation.artifacts import (
    MIXED_ACROSS_QUESTIONS,
    NOT_EXERCISED,
    PHASE_GENERATION,
    EvalRunConfig,
)
from omniread.pipelines.evaluation.generation import (
    aggregate_generation,
    judge_citation_membership,
)
from omniread.pipelines.evaluation.types import (
    STATUS_GENERATION_FAILED,
    GenerationScoreRecord,
)

#: 中间产物的文件名（`M0-04` §5.2 给定）。落 `temp/`，**不进 git**。
TRANSCRIPT_FILENAME = "run.gen.jsonl"

#: 中间产物里单条错误信息的截断长度。错误文本来自 provider，可能很长且不可控；
#: 它只落 `temp/`，但仍然截断——`temp/` 不该变成日志倾倒场。
_MAX_ERROR_CHARS = 200

#: 离线跑的信任标注。**与检索层那句分开写**：检索层讲的是 `must_cite_recall` 失真，
#: 而生成层产物里根本没有这个指标——照抄会让读的人去找一个不存在的数字。
FAKE_GENERATION_TRUST_NOTE = (
    "本次跑用假回答模型：答案由确定性假 provider 生成，不含任何真实模型行为，"
    "所以引用相关指标只反映「链路结构对不对」，不反映模型会不会引用。"
    "检索侧同样是假的（dense 以假查询向量对真库向量），喂进 prompt 的上下文也不可信。"
    "本产物不可作为基线。"
)


class CapturingContextSource:
    """包一层 `ContextSource`，把「这次请求实际取到的材料」留下来。

    不另查一次库：再查一遍拿到的可能与真正进 prompt 的不是同一份，而
    `temp/run.gen.jsonl` 的意义恰恰是「模型当时看到的是什么」。

    调用方需要把它**同时**交给 `AnsweringRunner(context=...)` 与本模块的
    `run_generation_eval(context=...)`——前者用它取材料，后者用它留档。
    """

    def __init__(self, inner: ContextSource) -> None:
        self._inner = inner
        self.loaded: tuple[ContextChunk, ...] = ()

    def load(self, book_id: int, chunk_keys: Sequence[str]) -> Sequence[ContextChunk]:
        chunks = tuple(self._inner.load(book_id, chunk_keys))
        self.loaded = chunks
        return chunks

    def reset(self) -> None:
        """每题开始前清空，免得上一题的材料被当成这一题的。"""
        self.loaded = ()


@dataclass(frozen=True, slots=True)
class GenerationEvalResult:
    config: EvalRunConfig
    records: tuple[GenerationScoreRecord, ...]
    summary: dict[str, object]
    failures: tuple[dict[str, object], ...]
    #: 落 `temp/run.gen.jsonl` 的行（含正文）。调用方负责写盘——本模块不碰文件系统，
    #: 与检索层的 runner 一样只做编排，纯函数好测。
    transcripts: tuple[dict[str, object], ...]


def _cached_is_reusable(
    cached: Mapping[str, object],
    question: Mapping[str, object],
    dataset_hash: str,
) -> tuple[bool, str]:
    """中间产物里的这一行，能不能当作「这道题已经答过了」；不能的话给出原因。

    **只按 `question_id` 匹配是不够的**：题号不变而题面被改写时（Golden 复核里改过题的
    措辞是常事），旧答案会被当成新题的结果写进产物。而那份产物从外面看完全自洽——
    逐题记录里没有题面，中间产物又不进 git。中间产物里本来就存着 `question`，
    检出这件事不需要任何额外成本。

    另有一条同样要紧：`generation_failed` 的行**是「没答出来」，不是「答过了」**。
    把它算作已完成，会让带 provider 故障的 run 永远修不好——而 `--resume` 恰恰是
    唯一不重花整轮调用的修复方式（`summary.md` 自己写着「`generation_failed` > 0
    说明这次 run 带故障，应重跑」）。

    `dataset_hash` 缺失（更早格式的中间产物）时不据此拦截，退回题面比对——那条更强。
    """
    if str(cached.get("status") or "") == STATUS_GENERATION_FAILED:
        return False, "上次是 generation_failed，重试"
    if str(cached.get("question") or "") != str(question["question"]):
        return False, "题面与中间产物不同（Golden 改过），重跑"
    recorded = cached.get("dataset_hash")
    if recorded is not None and str(recorded) != dataset_hash:
        return False, "dataset_hash 与中间产物不同，重跑"
    return True, ""


def load_transcripts(path: Path) -> dict[str, dict[str, object]]:
    """读回中间产物，按 `question_id` 索引；文件不存在就是空。"""
    if not path.is_file():
        return {}
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return {str(row["question_id"]): row for row in rows}


async def run_generation_eval(
    *,
    run_id: str,
    questions: Sequence[dict],
    runner: AnsweringRunner,
    context: CapturingContextSource,
    transcript_path: Path,
    dataset_hash: str,
    dataset_version: str,
    corpus_manifest_hash: str,
    chunking_version: str,
    tokenizer_id: str,
    answer_provider: str,
    retrieval_provider: str,
    embedding_provider: str,
    embedding_model: str,
    embedding_dim: int,
    rerank_provider: str,
    rerank_model: str,
    retrieval_params: Mapping[str, object],
    book_id: int = 1,
    resume: bool = False,
    trust_note: str = "",
    on_progress: Callable[[int, int, str], None] | None = None,
) -> GenerationEvalResult:
    """逐题跑问答链并打分；每题一有结果就追加进 `transcript_path`。

    `resume=True` 时跳过中间产物里**已经答出来**的题——那些题的真实调用已经花过了，
    重跑既费钱又会拿到另一次采样的结果。跳过时记录由中间产物**重建**（确定性函数），
    不依赖任何 `eval/` 的半成品。

    「跳过」的判据见 `_cached_is_reusable`：**不是**「有这个题号的行」就算数。
    """
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_transcripts(transcript_path) if resume else {}

    records: list[GenerationScoreRecord] = []
    transcripts: list[dict[str, object]] = []
    total = len(questions)

    for index, question in enumerate(questions, start=1):
        question_id = str(question["id"])
        cached = done.get(question_id)
        if cached is not None:
            reusable, reason = _cached_is_reusable(cached, question, dataset_hash)
            if reusable:
                transcripts.append(cached)
                records.append(record_from_transcript(cached, question))
                if on_progress is not None:
                    on_progress(index, total, f"{question_id} 跳过（中间产物里已有）")
                continue
            if on_progress is not None:
                on_progress(index, total, f"{question_id} 不跳过：{reason}")

        row = await _run_one(
            runner=runner,
            context=context,
            request=QueryRequest(
                book_id=book_id,
                question=str(question["question"]),
                level=RealmLevel(question["level"]),
                progress=question.get("progress"),
            ),
            question_id=question_id,
            dataset_hash=dataset_hash,
        )
        transcripts.append(row)
        records.append(record_from_transcript(row, question))
        # 逐条追加：中途崩了也不会把已经付过费的调用丢掉。
        _append_jsonl(transcript_path, row)
        if on_progress is not None:
            on_progress(index, total, f"{question_id} {row['status']}")

    summary = aggregate_generation(records)
    return GenerationEvalResult(
        config=EvalRunConfig(
            run_id=run_id,
            kind=PHASE_GENERATION,
            phase=PHASE_GENERATION,
            dataset_hash=dataset_hash,
            dataset_version=dataset_version,
            corpus_manifest_hash=corpus_manifest_hash,
            chunking_version=chunking_version,
            tokenizer_id=tokenizer_id,
            chunk_source="db",
            retrieval_provider=retrieval_provider,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            rerank_provider=rerank_provider,
            rerank_model=rerank_model,
            answer_provider=answer_provider,
            # 真实型号在每题的事件流里取（`generation_started`）；这里只记「跑过生成」。
            # 两者不一致时以逐题记录为准——那才是那一次回答真正用的模型。
            answer_model=_common_answer_model(
                transcripts, fallback=MIXED_ACROSS_QUESTIONS
            ),
            # judge 还没接。写 NOT_EXERCISED 而不是编一个型号：这是确定结论。
            judge_provider=NOT_EXERCISED,
            judge_model=NOT_EXERCISED,
            prompt_version=_common_prompt_version(
                transcripts, fallback=MIXED_ACROSS_QUESTIONS
            ),
            retrieval_params=dict(retrieval_params),
            trust_note=trust_note,
        ),
        records=tuple(records),
        summary=summary,
        failures=failure_rows(records),
        transcripts=tuple(transcripts),
    )


async def _run_one(
    *,
    runner: AnsweringRunner,
    context: CapturingContextSource,
    request: QueryRequest,
    question_id: str,
    dataset_hash: str,
) -> dict[str, object]:
    """跑一题，折成中间产物的一行。**不抛异常**：故障折成 `generation_failed`。"""
    context.reset()
    request_id = f"req_{uuid4().hex}"

    answer_parts: list[str] = []
    context_chapters: list[dict[str, Any]] = []
    status = STATUS_GENERATION_FAILED
    prompt_version = NOT_EXERCISED
    answer_provider = NOT_EXERCISED
    answer_model = NOT_EXERCISED
    error = ""

    try:
        async for event in runner.run(request, request_id):
            if event.name is EventName.ANSWER_DELTA:
                answer_parts.append(str(event.payload["text"]))
            elif event.name is EventName.GENERATION_STARTED:
                prompt_version = str(event.payload["prompt_version"])
                answer_provider = str(event.payload["answer_provider"])
                answer_model = str(event.payload["answer_model"])
            elif event.name is EventName.CITATION_READY:
                context_chapters = [dict(item) for item in event.payload["context_chapters"]]
            elif event.name is EventName.QUERY_DONE:
                status = str(event.payload["status"])
                context_chapters = [dict(item) for item in event.payload["context_chapters"]]
            elif event.name is EventName.QUERY_ERROR:
                error = f"{event.payload.get('code', '')}: {event.payload.get('message', '')}"
    except Exception as exc:
        # 不按异常类型分档：这一层的职责是「别让一题炸掉整轮」，不是给故障分类。
        # provider 故障本来就该走 5xx 而不是被降级成拒答，这里记的是「这一题没成」。
        error = f"{type(exc).__name__}: {exc}"

    if error:
        # 走到这里说明没拿到正常收尾。可能是 provider 故障（`query_error`），
        # 也可能是别的异常——两种都记 `generation_failed`，**绝不记成拒答**。
        status = STATUS_GENERATION_FAILED

    return {
        "question_id": question_id,
        "request_id": request_id,
        # 题面与 dataset_hash 都留着：断点续跑靠它俩判断「这一行还算不算这道题的答案」。
        # 只按题号匹配的话，Golden 改了措辞就会让旧答案被当成新题的结果。
        "question": request.question,
        "dataset_hash": dataset_hash,
        "status": status,
        "answer": "".join(answer_parts),
        "context_chapters": context_chapters,
        # 材料正文只落这里。`citation_supported` 的 judge 需要它，而它绝不能进 `eval/`。
        "material": [
            {
                "chunk_key": chunk.chunk_key,
                "chapter_index": chunk.chapter_index,
                "chapter_title": chunk.chapter_title,
                "text": chunk.text,
            }
            for chunk in context.loaded
        ],
        "answer_provider": answer_provider,
        "answer_model": answer_model,
        "prompt_version": prompt_version,
        "error": error[:_MAX_ERROR_CHARS],
    }


def record_from_transcript(
    row: Mapping[str, object], question: Mapping[str, object]
) -> GenerationScoreRecord:
    """从中间产物的一行重建逐题记录。

    记录是确定性函数，所以断点续跑、以及事后重算口径，都只需要 `temp/` 那一份。
    生成失败（`status == generation_failed`）时回答按 `None` 处理——**不是空串**：
    空串会走「非拒答题零引用」那条判失败的路，看起来像答案不合规，而真相是压根没有答案。
    """
    status = str(row.get("status") or STATUS_GENERATION_FAILED)
    raw_answer = row.get("answer")
    answer = None if status == STATUS_GENERATION_FAILED else str(raw_answer or "")

    chapters = row.get("context_chapters")
    if not isinstance(chapters, list):
        # 不退回「允许集合为空」：那样任何引用都会被判成越界，把「产物坏了」
        # 伪装成「答案全错」。宁可在这里停下来。
        raise ValueError(
            f"{question['id']}: 中间产物的 context_chapters 不是列表"
            f"（{type(chapters).__name__}）——产物已损坏，拒绝猜一个允许集合出来"
        )
    allowed = {int(chapter["chapter_index"]) for chapter in chapters}

    verdict = judge_citation_membership(
        answer,
        allowed,
        expect_refusal=bool(question["expect_refusal"]),
    )

    return GenerationScoreRecord(
        question_id=str(question["id"]),
        question_type=str(question["type"]),
        difficulty=str(question["difficulty"]),
        expect_refusal=bool(question["expect_refusal"]),
        status=status,
        citation_count=verdict.citation_count,
        citation_membership_ok=verdict.membership_ok,
        citation_out_of_range=verdict.out_of_range,
        citation_malformed_count=verdict.malformed_count,
        request_id=str(row.get("request_id") or ""),
        answer_provider=str(row.get("answer_provider") or NOT_EXERCISED),
        answer_model=str(row.get("answer_model") or NOT_EXERCISED),
        prompt_version=str(row.get("prompt_version") or NOT_EXERCISED),
        judge_provider=NOT_EXERCISED,
        judge_model=NOT_EXERCISED,
    )


def failure_rows(
    records: Sequence[GenerationScoreRecord],
) -> tuple[dict[str, object], ...]:
    """生成层失败清单：只写指针、阶段与指标快照。

    与检索层的失败清单同一个规矩——**不写答案、不写材料**。`chunk_key` 这一列在
    生成层没有对应物（失败的是回答，不是一个 chunk），一律留空；越界引用的信息由
    `metrics` 里的计数承载，不把那串标记本身写进来（它是从答案派生的，能少写就少写）。
    """
    return tuple(_failure_row(record) for record in records if _is_failure(record))


def _is_failure(record: GenerationScoreRecord) -> bool:
    return record.status == STATUS_GENERATION_FAILED or not record.citation_membership_ok


def _failure_row(record: GenerationScoreRecord) -> dict[str, object]:
    return {
        "question_id": record.question_id,
        "difficulty": record.difficulty,
        "stage": _failure_stage(record),
        "chunk_key": "",
        "metrics": (
            f"status {record.status} citations {record.citation_count} "
            f"out_of_range {len(record.citation_out_of_range)} "
            f"malformed {record.citation_malformed_count} "
            f"membership {int(record.citation_membership_ok)}"
        ),
        "question_form": record.question_type,
    }


def _failure_stage(record: GenerationScoreRecord) -> str:
    """这一题卡在哪一层——用来分辨该修什么。

    `generation` 是**没有答案**（provider 故障等），不是「答得不好」；
    `citation` 是引用了不允许的章；`uncited` 是非拒答题一条引用都没标。
    分开是因为三者的修法完全不同。
    """
    if record.status == STATUS_GENERATION_FAILED:
        return "generation"
    if record.citation_out_of_range:
        return "citation"
    return "uncited"


def _common_answer_model(
    transcripts: Sequence[Mapping[str, object]], *, fallback: str
) -> str:
    """逐题里出现过的回答型号；不一致或一条都没有时回落到 `fallback`。

    不一致是真发生过的信号（中途换了模型、或部分题走了别的 provider），
    这时 run 级别的 config 不该二选一冒充全体——逐题记录才是权威。
    """
    models = {str(row.get("answer_model")) for row in transcripts}
    models.discard(NOT_EXERCISED)
    return models.pop() if len(models) == 1 else fallback


def _common_prompt_version(
    transcripts: Sequence[Mapping[str, object]], *, fallback: str
) -> str:
    """同上：`prompt_version` 变了就是换了一版 prompt，不能用一个值代表两种。"""
    versions = {str(row.get("prompt_version")) for row in transcripts}
    versions.discard(NOT_EXERCISED)
    return versions.pop() if len(versions) == 1 else fallback


def _append_jsonl(path: Path, row: Mapping[str, object]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


__all__ = [
    "TRANSCRIPT_FILENAME",
    "CapturingContextSource",
    "GenerationEvalResult",
    "failure_rows",
    "load_transcripts",
    "record_from_transcript",
    "run_generation_eval",
]
