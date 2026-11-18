import re
from dataclasses import dataclass

from app.db.models import Chunk
from app.schemas import Citation

REFUSAL_ANSWER = "根据已读内容无法回答。"
CITATION_PATTERN = re.compile(r"\[\[chunk:(\d+)\]\]")


@dataclass(frozen=True, slots=True)
class CitationResult:
    answer: str
    citations: list[Citation]


def extract_citation_ids(text: str) -> list[int]:
    return [int(match.group(1)) for match in CITATION_PATTERN.finditer(text)]


def strip_citation_markers(text: str) -> str:
    return CITATION_PATTERN.sub("", text).strip()


def refusal() -> CitationResult:
    return CitationResult(answer=REFUSAL_ANSWER, citations=[])


def validate_citations(
    answer: str, chunks: list[Chunk], cited_ids: list[int] | None = None
) -> CitationResult:
    whitelist = {chunk.id: chunk for chunk in chunks}
    if not whitelist:
        return refusal()

    ids = extract_citation_ids(answer) if cited_ids is None else cited_ids
    valid_ids: list[int] = []
    seen: set[int] = set()
    for chunk_id in ids:
        if chunk_id in whitelist and chunk_id not in seen:
            seen.add(chunk_id)
            valid_ids.append(chunk_id)

    cleaned_answer = strip_citation_markers(answer)
    if not valid_ids or not cleaned_answer:
        return refusal()

    return CitationResult(
        answer=cleaned_answer,
        citations=[
            Citation(
                chapter_id=whitelist[chunk_id].chapter_id,
                chapter_index=whitelist[chunk_id].chapter_index,
                title=whitelist[chunk_id].title,
                quote=whitelist[chunk_id].text,
            )
            for chunk_id in valid_ids
        ],
    )
