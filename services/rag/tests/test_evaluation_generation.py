"""生成层确定性指标单测（M0-04 §5.2）。

重点钉住三件事：

1. **② 号条件真的在拦**「从不标注引用」的回答——没有它，这条硬门禁对一个空集合
   恒真，等于没有门禁。
2. **失败的题留在分母里**，不让分母随结果塌缩（映射侧踩过的坑）。
3. **记录里不出现答案正文**。这是生成层唯一的自动防线：`verify_artifacts.py` 的
   「与语料逐字重合」比对只认语料原文，对模型写的文本天然失效。
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest

from omniread.pipelines.evaluation.generation import (
    MEMBERSHIP_KEY,
    aggregate_generation,
    judge_citation_membership,
)
from omniread.pipelines.evaluation.types import (
    STATUS_ANSWERED,
    STATUS_GENERATION_FAILED,
    STATUS_INSUFFICIENT_EVIDENCE,
    GenerationScoreRecord,
)

ALLOWED = (3, 7, 17)


class TestCitationMembership:
    def test_in_range_citation_passes(self) -> None:
        verdict = judge_citation_membership("答案见 [C17]。", ALLOWED, expect_refusal=False)
        assert verdict.membership_ok is True
        assert verdict.citation_count == 1
        assert verdict.out_of_range == ()

    def test_out_of_range_citation_fails_condition_one(self) -> None:
        verdict = judge_citation_membership("答案见 [C45]。", ALLOWED, expect_refusal=False)
        assert verdict.membership_ok is False
        assert verdict.out_of_range == ("[C45]",)

    def test_non_refusal_answer_without_any_citation_fails(self) -> None:
        """② 号条件。没有它，一个从不引用的回答满分通过——门禁恒真。

        这是本轮唯一一处对 M0-04 §5.2 的加严，起因正是发现空集判定天然安全。
        """
        verdict = judge_citation_membership(
            "答案在这里，但我一条都没标。", ALLOWED, expect_refusal=False
        )
        assert verdict.citation_count == 0
        assert verdict.out_of_range == ()
        assert verdict.membership_ok is False  # ① 满足、② 不满足

    def test_refusal_answer_without_citation_passes(self) -> None:
        """拒答题不适用 ②——它本就不该引用。"""
        verdict = judge_citation_membership(
            "按当前进度，还答不了这个问题。", ALLOWED, expect_refusal=True
        )
        assert verdict.membership_ok is True

    def test_refusal_answer_still_bound_by_condition_one(self) -> None:
        """拒答题免的是 ②，不是 ①：它要是引用了越界的章，照样失败。"""
        verdict = judge_citation_membership("[C45]", ALLOWED, expect_refusal=True)
        assert verdict.membership_ok is False
        assert verdict.out_of_range == ("[C45]",)

    def test_missing_answer_fails_even_for_refusal(self) -> None:
        """生成失败是「没有回答」，不是「拒答」。

        故障记成拒答会让 refusal_correct 与这条门禁同时失真——provider 故障走 5xx
        不降级成拒答，是 M0-02 §8.3 定下的。
        """
        assert judge_citation_membership(None, ALLOWED, expect_refusal=True).membership_ok is False
        assert (
            judge_citation_membership(None, ALLOWED, expect_refusal=False).membership_ok is False
        )

    def test_out_of_range_is_deduplicated_and_rebuilt(self) -> None:
        """越界章号去重保序，且标记由章号重拼——不是从答案里切下来的。"""
        verdict = judge_citation_membership(
            "[C45] ... [C99] ... [C45] ...", ALLOWED, expect_refusal=False
        )
        assert verdict.out_of_range == ("[C45]", "[C99]")
        assert verdict.citation_count == 3

    def test_malformed_writings_are_counted_not_stored(self) -> None:
        """非规范写法只记条数。片段本身可能裹着正文，落盘就是泄漏。"""
        verdict = judge_citation_membership(
            "见 [c17] 与 [C017]。", ALLOWED, expect_refusal=False
        )
        assert verdict.malformed_count == 2
        assert verdict.citation_count == 0  # 两者都不算规范引用


class TestAnswerTextNeverReachesTheRecord:
    PROSE = "这一段是模型写的正文，绝不能被切进产物里"

    def test_malformed_citation_prose_is_not_captured(self) -> None:
        """`CANDIDATE_PATTERN` 的 `[^\\]]*` 能吃掉一整段正文。

        `[C17 正文...]` 这种写法会被 `find_violations` 整段返回；只要有人把它照抄进
        记录，`eval/` 就夹带了模型正文，而 500 字符长度上限拦不住它。
        """
        answer = f"按 [C17 {self.PROSE}] 的说法……"
        verdict = judge_citation_membership(answer, ALLOWED, expect_refusal=False)
        assert verdict.malformed_count == 1
        assert self.PROSE not in json.dumps(asdict(_record()), ensure_ascii=False)

    def test_record_has_no_field_for_the_answer(self) -> None:
        """防线是类型本身：字段集里就没有装答案的地方。"""
        names = set(GenerationScoreRecord.__dataclass_fields__)
        for forbidden in ("answer", "answer_text", "text", "context", "reason", "rationale"):
            assert forbidden not in names

    def test_long_answer_never_enters_the_payload(self) -> None:
        answer = f"[C3] {self.PROSE}" * 40  # 远超 500 字符上限
        verdict = judge_citation_membership(answer, ALLOWED, expect_refusal=False)
        assert verdict.membership_ok is True
        assert self.PROSE not in json.dumps(asdict(_record()), ensure_ascii=False)


def _record(**overrides: object) -> GenerationScoreRecord:
    base = GenerationScoreRecord(
        question_id="fact-001",
        question_type="fact",
        difficulty="easy",
        expect_refusal=False,
        status=STATUS_ANSWERED,
        citation_count=1,
        citation_membership_ok=True,
        citation_out_of_range=(),
        citation_malformed_count=0,
        request_id="req_" + "0" * 32,
        answer_provider="glm",
        answer_model="glm-5.3-flash",
        prompt_version="abc123def456",
        judge_provider="not-exercised",
        judge_model="not-exercised",
    )
    return replace(base, **overrides) if overrides else base  # type: ignore[arg-type]


class TestGenerationAggregate:
    def test_failed_questions_stay_in_the_denominator(self) -> None:
        """分母不随结果塌缩：失败题留在里面，门禁就该红。

        一次带 provider 故障的 run 本来就该重跑，而不是被评分——把失败题剔出分母
        正是映射侧踩过的「分母塌缩」坑。
        """
        ok = _record()
        failed = _record(
            question_id="fact-002",
            status=STATUS_GENERATION_FAILED,
            citation_count=0,
            citation_membership_ok=False,
        )
        summary = aggregate_generation([ok, failed])
        assert summary["question_count"] == 2
        assert summary["citation_membership_denominator"] == 2
        assert summary[MEMBERSHIP_KEY] == 0.5
        assert summary["generation_failed"] == 1

    def test_judge_metrics_are_none_not_zero(self) -> None:
        """未执行 ≠ 得 0 分。judge 还没接，汇总必须是 None 而不是 0.0。"""
        summary = aggregate_generation([_record()])
        for key in (
            "point_coverage",
            "faithfulness",
            "answer_relevancy",
            "answer_boundary_violation",
            "citation_supported",
        ):
            assert summary[key] is None, key

    def test_judge_metrics_aggregate_once_every_record_has_one(self) -> None:
        a = _record(point_coverage=1.0)
        b = _record(question_id="fact-002", point_coverage=0.0)
        assert aggregate_generation([a, b])["point_coverage"] == 0.5

    def test_refusals_count_as_membership_failures_here(self) -> None:
        """拒答题的引用合规性是**可判的**，与 refusal_correct 推迟判定无关。

        推迟的是「模型有没有正确拒答」，不是「它引用的章在不在允许集里」。
        """
        refused = _record(
            question_id="spoiler-001",
            question_type="spoiler",
            expect_refusal=True,
            status=STATUS_INSUFFICIENT_EVIDENCE,
        )
        summary = aggregate_generation([refused])
        assert summary[MEMBERSHIP_KEY] == 1.0


class TestBadShapesAreRejected:
    """坏形状必须**拒绝**，不能是「收下之后静默判错」那种。

    `citation_membership_ok="no"` 是个真值字符串——收下它，门禁的分子照收，
    失败题被算成通过，而产物落盘毫无告警。这与给元组字段加校验是同一条理由，
    所以标量字段不能漏。恢复路径的严格程度决定了产物能不能被信任。
    """

    def _payload(self) -> dict:
        return json.loads(json.dumps(asdict(_record()), ensure_ascii=False))

    def test_string_for_bool_is_rejected(self) -> None:
        payload = self._payload()
        payload["citation_membership_ok"] = "no"
        with pytest.raises(ValueError):
            GenerationScoreRecord.from_payload(payload)

    def test_string_for_int_is_rejected(self) -> None:
        payload = self._payload()
        payload["citation_count"] = "1"
        with pytest.raises(ValueError):
            GenerationScoreRecord.from_payload(payload)

    def test_string_for_optional_float_is_rejected(self) -> None:
        payload = self._payload()
        payload["point_coverage"] = "0.9"
        with pytest.raises(ValueError):
            GenerationScoreRecord.from_payload(payload)

    def test_true_does_not_pass_as_an_int(self) -> None:
        """`bool` 是 `int` 的子类——注解写 `int` 的字段不能被 `True` 蒙混过关。"""
        payload = self._payload()
        payload["citation_count"] = True
        with pytest.raises(ValueError):
            GenerationScoreRecord.from_payload(payload)

    def test_unknown_status_is_rejected(self) -> None:
        """`status` 驱动 `generation_failed` 的计数，拼错的取值会让故障从产物里消失。"""
        payload = self._payload()
        payload["status"] = "REFUSED"
        with pytest.raises(ValueError):
            GenerationScoreRecord.from_payload(payload)

    def test_null_judge_metric_is_not_a_bad_shape(self) -> None:
        """`None` 是「未执行」的合法取值，别把正常状态当坏形状拦掉。"""
        payload = self._payload()
        payload["faithfulness"] = None
        assert GenerationScoreRecord.from_payload(payload).faithfulness is None


class TestGenerationRecordRoundTrip:
    def test_round_trips_exactly(self) -> None:
        original = _record(citation_out_of_range=("[C45]",))
        payload = json.loads(json.dumps(asdict(original), ensure_ascii=False))
        assert asdict(GenerationScoreRecord.from_payload(payload)) == asdict(original)

    def test_rejects_a_string_where_a_marker_list_belongs(self) -> None:
        payload = json.loads(json.dumps(asdict(_record()), ensure_ascii=False))
        payload["citation_out_of_range"] = "[C45]"
        with pytest.raises(ValueError):
            GenerationScoreRecord.from_payload(payload)

    def test_rejects_unknown_keys(self) -> None:
        """字段白名单是 `eval/` 红线的实现方式，还原路径也得守。"""
        payload = json.loads(json.dumps(asdict(_record()), ensure_ascii=False))
        payload["answer"] = "模型写的正文"
        with pytest.raises(TypeError):
            GenerationScoreRecord.from_payload(payload)
