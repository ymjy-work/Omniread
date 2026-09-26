"""映射产物红线与兜底路径单测（M0-7b）。

产物侧测的是「坏东西写不进去」，不是「好东西写得进」——`eval/` 进 git，
一段正文 push 出去就只能重写历史，所以红线必须由写入方在落盘前挡住。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from omniread.infrastructure.providers.base import MapperCandidate, MapperResult
from omniread.infrastructure.providers.fake import FakeMapperModel
from omniread.pipelines.mapping.artifacts import (
    ALLOWED_RUN_FILES,
    MAX_REASON_CHARS,
    MAX_STRING_FIELD,
    ArtifactRedlineError,
    MappingRecord,
    RunConfig,
    check_run_dir,
    flatten_reason,
    write_run_dir,
)
from omniread.pipelines.mapping.fallback import (
    MapperParseError,
    apply_fallback,
    parse_mapper_output,
)
from omniread.pipelines.mapping.types import (
    DETERMINISTIC_MAPPER_MODEL,
    MATCH_MATCHED,
    MATCH_UNMATCHED,
    MappingOutcome,
)

CANDIDATES = [
    MapperCandidate(chunk_key="book:1:chapter:1#c0", content="前一段正文。"),
    MapperCandidate(chunk_key="book:1:chapter:1#c1", content="含目标证据的正文片段。"),
]


def _nomatch() -> MappingOutcome:
    return MappingOutcome(
        evidence_hash="0" * 64,
        chapter_id="book:1:chapter:1",
        match_status=MATCH_UNMATCHED,
        matched_chunk_key=None,
        confidence=0.0,
        overlap_reason="构造的未命中样例",
        alternative_chunk_key=None,
        mapper_model=DETERMINISTIC_MAPPER_MODEL,
        mapper_prompt_version="no-prompt",
    )


def _record(**overrides: object) -> MappingRecord:
    base = MappingRecord(
        question_id="fact-001",
        evidence_hash="a" * 64,
        chapter_id="book:1:chapter:1",
        match_status=MATCH_MATCHED,
        matched_chunk_key="book:1:chapter:1#c0",
        alternative_chunk_key=None,
        confidence=1.0,
        decision_tier="unique_cover",
        mapper_model=DETERMINISTIC_MAPPER_MODEL,
        mapper_prompt_version="no-prompt",
        overlap_reason="精确子串位于章内 [0,10)",
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def _payload(*, confidence: str = "0.8", reason: str = '"r"') -> str:
    """拼一条四字段 JSON；只让被测字段变化，避免整串字面量在断言里看走眼。"""
    return (
        '{"matched_chunk_key": "a#c1", '
        f'"confidence": {confidence}, '
        f'"overlap_reason": {reason}, '
        '"alternative_chunk_key": null}'
    )


def _config() -> RunConfig:
    return RunConfig(
        run_id="test-run",
        kind="mapping",
        dataset_hash="b" * 64,
        dataset_version="m0-placeholder-v1",
        golden_question_count=1,
        evidence_count=1,
        chunking_version="m0-placeholder-v1",
        tokenizer_id="tokenizers:test",
        chunk_source="corpus",
        mapper_model=DETERMINISTIC_MAPPER_MODEL,
        mapper_prompt_version="no-prompt",
        mapper_provider="none",
        deterministic_only=True,
    )


# 映射 run 实际产出的文件。`ALLOWED_RUN_FILES` 是整个 run 目录布局的并集
# （含检索层那几件），映射只写其中这五个。
MAPPING_RUN_FILES = frozenset(
    {"config.json", "summary.json", "summary.md", "mappings.jsonl", "mapping_failures.jsonl"}
)


class TestArtifactWhitelist:
    def test_writes_exactly_the_mapping_files(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        write_run_dir(
            run_dir, config=_config(), records=[_record()], summary={"run_id": "test-run"}
        )
        assert {path.name for path in run_dir.iterdir()} == set(MAPPING_RUN_FILES)
        assert MAPPING_RUN_FILES <= ALLOWED_RUN_FILES
        assert check_run_dir(run_dir) == []

    def test_extra_file_is_rejected(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        write_run_dir(
            run_dir, config=_config(), records=[_record()], summary={"run_id": "test-run"}
        )
        (run_dir / "debug.txt").write_text("随手 dump 的正文", encoding="utf-8")
        problems = check_run_dir(run_dir)
        assert any("debug.txt" in problem for problem in problems)

    def test_subdirectory_is_rejected(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        write_run_dir(
            run_dir, config=_config(), records=[_record()], summary={"run_id": "test-run"}
        )
        (run_dir / "raw").mkdir()
        (run_dir / "raw" / "prompt.txt").write_text("候选 chunk 原文", encoding="utf-8")
        problems = check_run_dir(run_dir)
        assert any("子目录" in problem for problem in problems)

    def test_over_long_field_is_refused_before_writing(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        with pytest.raises(ArtifactRedlineError):
            write_run_dir(
                run_dir,
                config=_config(),
                records=[_record(overlap_reason="正" * (MAX_STRING_FIELD + 1))],
                summary={"run_id": "test-run"},
            )
        assert not run_dir.exists() or not any(run_dir.iterdir())

    def test_nested_over_long_field_is_caught(self, tmp_path: Path) -> None:
        """长度检查必须递归到嵌套对象与数组——候选列表天然是数组，正文能藏在元素里。"""
        run_dir = tmp_path / "run"
        with pytest.raises(ArtifactRedlineError):
            write_run_dir(
                run_dir,
                config=_config(),
                records=[_record()],
                summary={"run_id": "x", "nested": {"deep": ["短", "正" * 600]}},
            )

    def test_run_config_carries_no_credential_fields(self) -> None:
        """`config.json` 进 git；把 Settings 整体 dump 进来会把 access key 写进仓库。"""
        keys = set(asdict(_config()))
        assert keys == {
            "run_id",
            "kind",
            "dataset_hash",
            "dataset_version",
            "golden_question_count",
            "evidence_count",
            "chunking_version",
            "tokenizer_id",
            "chunk_source",
            "mapper_model",
            "mapper_prompt_version",
            "mapper_provider",
            "deterministic_only",
        }
        assert not any("key" in key or "secret" in key or "password" in key for key in keys)


class TestFlattenReason:
    def test_newlines_collapse_and_length_is_capped(self) -> None:
        flattened = flatten_reason("第一行\n\n第二行\t第三行")
        assert "\n" not in flattened and "\t" not in flattened
        assert flattened == "第一行 第二行 第三行"

    def test_over_long_reason_is_truncated(self) -> None:
        assert len(flatten_reason("字" * 5000)) == MAX_REASON_CHARS


class TestFallback:
    async def test_picks_candidate_containing_the_evidence(self) -> None:
        mapper = FakeMapperModel()
        outcome = (await apply_fallback([_nomatch()], ["含目标证据"], [CANDIDATES], mapper))[0]
        assert outcome.match_status == MATCH_MATCHED
        assert outcome.matched_chunk_key == "book:1:chapter:1#c1"
        assert outcome.alternative_chunk_key == "book:1:chapter:1#c0"
        assert outcome.mapper_model == mapper.model

    async def test_already_matched_is_not_sent_to_the_model(self) -> None:
        mapper = FakeMapperModel()
        matched = replace(_nomatch(), match_status=MATCH_MATCHED)
        await apply_fallback([matched], ["证据"], [CANDIDATES], mapper)
        assert mapper.calls == []

    async def test_fabricated_key_is_discarded(self) -> None:
        mapper = FakeMapperModel(fabricate_key="book:1:chapter:999#c7")
        outcome = (await apply_fallback([_nomatch()], ["证据"], [CANDIDATES], mapper))[0]
        assert outcome.match_status == MATCH_UNMATCHED
        assert outcome.matched_chunk_key is None
        assert "不在候选集合内" in outcome.overlap_reason

    async def test_provider_failure_is_recorded_not_swallowed(self) -> None:
        class Boom:
            model = "boom"

            async def map_evidence(
                self, evidence_content: str, candidates: Sequence[MapperCandidate]
            ) -> MapperResult:
                raise RuntimeError("抖动")

        outcome = (await apply_fallback([_nomatch()], ["证据"], [CANDIDATES], Boom()))[0]
        assert outcome.match_status == MATCH_UNMATCHED
        assert "兜底映射失败" in outcome.overlap_reason

    async def test_empty_candidate_list_is_reported(self) -> None:
        outcome = (await apply_fallback([_nomatch()], ["证据"], [[]], FakeMapperModel()))[0]
        assert outcome.match_status == MATCH_UNMATCHED
        assert "无候选" in outcome.overlap_reason


class TestParseMapperOutput:
    def test_valid_payload(self) -> None:
        result = parse_mapper_output(
            '{"matched_chunk_key": "a#c1", "confidence": 0.8, '
            '"overlap_reason": "覆盖最高", "alternative_chunk_key": "a#c2"}',
            model="m",
        )
        assert result.matched_chunk_key == "a#c1"
        assert result.confidence == 0.8
        assert result.alternative_chunk_key == "a#c2"
        assert result.model == "m"

    def test_json_wrapped_in_prose_is_extracted(self) -> None:
        result = parse_mapper_output(
            '好的，结果如下：\n{"matched_chunk_key": "a#c1", "confidence": 1, '
            '"overlap_reason": "r", "alternative_chunk_key": null}\n以上。',
            model="m",
        )
        assert result.matched_chunk_key == "a#c1"
        assert result.alternative_chunk_key is None

    @pytest.mark.parametrize(
        "payload",
        [
            "完全不是 JSON",
            "[]",
            '{"matched_chunk_key": "a#c1"}',
            _payload(confidence='"高"'),
            _payload(confidence="true"),
            _payload(reason='"  "'),
        ],
    )
    def test_malformed_payloads_are_rejected(self, payload: str) -> None:
        with pytest.raises(MapperParseError):
            parse_mapper_output(payload, model="m")
