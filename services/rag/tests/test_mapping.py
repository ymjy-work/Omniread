"""evidence → chunk 映射（M0-7b）单测：区间还原、判据档位、多覆盖定主次、失败不静默。

真实语料与 Golden 的联测在缺 `asset/` 的环境自动跳过（语料不入库，公共 CI 不带）。
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest

from omniread.domain.text import evidence_hash, normalize_minimal
from omniread.pipelines.chunking import chunk_chapter
from omniread.pipelines.mapping import (
    MATCH_LOW_CONF,
    MATCH_MATCHED,
    MATCH_UNMATCHED,
    TIER_INTRODUCER,
    TIER_MAX_COVERAGE,
    TIER_NONE,
    TIER_PARTIAL,
    TIER_UNIQUE_COVER,
    ChunkSpanError,
    map_evidence_deterministic,
    spans_from_contents,
)

PROMPT_VERSION = "0123456789abcdef"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_CORPUS = _REPO_ROOT / "asset" / "《不时轻声地以俄语遮羞的邻座艾莉同学》"
_GOLDEN = _REPO_ROOT / "eval" / "golden"


def _long_chapter(sentence: str, times: int) -> str:
    """拼出一章长到必然切成多块的正文（600 token 上限，约 1.23 汉字/token）。

    每节带序号，使任意一段切片在全章**位置唯一**——不加序号的话，同一句重复出现会让
    「只覆盖该切片」的块不唯一，测的就不是映射逻辑而是文本是否重复。
    """
    return "\n\n".join(f"第{index:03d}节　{sentence}" for index in range(times))


def _build(sentence: str = "阿尔法在窗边读着书，阳光落在书页上。", times: int = 120):
    chapter_id = "book:1:chapter:7"
    text = _long_chapter(sentence, times)
    drafts = chunk_chapter(chapter_id, text)
    spans = spans_from_contents(chapter_id, text, [d.content for d in drafts])
    return chapter_id, text, spans


def _map(text: str, chapter_id: str, content: str, spans):
    return map_evidence_deterministic(
        text,
        content,
        spans,
        evidence_hash=evidence_hash(chapter_id, content),
        chapter_id=chapter_id,
        mapper_prompt_version=PROMPT_VERSION,
    )


class TestSpans:
    def test_spans_are_contiguous_slices(self) -> None:
        _, text, spans = _build()
        assert len(spans) > 1, "样例章节应切出多块"
        for span in spans:
            key = span.chunk_key
            index = span.chunk_index
            assert key == f"{span.chapter_id}#c{index}"
            assert 0 <= span.start < span.end <= len(text)

    def test_overlap_prefix_matches_previous_tail(self) -> None:
        _, _text, spans = _build()
        assert spans[0].overlap_len == 0
        for previous, span in pairwise(spans):
            assert span.overlap_len == previous.end - span.start
            assert span.overlap_len > 0, "本例每一块都应带上一块的尾 overlap"

    def test_non_slice_content_raises(self) -> None:
        chapter_id = "book:1:chapter:7"
        text = "甲。乙。丙。"
        with pytest.raises(ChunkSpanError):
            spans_from_contents(chapter_id, text, ["甲。", "不存在的正文。"])


class TestDeterministic:
    def test_single_cover(self) -> None:
        chapter_id, text, spans = _build()
        content = text[spans[1].start + spans[1].overlap_len :][:20]
        outcome = _map(text, chapter_id, content, spans)
        assert outcome.match_status == MATCH_MATCHED
        assert outcome.decision_tier == TIER_UNIQUE_COVER
        assert outcome.matched_chunk_key == spans[1].chunk_key
        assert outcome.alternative_chunk_key is None
        assert outcome.confidence == 1.0

    def test_boundary_evidence_picks_introducer(self) -> None:
        """跨块边界的 evidence 被两块完整包含，主块取**引入者**（较早那块）。"""
        chapter_id, text, spans = _build()
        first, second = spans[0], spans[1]
        # 取到节号，保证这段文本在章内只出现一次；否则测的是重复文本而非边界判定
        content = text[first.end - 30 : first.end]
        assert text.count(content) == 1

        outcome = _map(text, chapter_id, content, spans)

        assert outcome.match_status == MATCH_MATCHED
        assert outcome.decision_tier == TIER_INTRODUCER
        assert outcome.matched_chunk_key == first.chunk_key
        assert outcome.alternative_chunk_key == second.chunk_key

    def test_repeated_evidence_considers_every_occurrence(self) -> None:
        """章内重复出现的证据要扫描全部位置，不能只看第一次出现。

        `书，阳光落在书页上。\\n\\n` 在每节末尾都出现，因此每个 chunk 都含它；
        只看第一次出现会给出「唯一覆盖」的片面结论。
        """
        chapter_id, text, spans = _build()
        content = "书，阳光落在书页上。\n\n"
        assert text.count(content) > 1

        outcome = _map(text, chapter_id, content, spans)

        assert outcome.match_status == MATCH_MATCHED
        assert outcome.decision_tier == TIER_MAX_COVERAGE
        assert outcome.matched_chunk_key == spans[0].chunk_key  # 多个归属时取章内最早的块
        assert outcome.alternative_chunk_key == spans[1].chunk_key
        assert f"{len(spans)} 个 chunk 完整包含" in outcome.overlap_reason

    def test_line_endings_and_trailing_blanks_are_normalized(self) -> None:
        """映射用的 content 与导入时的正文走同一个 normalize_minimal，CRLF 与行尾空白不影响判定。

        只做 P-3 的两种统一；空行不折叠，所以这里不给行尾加换行，只加空白。
        """
        chapter_id, text, spans = _build()
        content = text[spans[1].start + spans[1].overlap_len :][:20]
        noisy = "\r\n".join(line + "   " for line in content.split("\n"))
        outcome = _map(text, chapter_id, noisy, spans)
        assert outcome.match_status == MATCH_MATCHED
        assert outcome.matched_chunk_key == spans[1].chunk_key

    def test_content_not_in_chapter_is_unmatched(self) -> None:
        chapter_id, text, spans = _build()
        outcome = _map(text, chapter_id, "这段话在本章里根本不存在。", spans)
        assert outcome.match_status == MATCH_UNMATCHED
        assert outcome.matched_chunk_key is None
        assert outcome.confidence == 0.0
        assert outcome.decision_tier == TIER_NONE

    def test_partially_covered_is_low_conf_not_matched(self) -> None:
        """没有任何块完整包含时不冒充命中；部分重叠如实记 low_conf。"""
        chapter_id = "book:1:chapter:7"
        text = normalize_minimal("阿尔法走进教室，看见窗外在下雪。")
        # 人为造出「只与某块部分重叠」的 evidence：取其末尾若干字再接一节章外文本
        spans = spans_from_contents(chapter_id, text, [text])
        content = text[-8:] + "这段接在章外。"
        outcome = _map(text, chapter_id, content, spans)
        assert outcome.match_status == MATCH_UNMATCHED  # 整段不是子串 → 未命中

        # 构造真正「是子串但被截断覆盖」的情形：区块只覆盖前半
        partial_text = normalize_minimal("甲甲甲甲。乙乙乙乙。丙丙丙丙。")
        partial_spans = spans_from_contents(
            chapter_id, partial_text, ["甲甲甲甲。乙乙乙乙。"]
        )
        straddle = partial_text[6:14]  # 跨越该块右边界
        outcome2 = _map(partial_text, chapter_id, straddle, partial_spans)
        assert outcome2.match_status == MATCH_LOW_CONF
        assert outcome2.decision_tier == TIER_PARTIAL
        assert outcome2.matched_chunk_key == partial_spans[0].chunk_key


pytestmark_corpus = pytest.mark.skipif(
    not _REAL_CORPUS.is_dir() or not _GOLDEN.is_dir(),
    reason="真实语料或 Golden 不在本机（语料不入库）",
)


@pytestmark_corpus
class TestAgainstRealGolden:
    def _chapters(self) -> dict[str, str]:
        index = [
            json.loads(line)
            for line in (_REAL_CORPUS / "index.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        return {
            f"book:1:chapter:{position}": normalize_minimal(entry["text"])
            for position, entry in enumerate(index, start=1)
        }

    def test_every_evidence_maps_to_a_chunk_in_its_own_chapter(self) -> None:
        chapters = self._chapters()
        span_cache: dict[str, list] = {}
        total = 0
        tiers: dict[str, int] = {}

        for path in sorted(_GOLDEN.glob("*.json")):
            if path.name in {"schema.json", "example.json"}:
                continue
            question = json.loads(path.read_text(encoding="utf-8"))
            for group in question["must_cite_groups"]:
                for evidence in group:
                    total += 1
                    chapter_id = evidence["chapter_id"]
                    text = chapters[chapter_id]
                    if chapter_id not in span_cache:
                        drafts = chunk_chapter(chapter_id, text)
                        span_cache[chapter_id] = spans_from_contents(
                            chapter_id, text, [d.content for d in drafts]
                        )
                    spans = span_cache[chapter_id]
                    outcome = _map(text, chapter_id, evidence["content"], spans)

                    assert outcome.match_status == MATCH_MATCHED, (
                        f"{question['id']} :: {outcome.overlap_reason}"
                    )
                    keys = {span.chunk_key for span in spans}
                    assert outcome.matched_chunk_key in keys
                    if outcome.alternative_chunk_key is not None:
                        assert outcome.alternative_chunk_key in keys
                        assert outcome.alternative_chunk_key != outcome.matched_chunk_key
                    tiers[outcome.decision_tier] = tiers.get(outcome.decision_tier, 0) + 1

        assert total == 357
        assert tiers.get(TIER_INTRODUCER, 0) > 0, "跨块边界的样例不该为空，否则这条测试没覆盖到边界"
        # 三条档位之外不该出现：出现 partial/none 说明有证据没被任何块完整包含，
        # 那是必须显式暴露的事实，不该被这条测试放过。
        assert set(tiers) <= {TIER_UNIQUE_COVER, TIER_INTRODUCER, TIER_MAX_COVERAGE}, tiers
