import pytest

from app.rag.realm import InvalidRealmError, chapter_range


@pytest.mark.parametrize("progress", [1, 100, 193])
def test_past_returns_reading_range(progress: int) -> None:
    assert chapter_range("past", progress) == (1, progress)


def test_full_returns_all_chapters() -> None:
    assert chapter_range("full", None) == (1, None)


@pytest.mark.parametrize("progress", [None, 0, -1, 194])
def test_past_rejects_invalid_progress(progress: int | None) -> None:
    with pytest.raises(InvalidRealmError):
        chapter_range("past", progress)
