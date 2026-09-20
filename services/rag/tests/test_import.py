"""导入映射（M0-3）单测：卷序号首现次序、章行号、chunk 标识与确定性。

真库上的幂等与 prev/next 回填由 `scripts/import-corpus.sh` 跑完后的 SQL 抽检验证；
这里只测不碰库的 `build_import_plan`，以及语料缺正文的硬错误。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniread.domain.text import chapter_content_hash, normalize_minimal
from omniread.infrastructure.objectstore.corpus import (
    Corpus,
    CorpusChapter,
    CorpusFormatError,
    read_corpus,
)
from omniread.infrastructure.tokenizer import TokenCounter, get_token_counter
from omniread.pipelines.chunking import M0_PLACEHOLDER_V1
from omniread.pipelines.importing import build_import_plan

SENTENCE = "阿尔法在窗边读着书，阳光落在书页上。"


@pytest.fixture(scope="module")
def counter() -> TokenCounter:
    return get_token_counter()


def _chapter(
    chapter_index: int,
    volume_title: str,
    raw_text: str,
    image_paths: tuple[str, ...] = (),
) -> CorpusChapter:
    return CorpusChapter(
        chapter_index=chapter_index,
        chapter_id=f"book:1:chapter:{chapter_index}",
        volume_title=volume_title,
        title=f"第{chapter_index}话",
        source_id=f"src-{chapter_index}",
        source_url=f"https://example.invalid/{chapter_index}",
        text=normalize_minimal(raw_text),
        image_paths=image_paths,
        content_hash=chapter_content_hash(raw_text),
    )


def _corpus(chapters: list[CorpusChapter]) -> Corpus:
    return Corpus(
        book_id=1,
        title="测试书",
        author="测试作者",
        corpus_version="corpus-deadbeef",
        chapters=tuple(chapters),
        volume_titles=tuple(dict.fromkeys(chapter.volume_title for chapter in chapters)),
        index_bytes=b"",
        description_bytes=b"",
    )


def test_volume_index_follows_first_appearance(counter: TokenCounter) -> None:
    corpus = _corpus(
        [
            _chapter(1, "第十卷", SENTENCE),
            _chapter(2, "第一卷", SENTENCE),
            _chapter(3, "第十卷", SENTENCE),
            _chapter(4, "短篇", SENTENCE),
        ]
    )

    plan = build_import_plan(corpus, counter=counter)

    # 次序按 vol 首次出现，不按数字排（M0-02 §1）。
    assert [(volume.volume_index, volume.title) for volume in plan.volumes] == [
        (1, "第十卷"),
        (2, "第一卷"),
        (3, "短篇"),
    ]
    assert [chapter.volume_index for chapter in plan.chapters] == [1, 2, 1, 3]


def test_chapter_fields_reuse_corpus_normalization_and_hash(counter: TokenCounter) -> None:
    raw = "第一段。\r\n\r\n第二段。  \r\n"
    raw_chapter = _chapter(5, "第一卷", raw)

    plan = build_import_plan(_corpus([raw_chapter]), counter=counter)

    [chapter] = plan.chapters
    assert chapter.chapter_index == 5
    assert chapter.chapter_id == "book:1:chapter:5"
    assert chapter.text == normalize_minimal(raw)
    assert "\r" not in chapter.text
    assert chapter.content_hash == chapter_content_hash(raw)
    assert chapter.char_count == len(chapter.text)


def test_chapter_rows_carry_image_paths(counter: TokenCounter) -> None:
    # 图片路径原样从 index.jsonl[].images 带进 chapters.image_paths（M0-02 §2），
    # 目录接口据此重建 marker→url；无图章保持空元组。
    images = ("images/01_第1卷/007.jpg", "images/01_第1卷/008.jpg")
    plan = build_import_plan(
        _corpus(
            [
                _chapter(1, "第一卷", SENTENCE, image_paths=images),
                _chapter(2, "第一卷", SENTENCE),
            ]
        ),
        counter=counter,
    )

    assert plan.chapters[0].image_paths == images
    assert plan.chapters[1].image_paths == ()


def test_chunk_rows_carry_frozen_profile_identifiers(counter: TokenCounter) -> None:
    plan = build_import_plan(
        _corpus([_chapter(7, "第一卷", SENTENCE * 400)]), counter=counter
    )

    assert len(plan.chunks) > 1
    for index, chunk in enumerate(plan.chunks):
        assert chunk.chunk_key == f"book:1:chapter:7#c{index}"
        assert chunk.chapter_id == "book:1:chapter:7"
        assert chunk.chapter_index == 7
        assert chunk.chunk_index == index
        assert chunk.token_count == counter.count(chunk.content)
        assert chunk.token_count <= M0_PLACEHOLDER_V1.max_chunk_tokens
        assert chunk.content_hash == chapter_content_hash(chunk.content)
        assert chunk.chunking_version == M0_PLACEHOLDER_V1.profile_id == "m0-placeholder-v1"
        assert chunk.tokenizer_id == M0_PLACEHOLDER_V1.tokenizer_id


def test_chunk_indices_restart_in_every_chapter(counter: TokenCounter) -> None:
    corpus = _corpus(
        [
            _chapter(1, "第一卷", SENTENCE * 400),
            _chapter(2, "第一卷", SENTENCE * 30),
        ]
    )

    plan = build_import_plan(corpus, counter=counter)

    per_chapter: dict[str, list[int]] = {}
    for chunk in plan.chunks:
        per_chapter.setdefault(chunk.chapter_id, []).append(chunk.chunk_index)
    assert set(per_chapter) == {"book:1:chapter:1", "book:1:chapter:2"}
    for indices in per_chapter.values():
        assert indices == list(range(len(indices)))


def test_plan_is_deterministic(counter: TokenCounter) -> None:
    corpus = _corpus(
        [
            _chapter(1, "第一卷", SENTENCE * 400),
            _chapter(2, "短篇", SENTENCE * 50),
        ]
    )

    assert build_import_plan(corpus, counter=counter) == build_import_plan(
        corpus, counter=counter
    )


def test_empty_chapter_text_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "说明.md").write_text("# 《测试书》\n作者：测试作者\n", encoding="utf-8")
    row = {
        "id": "1",
        "vol": "第一卷",
        "title": "第1话",
        "url": "https://example.invalid/1",
        "images": [],
        "text": "   \n",
    }
    (root / "index.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", "utf-8")

    # 空正文必须报错，不得静默跳过（分母失真的数据比没有数据更危险）。
    with pytest.raises(CorpusFormatError, match="text 缺失或为空"):
        read_corpus(root)
