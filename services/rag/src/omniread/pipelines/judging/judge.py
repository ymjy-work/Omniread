"""裁判的调用与判据解析（评测专用，不在请求路径上）。

**判据格式从严，不做宽松解析**：
缺键、非布尔、`verdict` 不在三态里、带 Markdown 代码围栏——一律判整题失败。
宽松解析会把「模型没按格式答」悄悄变成「一个看起来正常的判定」，而这类漂移一旦
混进统计就再也分不出来。失败不静默：`judge_status` 记成 `failed` 并计数上报。

**为什么这份裁判不能当门禁**（外部共识）：模型判断重跑分数会变，
把回归与测量噪声分开做不到，门禁会误报然后被人关掉。它只**旁挂**在确定性指标旁边，
用来把确定性指标看不见的那类错（语义关系错）从「只能人工抽检」变成「有个数」。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from omniread.infrastructure.providers.base import ChatMessage, ChatModel, ChatOptions
from omniread.pipelines.answering.prompt import ContextPassage
from omniread.pipelines.answering.refusal import REFUSAL_MARKER
from omniread.pipelines.judging.prompt import (
    JudgePrompt,
    load_judge_prompt,
)

#: 三态。`UNCERTAIN` 是**合法结果**而不是失败：判据说「不能确定时标记为无法确定，
#: 不得强行判定通过」，把它折成 PASS 或 FAIL 都等于替裁判下结论。
VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_UNCERTAIN = "UNCERTAIN"
JUDGE_VERDICTS = (VERDICT_PASS, VERDICT_FAIL, VERDICT_UNCERTAIN)

#: 判据要求的七个键，一个都不能少。
_REQUIRED_KEYS = (
    "verdict",
    "supported",
    "citations_valid",
    "complete",
    "refusal_correct",
    "issues",
    "reason",
)
_BOOLEAN_KEYS = ("supported", "citations_valid", "complete", "refusal_correct")

#: 裁判调用是**判断**不是创作：同一份输入要给出同一个判定，温度显式给 0，
#: 不靠 provider 的默认值（与改写同一条纪律）。
JUDGE_OPTIONS = ChatOptions(temperature=0.0)


class JudgeError(Exception):
    """裁判输出不可用（格式不合判据，或 provider 故障）。**不静默降级**。"""


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """一次裁判的判定。

    `raw` 是模型原样输出，**只给复核件用**：它是自由文本，会逐字引用材料，
    因此只能落 `.agent/temp/`，绝不能进 `eval/runs`。
    """

    verdict: str
    supported: bool
    citations_valid: bool
    complete: bool
    refusal_correct: bool
    issues: tuple[str, ...]
    reason: str
    raw: str

    @property
    def passed(self) -> bool:
        return self.verdict == VERDICT_PASS


def parse_verdict(text: str) -> JudgeVerdict:
    """把裁判的输出解析成 `JudgeVerdict`；不合判据即抛 `JudgeError`。

    从严：`json.loads` 原文（只去首尾空白），**不剥代码围栏**。剥围栏等于替模型
    修正格式，而「模型开始带围栏」正是判据漂移最早的症状。
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        raise JudgeError("裁判输出带 Markdown 代码围栏（判据要求只输出合法 JSON）")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise JudgeError(f"裁判输出不是合法 JSON：{error.msg}") from error
    if not isinstance(payload, dict):
        raise JudgeError(f"裁判输出的顶层不是 JSON 对象：{type(payload).__name__}")

    missing = [key for key in _REQUIRED_KEYS if key not in payload]
    if missing:
        raise JudgeError(f"裁判输出缺少键：{'、'.join(missing)}")

    verdict = payload["verdict"]
    if verdict not in JUDGE_VERDICTS:
        raise JudgeError(f"verdict 不在 {JUDGE_VERDICTS} 里：{verdict!r}")

    flags: dict[str, bool] = {}
    for key in _BOOLEAN_KEYS:
        value = payload[key]
        if not isinstance(value, bool):
            raise JudgeError(f"{key} 不是布尔值：{value!r}")
        flags[key] = value

    issues = payload["issues"]
    if not isinstance(issues, list) or not all(
        isinstance(item, str) for item in issues
    ):
        raise JudgeError("issues 不是字符串数组")

    reason = payload["reason"]
    if not isinstance(reason, str):
        raise JudgeError("reason 不是字符串")

    return JudgeVerdict(
        verdict=verdict,
        issues=tuple(issues),
        reason=reason,
        raw=text,
        **flags,
    )


class AnswerJudge:
    """真裁判：一次 `complete` 调用，返回结构化判定。

    用 `complete` 而不是 `stream`：判定是一个整体，逐块吐出来没有消费方，
    而且半截 JSON 无法解析。
    """

    provider = "deepseek"

    def __init__(self, chat: ChatModel, prompt: JudgePrompt | None = None) -> None:
        self._chat = chat
        self._prompt = prompt or load_judge_prompt()

    @property
    def model(self) -> str:
        return self._chat.model

    @property
    def prompt_version(self) -> str:
        return self._prompt.version

    def build_messages(
        self, question: str, passages: Sequence[ContextPassage], answer: str
    ) -> list[ChatMessage]:
        """裁判实际看到的 messages。测试与复核件都从它取，不另拼一份。"""
        return self._prompt.build_messages(question, passages, answer)

    async def judge(
        self, question: str, passages: Sequence[ContextPassage], answer: str
    ) -> JudgeVerdict:
        messages = self.build_messages(question, passages, answer)
        response = await self._chat.complete(messages, JUDGE_OPTIONS)
        return parse_verdict(response.text)


class FakeAnswerJudge:
    """联调用的假裁判：确定性判定，绝不调模型。

    **它不是「一个宽松的裁判」**：判定与材料无关，只按答案里有没有拒答标记给出
    固定结果。它的用处是让评测链在没有凭据时也能跑通并落盘，所以产物必须带
    `trust_note` 标注不可作基线。
    """

    provider = "fake"
    model = "fake-judge"

    def __init__(self, prompt: JudgePrompt | None = None) -> None:
        self._prompt = prompt or load_judge_prompt()

    @property
    def prompt_version(self) -> str:
        return self._prompt.version

    def build_messages(
        self, question: str, passages: Sequence[ContextPassage], answer: str
    ) -> list[ChatMessage]:
        return self._prompt.build_messages(question, passages, answer)

    async def judge(
        self, question: str, passages: Sequence[ContextPassage], answer: str
    ) -> JudgeVerdict:
        # 四个布尔一律填「没问题」。**不能拿「这条答案是不是拒答」去填
        # `refusal_correct`**：那一个字段问的是「拒答行为对不对」，把「不是拒答」
        # 记成「拒答不对」会让假跑的报表显示 30 条拒答错误，而一条都不存在。
        # 假裁判没有判据，就不该报出它看不见的错。
        refused = answer.lstrip().startswith(REFUSAL_MARKER)
        return JudgeVerdict(
            verdict=VERDICT_PASS,
            supported=True,
            citations_valid=True,
            complete=True,
            refusal_correct=True,
            issues=(),
            reason=f"（联调裁判）确定性判定，与材料无关；答案{'是' if refused else '不是'}拒答",
            raw="",
        )


__all__ = [
    "JUDGE_OPTIONS",
    "JUDGE_VERDICTS",
    "VERDICT_FAIL",
    "VERDICT_PASS",
    "VERDICT_UNCERTAIN",
    "AnswerJudge",
    "FakeAnswerJudge",
    "JudgeError",
    "JudgeVerdict",
    "parse_verdict",
]
