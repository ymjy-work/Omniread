"""分块（M0-3）单测：确定性、无跨章、prev/next、token 上限与 overlap。

真实语料抽查在无 `asset/` 的环境自动跳过（语料不入库，公共 CI 不带）。
"""

from __future__ import annotations

from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from omniread.domain.text import chapter_content_hash
from omniread.infrastructure.objectstore.corpus import read_corpus
from omniread.infrastructure.tokenizer import TokenCounter, get_token_counter
from omniread.pipelines.chunking import M0_PLACEHOLDER_V1, chunk_chapter
from omniread.pipelines.chunking.chunker import _tail_overlap

PROFILE = M0_PLACEHOLDER_V1

SENTENCE = "阿尔法在窗边读着书，阳光落在书页上。"

_REAL_CORPUS = (
    Path(__file__).resolve().parents[3]
    / "asset"
    / "《不时轻声地以俄语遮羞的邻座艾莉同学》"
)


@pytest.fixture(scope="module")
def counter() -> TokenCounter:
    return get_token_counter()


def _chapter_text(marker: str, count: int) -> str:
    return "".join(f"{marker}编号{index}号。\n\n" for index in range(count))


@pytest.mark.parametrize(
    "text", ["", "很短的一句。", SENTENCE * 400], ids=["empty", "short", "long"]
)
def test_chunk_chapter_is_deterministic(text: str, counter: TokenCounter) -> None:
    first = chunk_chapter("book:1:chapter:7", text, PROFILE, counter)
    second = chunk_chapter("book:1:chapter:7", text, PROFILE, counter)
    assert first == second


def test_chunk_indices_and_neighbor_keys_form_a_chain(counter: TokenCounter) -> None:
    chunks = chunk_chapter("book:1:chapter:7", SENTENCE * 400, PROFILE, counter)

    assert len(chunks) > 2
    for index, chunk in enumerate(chunks):
        assert chunk.chunk_key == f"book:1:chapter:7#c{index}"
        assert chunk.chunk_index == index
    assert chunks[0].prev_chunk_key is None
    assert chunks[-1].next_chunk_key is None
    for previous, following in pairwise(chunks):
        assert previous.next_chunk_key == following.chunk_key
        assert following.prev_chunk_key == previous.chunk_key


def test_token_count_and_content_hash_match_content(counter: TokenCounter) -> None:
    chunks = chunk_chapter("book:1:chapter:9", SENTENCE * 120, PROFILE, counter)

    for chunk in chunks:
        assert chunk.token_count == counter.count(chunk.content)
        assert chunk.content_hash == chapter_content_hash(chunk.content)


def test_every_chunk_stays_within_max_tokens(counter: TokenCounter) -> None:
    chunks = chunk_chapter("book:1:chapter:11", SENTENCE * 400, PROFILE, counter)

    assert chunks
    assert all(chunk.token_count <= PROFILE.max_chunk_tokens for chunk in chunks)


def test_chunks_do_not_bleed_across_chapters(counter: TokenCounter) -> None:
    alpha = _chapter_text("阿尔法", 120)
    beta = _chapter_text("贝塔", 120)

    alpha_chunks = chunk_chapter("book:1:chapter:1", alpha, PROFILE, counter)
    beta_chunks = chunk_chapter("book:1:chapter:2", beta, PROFILE, counter)

    assert alpha_chunks and beta_chunks
    assert all("贝塔" not in chunk.content for chunk in alpha_chunks)
    assert all("阿尔法" not in chunk.content for chunk in beta_chunks)
    assert all(chunk.chunk_key.startswith("book:1:chapter:1#") for chunk in alpha_chunks)
    assert all(chunk.chunk_key.startswith("book:1:chapter:2#") for chunk in beta_chunks)


def test_over_long_sentence_is_hard_split_with_tail_overlap(counter: TokenCounter) -> None:
    # 无句末标点 = 单句；长度必须超过 600 token 才触发硬切。
    long_sentence = "这是一句没有句末标点的超长句子用于验证按 token 硬切" * 80
    assert counter.count(long_sentence) > PROFILE.max_chunk_tokens

    chunks = chunk_chapter("book:1:chapter:3", long_sentence, PROFILE, counter)

    assert len(chunks) >= 2
    assert all(chunk.token_count <= PROFILE.max_chunk_tokens for chunk in chunks)
    for previous, following in pairwise(chunks):
        overlap = _tail_overlap(previous.content, PROFILE, counter)
        assert overlap
        assert following.content.startswith(overlap)
        assert counter.count(overlap) <= PROFILE.overlap_tokens


def test_overlap_falls_back_to_tail_window_when_last_sentence_is_too_long(
    counter: TokenCounter,
) -> None:
    content = "短句。" + "没有标点的长尾段落" * 40

    overlap = _tail_overlap(content, PROFILE, counter)

    assert content.endswith(overlap)
    assert 0 < counter.count(overlap) <= PROFILE.overlap_tokens
    # 尾句超长 → 取末尾 token 窗，而不是整句。
    assert overlap == counter.tail(content, PROFILE.overlap_tokens)


def test_overlap_prefers_complete_tail_sentences(counter: TokenCounter) -> None:
    content = "甲乙丙丁。戊己庚辛。" * 8

    overlap = _tail_overlap(content, PROFILE, counter)

    assert content.endswith(overlap)
    assert overlap.endswith("。")
    assert 0 < counter.count(overlap) <= PROFILE.overlap_tokens


def test_empty_chapter_yields_no_chunks(counter: TokenCounter) -> None:
    assert chunk_chapter("book:1:chapter:4", "", PROFILE, counter) == []


def test_very_short_chapter_yields_one_chunk(counter: TokenCounter) -> None:
    chunks = chunk_chapter("book:1:chapter:5", SENTENCE, PROFILE, counter)

    assert len(chunks) == 1
    assert chunks[0].content == SENTENCE
    assert chunks[0].prev_chunk_key is None
    assert chunks[0].next_chunk_key is None


def test_single_over_long_sentence_only_chapter_does_not_crash(
    counter: TokenCounter,
) -> None:
    long_sentence = "超长单句" * 400

    chunks = chunk_chapter("book:1:chapter:6", long_sentence, PROFILE, counter)

    assert len(chunks) >= 2
    assert all(chunk.token_count <= PROFILE.max_chunk_tokens for chunk in chunks)
    assert all(chunk.content for chunk in chunks)


def test_cross_chapter_profile_is_rejected(counter: TokenCounter) -> None:
    with pytest.raises(ValueError, match="cross_chapter"):
        chunk_chapter(
            "book:1:chapter:8",
            SENTENCE,
            replace(PROFILE, cross_chapter=True),
            counter,
        )


@pytest.mark.skipif(not (_REAL_CORPUS / "index.jsonl").is_file(), reason="本机无正式语料")
def test_real_corpus_samples_respect_limit_and_overlap(counter: TokenCounter) -> None:
    corpus = read_corpus(_REAL_CORPUS)
    sampled = [corpus.chapters[index] for index in (0, 48, 119, 192)]

    for chapter in sampled:
        chunks = chunk_chapter(chapter.chapter_id, chapter.text, PROFILE, counter)
        assert chunks
        assert all(chunk.chunk_key.startswith(f"{chapter.chapter_id}#") for chunk in chunks)
        assert all(chunk.token_count == counter.count(chunk.content) for chunk in chunks)
        assert all(chunk.token_count <= PROFILE.max_chunk_tokens for chunk in chunks)
        for previous, following in pairwise(chunks):
            assert following.prev_chunk_key == previous.chunk_key
            assert previous.next_chunk_key == following.chunk_key
            overlap = _tail_overlap(previous.content, PROFILE, counter)
            assert overlap
            assert following.content.startswith(overlap)
            assert counter.count(overlap) <= PROFILE.overlap_tokens
