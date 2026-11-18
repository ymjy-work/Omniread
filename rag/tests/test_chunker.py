from app.ingestion.chunker import chunk_chapter, chunk_chapters
from app.schemas import ChapterInput


def chapter(index: int, text: str) -> ChapterInput:
    return ChapterInput(
        chapter_id=f"book:1:chapter:{index}",
        chapter_index=index,
        title=f"第{index}章",
        text=text,
    )


def test_merges_paragraphs_within_one_chapter() -> None:
    text = ("甲" * 250) + "\n\n" + ("乙" * 250)
    chunks = chunk_chapter(chapter(1, text))

    assert len(chunks) == 1
    assert chunks[0].text == text


def test_does_not_cross_chapters() -> None:
    chapters = [chapter(1, "甲" * 500), chapter(2, "乙" * 500)]
    chunks = chunk_chapters(chapters)

    assert len(chunks) == 2
    assert chunks[0].chapter_index == 1
    assert chunks[0].text == "甲" * 500
    assert chunks[1].chapter_index == 2
    assert chunks[1].text == "乙" * 500


def test_splits_long_paragraph_without_overlap() -> None:
    text = "".join(str(index % 10) for index in range(1300))
    chunks = chunk_chapter(chapter(3, text))

    assert [len(item.text) for item in chunks] == [600, 600, 100]
    assert "".join(item.text for item in chunks) == text


def test_empty_text_produces_no_chunks() -> None:
    assert chunk_chapter(chapter(1, "\n\n  \n")) == []
