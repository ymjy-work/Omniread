"""裁判 prompt 与判据解析：模板纪律、版本、从严解析、假裁判的确定性。"""

from __future__ import annotations

import json

import pytest

from omniread.infrastructure.providers.base import (
    ChatMessage,
    ChatOptions,
    ChatResponse,
)
from omniread.pipelines.answering import prompt as answering_prompt
from omniread.pipelines.answering.prompt import ContextPassage
from omniread.pipelines.answering.refusal import REFUSAL_MARKER
from omniread.pipelines.judging import (
    PROMPT_VERSION_LENGTH,
    AnswerJudge,
    FakeAnswerJudge,
    JudgeError,
    build_judge_messages,
    judge_prompt_version,
    load_judge_prompt,
    parse_judge_prompt,
    parse_verdict,
    prompt_version,
    read_judge_template,
)

PASSAGES = [
    ContextPassage(chapter_index=17, text="政近在机场对艾莉说了那番话。"),
    ContextPassage(chapter_index=45, text="艾莉把围巾还了回去。"),
]

QUESTION = "政近为什么离开周防家？"

ANSWER = "因为家里出了事[C17]。"


def verdict_payload(**overrides: object) -> str:
    payload: dict[str, object] = {
        "verdict": "PASS",
        "supported": True,
        "citations_valid": True,
        "complete": True,
        "refusal_correct": True,
        "issues": [],
        "reason": "材料支持该结论",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


class StubChat:
    """只回一段文本的假模型；记录每次收到的消息与选项。"""

    model = "stub-judge"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[list[ChatMessage], ChatOptions | None]] = []

    async def complete(
        self, messages, options: ChatOptions | None = None
    ) -> ChatResponse:
        self.calls.append((list(messages), options))
        return ChatResponse(text=self.text, model=self.model)

    async def stream(self, messages, options: ChatOptions | None = None):
        raise AssertionError("裁判不该走流式：半截 JSON 无法解析")


# ── 模板 ──


def test_template_carries_the_rubric_dimensions() -> None:
    prompt = load_judge_prompt()

    # 五个维度一个都不能少：少一个，那一类错就没人看。
    assert "事实支持性" in prompt.system
    assert "引用正确性" in prompt.system
    assert "信息完整性" in prompt.system
    assert "幻觉与越界" in prompt.system
    assert "拒答正确性" in prompt.system
    # 标记的真相源在 refusal.py，这里断言它逐字出现——但**出现的位置是「别要求它」**，
    # 见下一条：裁判判的是用户可见的回答，而那个标记在服务端就被换掉了。
    assert REFUSAL_MARKER in prompt.system
    # 「不能确定时不得强行判定通过」——UNCERTAIN 之所以是合法结果，全靠这一条。
    assert "不得强行判定通过" in prompt.system


def test_template_warns_against_the_two_protocol_misreads() -> None:
    """两条**协议性误判**的防线。缺了它们，裁判会把合格的回答判成不合格：

    - 不认 `【第 N 章】` ↔ `[CN]` 的对应：实测 4 条 FAIL 全是这个原因，裁判自己写着
      「引用内容虽能在相应章节找到支持，但引用编号本身不合规」。
    - 拿 `[INSUFFICIENT]` 去判用户可见的回答：装配集为空时模型根本没被调用，回答是
      服务端那句自然语言话术，标记在服务端就被换掉了。实测 3 条 spoiler 因此全判 FAIL，
      而裁判自己的 reason 写着「实质拒答可以接受」。
    """
    system = load_judge_prompt().system

    assert "【第 17 章】" in system
    assert "[C17]" in system
    assert "两种写法" in system
    # 拒答那一维不能要求标记出现——它是内部信号，用户看不到。
    assert "用户可见的回答里不会包含它" in system


def test_template_forces_every_charge_onto_the_material() -> None:
    """「不得使用外部知识」这条**光写在规则里不够**——实测裁判自己破了它。

    它拿「深闺的千金小姐」去定「千金小姐」是谁，而那个称号出自**另一道题的材料**，
    对这一题来说是外部知识。所以规则要写成可操作的：指控必须指得出材料里的那一句，
    并且给出两条不依赖外部事实的替代判据（自相矛盾、把未交代的信息写成事实）。
    """
    system = load_judge_prompt().system

    assert "指不出来，就不要提这条指控" in system
    assert "材料之外的知识" in system
    assert "自相矛盾" in system
    assert "没有交代" in system


def test_prompt_version_is_the_short_hash_of_the_template() -> None:
    assert judge_prompt_version() == prompt_version(read_judge_template())
    assert len(judge_prompt_version()) == PROMPT_VERSION_LENGTH


def test_prompt_version_is_stable_and_follows_content() -> None:
    text = read_judge_template()
    changed = text.replace("待评估答案", "待判答案")

    assert prompt_version(text) == prompt_version(text)
    assert prompt_version(text) != prompt_version(changed)


def test_prompt_version_covers_the_shared_material_format(monkeypatch) -> None:
    """材料段的渲染格式来自 `answering`——改了它，裁判的版本必须跟着变。

    裁判看的就是回答看过的那批材料段。若两份版本各算各的，改了段头之后回答换了
    版本、裁判没换，而两边都不报错：同一个裁判版本号会同时指代两种不同的输入。
    """
    before = judge_prompt_version()
    monkeypatch.setattr(answering_prompt, "_PASSAGE_HEADER", "【第 {chapter_index} 節】")

    assert judge_prompt_version() != before


def test_material_question_and_answer_land_in_the_user_message() -> None:
    _, user = build_judge_messages(QUESTION, PASSAGES, ANSWER)

    assert "【第 17 章】\n政近在机场对艾莉说了那番话。" in user.content
    assert "{{CONTEXT}}" not in user.content
    assert "{{QUESTION}}" not in user.content
    assert "{{ANSWER}}" not in user.content
    # 顺序：材料 → 问题 → 待评估答案。答案在最后，才不会被后一趟替换扫到。
    assert user.content.index("【第 17 章】") < user.content.index(QUESTION)
    assert user.content.index(QUESTION) < user.content.index(ANSWER)


def test_empty_material_still_renders_the_placeholder() -> None:
    _, user = build_judge_messages(QUESTION, [], ANSWER)

    assert "本次没有可用材料" in user.content
    assert ANSWER in user.content


def test_parse_rejects_missing_section_or_placeholder() -> None:
    with pytest.raises(ValueError):
        parse_judge_prompt("<user>\n{{CONTEXT}} {{QUESTION}} {{ANSWER}}\n</user>")
    with pytest.raises(ValueError):
        # 少了 {{ANSWER}}：没有待评估答案，判据就不再是「对照材料判答案」。
        parse_judge_prompt("<system>判据</system>\n<user>{{CONTEXT}} {{QUESTION}}</user>")


# ── 判据解析：从严 ──


def test_parse_verdict_accepts_a_well_formed_verdict() -> None:
    verdict = parse_verdict(verdict_payload())

    assert verdict.verdict == "PASS"
    assert verdict.passed is True
    assert verdict.supported is True
    assert verdict.issues == ()
    assert verdict.raw == verdict_payload()


def test_uncertain_is_a_legal_verdict() -> None:
    """UNCERTAIN 是合法结果，不是失败——判据明写「不得强行判定通过」。"""
    verdict = parse_verdict(verdict_payload(verdict="UNCERTAIN"))

    assert verdict.verdict == "UNCERTAIN"
    assert verdict.passed is False


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ("not json at all", "不是合法 JSON"),
        ("[1, 2, 3]", "顶层不是 JSON 对象"),
        (json.dumps({"verdict": "PASS"}), "缺少键"),
        (verdict_payload(verdict="MAYBE"), "verdict 不在"),
        (verdict_payload(supported="true"), "不是布尔值"),
        (verdict_payload(complete=1), "不是布尔值"),
        (verdict_payload(issues="没有引用"), "不是字符串数组"),
        (verdict_payload(reason=None), "reason 不是字符串"),
        ("```json\n" + verdict_payload() + "\n```", "代码围栏"),
    ],
)
def test_parse_verdict_rejects_malformed_output(payload: str, reason: str) -> None:
    with pytest.raises(JudgeError, match=reason):
        parse_verdict(payload)


def test_extra_keys_are_tolerated() -> None:
    """多一个键不影响判定：判据关心的是那七个字段在不在、类型对不对。"""
    payload = json.loads(verdict_payload())
    payload["confidence"] = 0.9

    assert parse_verdict(json.dumps(payload, ensure_ascii=False)).verdict == "PASS"


# ── 调用 ──


async def test_judge_uses_a_deterministic_temperature() -> None:
    chat = StubChat(text=verdict_payload())
    verdict = await AnswerJudge(chat).judge(QUESTION, PASSAGES, ANSWER)

    assert verdict.verdict == "PASS"
    assert chat.calls[0][1] == ChatOptions(temperature=0.0)


async def test_judge_raises_on_unusable_output() -> None:
    chat = StubChat(text="我觉得这个答案还行")

    with pytest.raises(JudgeError):
        await AnswerJudge(chat).judge(QUESTION, PASSAGES, ANSWER)


async def test_fake_judge_is_deterministic_and_never_calls_a_model() -> None:
    judge = FakeAnswerJudge()
    verdict = await judge.judge(QUESTION, PASSAGES, ANSWER)

    assert judge.provider == "fake"
    assert verdict.verdict == "PASS"
    assert verdict.raw == ""


@pytest.mark.parametrize("answer", [ANSWER, REFUSAL_MARKER])
async def test_fake_judge_reports_no_failure_it_cannot_see(answer: str) -> None:
    """假裁判没有判据，就不该报出它看不见的错。

    `refusal_correct` 问的是「拒答行为对不对」，不是「这条答案是不是拒答」——
    拿后者去填会让假跑的报表显示一整列并不存在的拒答错误。
    """
    verdict = await FakeAnswerJudge().judge(QUESTION, PASSAGES, answer)

    assert verdict.refusal_correct is True
    assert verdict.supported is True
    assert verdict.issues == ()
