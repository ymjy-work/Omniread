"""评测产物的渲染与还原（M0-02 §7.1、M0-04 §5.1）。

这里钉住的都是同一类问题：**数字算对了，写出来却被读错**。它们不像算错那样会
自己冒出来——产物照样生成、红线检查照样通过、退出码照样是 0，只是把评审引到
相反的结论上。

两个具体形态：

- `spoiler` 档全是拒答题，`must_cite_recall` 的分母是 0。`_ratio` 会返回 `0.0`，
  照直渲染成 `0.0000` 就会被读成「该档引用全错」，而实际是「该档没有可判定的题」。
- 「分母为 0」与「分母字段缺失」是两个不同的状态，**不能共用一个占位符**。
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from omniread.pipelines.evaluation.artifacts import (
    EvalRunConfig,
    fmt_ratio,
    write_eval_run_dir,
)
from omniread.pipelines.evaluation.types import RetrievalScoreRecord


def _config() -> EvalRunConfig:
    return EvalRunConfig(
        run_id="run-x",
        kind="retrieval",
        phase="retrieval",
        dataset_hash="h",
        dataset_version="m0.1.0",
        corpus_manifest_hash="c",
        chunking_version="m0-placeholder-v1",
        tokenizer_id="t",
        chunk_source="db",
        retrieval_provider="ali",
        embedding_provider="dashscope",
        embedding_model="e",
        embedding_dim=1024,
        rerank_provider="dashscope",
        rerank_model="r",
    )


def _record(**overrides: object) -> RetrievalScoreRecord:
    keys = ("book:1:chapter:2#c0",)
    base = RetrievalScoreRecord(
        question_id="fact-001",
        question_type="fact",
        difficulty="easy",
        level="past",
        progress=10,
        expect_refusal=False,
        must_cite_hit=True,
        groups_total=1,
        groups_hit=1,
        evidence_total=1,
        evidence_hit=1,
        evidence_mapped=1,
        all_evidence_hit=True,
        chapter_recall_hit=True,
        leak_dense=0,
        leak_kw=0,
        leak_fused=0,
        leak_rerank=0,
        leak_assembled=0,
        dense_keys=keys,
        kw_keys=keys,
        fused_keys=keys,
        rerank_keys=keys,
        assembled_keys=keys,
        dropped=(),
        mapped_not_assembled_keys=(),
    )
    # 覆盖项由调用方按用例逐个给出，键值对类型无法在此静态收窄
    return replace(base, **overrides) if overrides else base  # type: ignore[arg-type]


def _entry(*, questions: int, denominator: int, recall: float) -> dict[str, object]:
    return {
        "questions": questions,
        "must_cite_recall_denominator": denominator,
        "must_cite_recall": recall,
        "evidence_recall": 1.0,
        "leak": 0,
    }


def _summary(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "question_count": 2,
        "must_cite_recall": 0.5,
        "must_cite_recall_denominator": 2,
        "evidence_recall": 1.0,
        "group_recall": 1.0,
        "all_evidence_recall": 0.5,
        "chapter_recall": 1.0,
        "evidence_mapped": 1.0,
        "leak": 0,
        "per_type": {
            "fact": _entry(questions=1, denominator=1, recall=0.0),
            "spoiler": _entry(questions=1, denominator=0, recall=0.0),
        },
    }
    base.update(overrides)
    return base


def _render(tmp_path: Path, summary: dict[str, object]) -> str:
    write_eval_run_dir(tmp_path, config=_config(), summary=summary, failures=())
    return (tmp_path / "summary.md").read_text(encoding="utf-8")


class TestFmtRatio:
    def test_real_zero_is_not_masked(self) -> None:
        """分母非 0 的 0 分是真结果，必须照原样写出来。"""
        assert fmt_ratio(0.0, 5) == "0.0000"

    def test_zero_denominator_is_not_a_score(self) -> None:
        assert fmt_ratio(0.0, 0) == "—"

    def test_missing_denominator_still_shows_the_value(self) -> None:
        """分母缺失是「不知道」，不是「就是 0」。

        判据必须是 `== 0` 而不是 `not denominator`：后者会连算出来的比率一起吞掉，
        把 `1.0000` 写成 `—`；而同一行的分母列已经用 `?` 标了「不知道」，
        比率列再抹一次就把「未知」伪装成了「不可计算」。
        """
        assert fmt_ratio(1.0, None) == "1.0000"


class TestSummaryMarkdown:
    def test_empty_population_renders_as_dash_not_zero(self, tmp_path: Path) -> None:
        text = _render(tmp_path, _summary())
        assert "| `spoiler` | 1 | 0 | — | 1.0000 | 0 |" in text
        # 真要紧的是同一张表里的另一行：分母非 0 的真 0 分不能被一起抹掉
        assert "| `fact` | 1 | 1 | 0.0000 | 1.0000 | 0 |" in text

    def test_headline_agrees_with_the_breakdown(self, tmp_path: Path) -> None:
        """全拒答的 run：头条与分列必须给出同一种读法。

        两处各写一套渲染规则时，同一份产物会同时写着「0.0000」（读作引用全错）
        与「—」（读作不可计算）。
        """
        summary = _summary(
            question_count=1,
            must_cite_recall=0.0,
            must_cite_recall_denominator=0,
            per_type={"spoiler": _entry(questions=1, denominator=0, recall=0.0)},
        )
        text = _render(tmp_path, summary)
        assert "- `must_cite_recall`：—" in text
        assert "| `spoiler` | 1 | 0 | — | 1.0000 | 0 |" in text

    def test_missing_denominator_field_reads_as_unknown(self, tmp_path: Path) -> None:
        """产物比代码旧（没有分母列）时记 `?`，且不吞掉比率。"""
        summary = _summary(
            per_type={
                "fact": {
                    "questions": 2,
                    "must_cite_recall": 1.0,
                    "evidence_recall": 1.0,
                    "leak": 0,
                }
            }
        )
        text = _render(tmp_path, summary)
        assert "| `fact` | 2 | ? | 1.0000 | 1.0000 | 0 |" in text


class TestRecordFromPayload:
    def test_round_trips_exactly(self) -> None:
        original = _record()
        payload = json.loads(json.dumps(asdict(original), ensure_ascii=False))
        assert asdict(RetrievalScoreRecord.from_payload(payload)) == asdict(original)

    def test_rejects_a_string_where_a_pointer_list_belongs(self) -> None:
        """误写成字符串的指针列不能被悄悄拆成一串单字符元组。

        拆出来的结果不会让任何一步报错，`set(record.rerank_keys)` 照样能跑，
        只是 `_failure_stage` 会把「被装配截掉」判成「根本没召回」——
        失败清单照样生成，阶段列却是错的。
        """
        payload = json.loads(json.dumps(asdict(_record()), ensure_ascii=False))
        payload["rerank_keys"] = "book:1:chapter:2#c0"
        with pytest.raises(ValueError):
            RetrievalScoreRecord.from_payload(payload)

    def test_rejects_unknown_keys(self) -> None:
        """字段白名单是 `eval/` 红线的实现方式，还原路径也得守。"""
        payload = json.loads(json.dumps(asdict(_record()), ensure_ascii=False))
        payload["note"] = "正文不进产物"
        with pytest.raises(TypeError):
            RetrievalScoreRecord.from_payload(payload)
