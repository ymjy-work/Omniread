"""答案层评测编排（M1-2）。

与检索层同一个 run 目录、同一次跑：`run_eval.py --answer-layer` 先跑检索拿到装配集，
再让**同一个 `AnsweringRunner`**（线上问答链的那一个，不是它的复刻）逐题作答。
复刻一条只给评测用的问答链等于把口径写在两处，跑出来的数就不再描述线上行为。

逐题调用的两条纪律：

- **`request_id` 由题号派生**（`eval-<question_id>`），不随机。它进产物，是失败定位的
  指针；随机会让同一个 run 两次跑出不同的产物，重算就对不上了。
- **一次问答的全部事件先收齐再折叠**，不边流边算。`citation_in_set` 要用 `query_done`
  报的 `context_chapters`，而它在流的末尾——边流边算等于在信息不全时下结论。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from omniread.application.query_service import AnsweringRunner
from omniread.domain.models import QueryRequest
from omniread.pipelines.answering.prompt import answer_prompt_version
from omniread.pipelines.evaluation.generation import (
    AnswerOutcome,
    aggregate_generation,
    fold_answer,
    generation_failure_rows,
    score_answer,
)
from omniread.pipelines.evaluation.runner import build_query_request
from omniread.pipelines.evaluation.types import GenerationScoreRecord
from omniread.pipelines.retrieval.types import RetrievalOutcome

#: 假回答模型下的产物可以看，但不能当基线：回答是固定文本、与材料无关，
#: 引用与拒答两个数都只是「链路通了」的证据。
FAKE_ANSWER_TRUST_NOTE = (
    "本次跑用确定性假回答模型：回答内容固定且与材料无关，答案层的 "
    "citation_in_set 与 refusal_correct 都不可作为基线，只能验证链路结构。"
)


@dataclass(frozen=True, slots=True)
class GenerationEvalResult:
    records: tuple[GenerationScoreRecord, ...]
    summary: dict[str, object]
    failures: tuple[dict[str, object], ...]
    #: 逐题回答原文，**只给复核件用**（`M0-02` §7.1：回答原文只落 `temp/`）。
    #: 它不进任何逐题记录——`GenerationScoreRecord` 里没有放正文的位置是有意的。
    #: 人工抽检与「标记没被认出来」的排查都要看它，所以留着；写盘由调用方决定。
    outcomes: tuple[AnswerOutcome, ...] = ()


def eval_request_id(question_id: str) -> str:
    """评测用的 request_id：由题号派生，可复现、可回溯到题。"""
    return f"eval-{question_id}"


class RecordedRetrieval:
    """回放本次 run 里已经算好的检索结果，实现 `RetrievalService`。

    答案层不重跑检索：同一次 run 里两层的输入必须是**同一份**装配集，
    否则 `citation_in_set` 的允许引用范围与检索层的数字来自两次采样，
    而两次采样在 provider 那一侧并不保证一致。顺带省掉每题两次真实调用。

    查不到即报错，不静默退回「空上下文」——那会把「这次 run 的检索结果丢了」
    伪装成「模型拒答」，两个指标同时失真。
    """

    def __init__(self, outcomes: Mapping[QueryRequest, RetrievalOutcome]) -> None:
        self._outcomes = dict(outcomes)

    async def retrieve(self, request: QueryRequest) -> RetrievalOutcome:
        try:
            return self._outcomes[request]
        except KeyError:
            raise LookupError(
                f"检索结果里没有这一条请求：{request.question!r}"
                "（level / progress / neighbor_expand 任一不同都算另一次请求）"
            ) from None


async def run_generation_eval(
    *,
    questions: Sequence[Mapping[str, object]],
    runner: AnsweringRunner,
    answer_provider: str,
    answer_model: str,
    book_id: int = 1,
    neighbor_expand: bool = True,
    prompt_version: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> GenerationEvalResult:
    """逐题跑问答链并打分。题目顺序即 Golden 的 id 序，结果与顺序无关。

    `prompt_version` 默认取当前模板的版本；可以显式传，好让一次重算能复现当时的取值。

    `on_progress(序号, 总数, question_id)` 每题的**调用前**回调一次。这里不直接 print：
    库代码不该决定往哪写，而且 `run_eval.py` 的 stdout 是给人读的报告、进度属于 stderr。
    加它是被一次 86 题的真跑逼出来的——那条链跑四十分钟，没有逐题回显就分不出
    「在跑」与「吊在某个请求上」，只能去数数据库事务。
    """
    version = prompt_version or answer_prompt_version()
    records: list[GenerationScoreRecord] = []
    outcomes: list[AnswerOutcome] = []
    total = len(questions)
    for index, question in enumerate(questions, start=1):
        if on_progress is not None:
            on_progress(index, total, str(question["id"]))
        request = build_query_request(
            question, book_id=book_id, neighbor_expand=neighbor_expand
        )
        request_id = eval_request_id(str(question["id"]))
        events = [event async for event in runner.run(request, request_id)]
        answer = fold_answer(events)
        outcomes.append(answer)
        records.append(
            score_answer(
                question,
                answer,
                answer_provider=answer_provider,
                answer_model=answer_model,
                prompt_version=version,
            )
        )

    return GenerationEvalResult(
        records=tuple(records),
        summary=aggregate_generation(records),
        failures=generation_failure_rows(records),
        outcomes=tuple(outcomes),
    )


__all__ = [
    "FAKE_ANSWER_TRUST_NOTE",
    "GenerationEvalResult",
    "RecordedRetrieval",
    "eval_request_id",
    "run_generation_eval",
]
