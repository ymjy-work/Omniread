import numpy as np

from app.db.models import Chunk
from app.rag.citations import REFUSAL_ANSWER, validate_citations


def make_chunk(
    chunk_id: int,
    chapter_index: int,
    text: str,
    chapter_id: str | None = None,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        book_id=1,
        chapter_id=chapter_id or f"book:1:chapter:{chapter_index}",
        chapter_index=chapter_index,
        title=f"第{chapter_index}章",
        text=text,
        vector=np.zeros(4, dtype=np.float32),
    )


def test_valid_citations_use_chunk_quote_and_strip_markers() -> None:
    chunks = [make_chunk(1, 2, "证据甲"), make_chunk(2, 3, "证据乙")]
    result = validate_citations("答案。[[chunk:1]] 补充。[[chunk:2]]", chunks)

    assert "[[chunk:" not in result.answer
    assert [item.chapter_index for item in result.citations] == [2, 3]
    assert [item.quote for item in result.citations] == ["证据甲", "证据乙"]


def test_citations_dedupe_by_chapter_keeping_first_chunk_quote() -> None:
    chunks = [
        make_chunk(1, 2, "证据甲"),
        make_chunk(2, 2, "证据甲后段"),
        make_chunk(3, 3, "证据乙"),
    ]
    result = validate_citations(
        "答案。[[chunk:1]][[chunk:2]][[chunk:3]]", chunks
    )

    assert [item.chapter_id for item in result.citations] == [
        "book:1:chapter:2",
        "book:1:chapter:3",
    ]
    assert [item.quote for item in result.citations] == ["证据甲", "证据乙"]


def test_invalid_citation_is_removed_and_refuses() -> None:
    chunks = [make_chunk(1, 1, "证据")]
    result = validate_citations("答案。[[chunk:99]]", chunks)

    assert result.answer == REFUSAL_ANSWER
    assert result.citations == []


def test_mixed_citations_keep_only_whitelist() -> None:
    chunks = [make_chunk(1, 1, "证据")]
    result = validate_citations("保留。[[chunk:1]] 丢弃。[[chunk:2]]", chunks)

    assert result.answer == "保留。 丢弃。"
    assert len(result.citations) == 1
    assert result.citations[0].chapter_id == "book:1:chapter:1"


def test_answer_without_citation_refuses() -> None:
    result = validate_citations("没有引用", [make_chunk(1, 1, "证据")])

    assert result.answer == REFUSAL_ANSWER
    assert result.citations == []


def test_no_candidates_refuses_without_parsing() -> None:
    result = validate_citations("答案。[[chunk:1]]", [])

    assert result.answer == REFUSAL_ANSWER
    assert result.citations == []
