"""语料读取、校验与导入清单 / 逐章校验和（M0-02 §2、§4）。

`index.jsonl` 是唯一数据源：每行自带 `text` 正文，行号即 `chapter_index`。
任一行缺字段、正文为空或引用图片缺失都直接抛 `CorpusFormatError`，不静默跳过——
分母失真的数据比没有数据更危险（M0-02 §2）。

逐章 hash 复用 `omniread.domain.text`，与 `chapters.content_hash` 同源，
不在这里另写一份实现，避免「同一段正文两个值」。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from omniread.domain.text import chapter_content_hash, normalize_minimal, sha256_hex

INDEX_NAME = "index.jsonl"
DESCRIPTION_NAME = "说明.md"

# 规范化口径标识，写进 checksums.json：重算时据此确认两边用的是同一口径。
NORMALIZATION_ID = "m0-minimal-v1"

_REQUIRED_FIELDS = ("id", "vol", "title", "url", "images", "text")
_TEXT_FIELDS = ("id", "vol", "title", "url")
_TITLE_RE = re.compile(r"《(.+?)》")
_AUTHOR_RE = re.compile(r"作者[：:]\s*([^\s　，,、；;]+)")
_TITLE_SUFFIXES = ("文库精校版",)


class CorpusFormatError(ValueError):
    """语料不合法。导入期错误，不映射为对外错误码。"""


@dataclass(frozen=True, slots=True)
class CorpusChapter:
    chapter_index: int
    chapter_id: str
    volume_title: str
    title: str
    source_id: str
    source_url: str
    text: str
    image_paths: tuple[str, ...]
    content_hash: str


@dataclass(frozen=True, slots=True)
class Corpus:
    book_id: int
    title: str
    author: str
    corpus_version: str
    chapters: tuple[CorpusChapter, ...]
    volume_titles: tuple[str, ...]
    index_bytes: bytes
    description_bytes: bytes


def chapter_id(book_id: int, chapter_index: int) -> str:
    """`book:{book_id}:chapter:{chapter_index}`（M0-02 §1）。"""
    return f"book:{book_id}:chapter:{chapter_index}"


def derive_corpus_version(index_bytes: bytes) -> str:
    """默认语料版本取 index.jsonl 原始字节 sha256 的前 12 位。

    内容定址：语料一改版本即变，与「corpus hash 变化即新基线」（M0-02 §7.3）一致；
    调用方可用 `corpus_version` 参数覆盖。
    """
    return "corpus-" + sha256(index_bytes).hexdigest()[:12]


def read_corpus(
    root: Path,
    book_id: int = 1,
    corpus_version: str | None = None,
) -> Corpus:
    """读取并校验语料根目录；任一处不合法即抛 `CorpusFormatError`。"""
    root = Path(root)
    index_path = root / INDEX_NAME
    description_path = root / DESCRIPTION_NAME
    if not index_path.is_file():
        raise CorpusFormatError(f"缺少语料索引：{index_path}")
    if not description_path.is_file():
        raise CorpusFormatError(f"缺少来源说明：{description_path}")

    index_bytes = index_path.read_bytes()
    description_bytes = description_path.read_bytes()
    description = _decode(description_bytes, DESCRIPTION_NAME)
    chapters = _parse_index(index_bytes, book_id)
    volumes = tuple(dict.fromkeys(chapter.volume_title for chapter in chapters))
    return Corpus(
        book_id=book_id,
        title=_parse_title(description),
        author=_parse_author(description),
        corpus_version=corpus_version or derive_corpus_version(index_bytes),
        chapters=chapters,
        volume_titles=volumes,
        index_bytes=index_bytes,
        description_bytes=description_bytes,
    )


def build_manifest(corpus: Corpus, imported_at: datetime) -> dict[str, object]:
    """导入清单：书名、作者、corpus_version、章节数、卷数、导入时间（M0-02 §4）。"""
    return {
        "book_id": corpus.book_id,
        "title": corpus.title,
        "author": corpus.author,
        "corpus_version": corpus.corpus_version,
        "chapter_count": len(corpus.chapters),
        "volume_count": len(corpus.volume_titles),
        "imported_at": _iso_utc(imported_at),
    }


def build_checksums(corpus: Corpus) -> dict[str, object]:
    """逐章 hash 及其汇总 `corpus_manifest_hash`（M0-02 §4、§7）。"""
    entries: list[dict[str, object]] = [
        {
            "chapter_index": chapter.chapter_index,
            "chapter_id": chapter.chapter_id,
            "content_hash": chapter.content_hash,
        }
        for chapter in corpus.chapters
    ]
    return {
        "book_id": corpus.book_id,
        "algorithm": "sha256",
        "normalization": NORMALIZATION_ID,
        "chapters": entries,
        "corpus_manifest_hash": corpus_manifest_hash(entries),
    }


def corpus_manifest_hash(entries: Sequence[Mapping[str, object]]) -> str:
    """逐章 hash 的汇总口径，与 `rag_runs.corpus_manifest_hash` 共用。

    按 chapter_index 升序把 `chapter_index \\t chapter_id \\t content_hash \\n` 拼接后取 sha256；
    口径定死才能重算对齐——否则两次 run 是否可比只能靠人记。
    """
    canonical = "".join(
        f"{entry['chapter_index']}\t{entry['chapter_id']}\t{entry['content_hash']}\n"
        for entry in entries
    )
    return sha256_hex(canonical)


def dumps_canonical(document: Mapping[str, object] | Sequence[object]) -> bytes:
    """固定键序（按构造顺序）、UTF-8、缩进 2、末尾一个换行；落盘与上传共用同一份字节。"""
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _parse_index(index_bytes: bytes, book_id: int) -> tuple[CorpusChapter, ...]:
    raw = _decode(index_bytes, INDEX_NAME)
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        # 末尾换行产生的空元素，不是空章节。
        lines.pop()
    if not lines:
        raise CorpusFormatError("index.jsonl 没有任何章节")

    chapters: list[CorpusChapter] = []
    for chapter_index, line in enumerate(lines, start=1):
        if not line.strip():
            raise CorpusFormatError(
                f"index.jsonl 第 {chapter_index} 行为空行；行号必须与 chapter_index 一一对应"
            )
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CorpusFormatError(
                f"index.jsonl 第 {chapter_index} 行不是合法 JSON：{exc}"
            ) from exc
        if not isinstance(record, dict):
            raise CorpusFormatError(f"index.jsonl 第 {chapter_index} 行不是 JSON 对象")

        missing = [field for field in _REQUIRED_FIELDS if field not in record]
        if missing:
            raise CorpusFormatError(
                f"index.jsonl 第 {chapter_index} 行缺少字段：{'、'.join(missing)}"
            )
        for field in _TEXT_FIELDS:
            value = record[field]
            if not isinstance(value, str) or not value.strip():
                raise CorpusFormatError(f"index.jsonl 第 {chapter_index} 行 {field} 缺失或为空")
        text = record["text"]
        if not isinstance(text, str) or not text.strip():
            raise CorpusFormatError(f"index.jsonl 第 {chapter_index} 行 text 缺失或为空")
        images = record["images"]
        if not isinstance(images, list) or any(
            not isinstance(path, str) or not path for path in images
        ):
            raise CorpusFormatError(f"index.jsonl 第 {chapter_index} 行 images 不是字符串数组")

        chapters.append(
            CorpusChapter(
                chapter_index=chapter_index,
                chapter_id=chapter_id(book_id, chapter_index),
                volume_title=record["vol"],
                title=record["title"],
                source_id=record["id"],
                source_url=record["url"],
                text=normalize_minimal(text),
                image_paths=tuple(images),
                content_hash=chapter_content_hash(text),
            )
        )
    return tuple(chapters)


def _parse_title(markdown: str) -> str:
    for line in markdown.splitlines():
        if not line.startswith("# "):
            continue
        heading = line[2:].strip()
        matched = _TITLE_RE.search(heading)
        title = matched.group(1) if matched else heading
        for suffix in _TITLE_SUFFIXES:
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()
        if not title:
            break
        return title
    raise CorpusFormatError("说明.md 缺少可解析的书名标题行")


def _parse_author(markdown: str) -> str:
    matched = _AUTHOR_RE.search(markdown)
    if matched is None:
        raise CorpusFormatError("说明.md 缺少「作者：」字段")
    return matched.group(1)


def _decode(payload: bytes, name: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorpusFormatError(f"{name} 不是 UTF-8 编码") from exc


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
