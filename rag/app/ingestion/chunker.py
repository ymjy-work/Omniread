from dataclasses import dataclass

from app.schemas import ChapterInput

DEFAULT_CHUNK_SIZE = 600


@dataclass(frozen=True, slots=True)
class ChapterChunk:
    chapter_id: str
    chapter_index: int
    title: str
    text: str


def _split_long_paragraph(paragraph: str, chunk_size: int) -> list[str]:
    return [
        paragraph[start : start + chunk_size]
        for start in range(0, len(paragraph), chunk_size)
    ]


def chunk_chapter(
    chapter: ChapterInput, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> list[ChapterChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    normalized = chapter.text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [part.strip() for part in normalized.split("\n\n") if part.strip()]

    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            pieces.extend(_split_long_paragraph(paragraph, chunk_size))
        else:
            pieces.append(paragraph)

    chunks: list[ChapterChunk] = []
    current = ""
    for piece in pieces:
        candidate = piece if not current else f"{current}\n\n{piece}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = piece
    if current:
        chunks.append(current)

    return [
        ChapterChunk(
            chapter_id=chapter.chapter_id,
            chapter_index=chapter.chapter_index,
            title=chapter.title,
            text=text,
        )
        for text in chunks
    ]


def chunk_chapters(
    chapters: list[ChapterInput], chunk_size: int = DEFAULT_CHUNK_SIZE
) -> list[ChapterChunk]:
    chunks: list[ChapterChunk] = []
    for chapter in chapters:
        chunks.extend(chunk_chapter(chapter, chunk_size=chunk_size))
    return chunks
