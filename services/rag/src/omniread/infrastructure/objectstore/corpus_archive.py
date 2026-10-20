"""把语料原始件归档到 S3。

对象布局与 key 构造在本文件（`book_prefix` / `source_key` / `manifest_key` / `checksums_key`）
与 `paths.py`（图片 key）里，这里只负责读语料、算清单 / 校验和并上传：

```text
books/{book_id}/source/index.jsonl          # 原始语料，原样归档
books/{book_id}/source/说明.md              # 来源与版权说明
books/{book_id}/images/{语料内相对路径}      # 插图
books/{book_id}/manifest.json               # 导入清单（程序生成）
books/{book_id}/checksums.json              # 每章 hash（程序生成）
```

`index.jsonl[].images` 形如 `images/01_第1卷/007.jpg`，去掉语料自带的 `images/` 前缀后
交给 `paths.resolve_image_key`，落成 `books/{book_id}/images/01_第1卷/007.jpg`（不加第二层前缀）。
图片路径来自语料、同样不可信，进 key 前复用 `paths.resolve_image_key` 的目录穿越与扩展名防护。

凭据只从环境变量进 Settings；缺凭据时构造写入端即失败，不静默降级。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol

from omniread.config import Settings
from omniread.domain.errors import UnsafeImagePath
from omniread.infrastructure.objectstore.corpus import (
    DESCRIPTION_NAME,
    INDEX_NAME,
    Corpus,
    CorpusFormatError,
    build_checksums,
    build_manifest,
    dumps_canonical,
    read_corpus,
)
from omniread.infrastructure.objectstore.paths import (
    CORPUS_IMAGES_PREFIX,
    image_media_type,
    resolve_image_key,
    strip_corpus_images_prefix,
)
from omniread.infrastructure.objectstore.s3 import build_object_store

INDEX_CONTENT_TYPE = "application/x-ndjson"
MARKDOWN_CONTENT_TYPE = "text/markdown; charset=utf-8"
JSON_CONTENT_TYPE = "application/json"


def book_prefix(book_id: int) -> str:
    return f"books/{book_id}/"


def source_key(book_id: int, filename: str) -> str:
    """原始语料 key，`books/{book_id}/source/{filename}`。"""
    return f"{book_prefix(book_id)}source/{filename}"


def manifest_key(book_id: int) -> str:
    return f"{book_prefix(book_id)}manifest.json"


def checksums_key(book_id: int) -> str:
    return f"{book_prefix(book_id)}checksums.json"


class ObjectWriter(Protocol):
    """归档写入端：S3 供真跑，内存实现供单测。"""

    def put(self, key: str, data: bytes, content_type: str) -> None: ...


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    book_id: int
    keys: tuple[str, ...]
    manifest: dict[str, object]
    checksums: dict[str, object]


class CorpusArchiver:
    def __init__(self, writer: ObjectWriter, book_id: int = 1) -> None:
        self._writer = writer
        self._book_id = book_id

    def archive(
        self,
        corpus_root: Path,
        corpus_version: str | None = None,
        imported_at: datetime | None = None,
    ) -> ArchiveResult:
        corpus = read_corpus(corpus_root, self._book_id, corpus_version)
        manifest = build_manifest(corpus, imported_at or datetime.now(UTC))
        checksums = build_checksums(corpus)

        uploaded: list[str] = []

        def upload(key: str, data: bytes, content_type: str) -> None:
            self._writer.put(key, data, content_type)
            uploaded.append(key)

        upload(
            source_key(self._book_id, INDEX_NAME),
            corpus.index_bytes,
            INDEX_CONTENT_TYPE,
        )
        upload(
            source_key(self._book_id, DESCRIPTION_NAME),
            corpus.description_bytes,
            MARKDOWN_CONTENT_TYPE,
        )
        for key, data in self._image_objects(corpus_root, corpus):
            upload(key, data, image_media_type(key))
        # checksums 先写、manifest 最后写：manifest 是整批的提交标记。
        upload(checksums_key(self._book_id), dumps_canonical(checksums), JSON_CONTENT_TYPE)
        upload(manifest_key(self._book_id), dumps_canonical(manifest), JSON_CONTENT_TYPE)

        return ArchiveResult(
            book_id=self._book_id,
            keys=tuple(uploaded),
            manifest=manifest,
            checksums=checksums,
        )

    def _image_objects(self, corpus_root: Path, corpus: Corpus) -> Iterator[tuple[str, bytes]]:
        base = Path(corpus_root).resolve()
        seen: set[str] = set()
        for chapter in corpus.chapters:
            for corpus_relative in chapter.image_paths:
                key = corpus_image_key(self._book_id, corpus_relative)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    yield key, read_corpus_file(base, corpus_relative)
                except CorpusFormatError as exc:
                    raise CorpusFormatError(f"{chapter.chapter_id}：{exc}") from exc


def corpus_image_key(book_id: int, corpus_relative: str) -> str:
    """语料内图片路径 → 对象 key，并施加目录穿越与扩展名两道防护。

    `images/01_第1卷/007.jpg` → `books/1/images/01_第1卷/007.jpg`。
    """
    if not corpus_relative.startswith(CORPUS_IMAGES_PREFIX):
        raise CorpusFormatError(f"图片路径不在 images/ 下：{corpus_relative}")
    relative = strip_corpus_images_prefix(corpus_relative)
    try:
        return resolve_image_key(book_id, relative)
    except UnsafeImagePath as exc:
        raise CorpusFormatError(f"图片路径未通过校验：{corpus_relative}（{exc.message}）") from exc


def read_corpus_file(base: Path, corpus_relative: str) -> bytes:
    """读取语料内文件；解析后的真实路径必须仍落在语料根内（纵深防御）。"""
    target = (base / PurePosixPath(corpus_relative)).resolve()
    if not target.is_relative_to(base):
        raise CorpusFormatError(f"文件路径越出语料根目录：{corpus_relative}")
    if not target.is_file():
        raise CorpusFormatError(f"index.jsonl 引用的文件不存在：{corpus_relative}")
    return target.read_bytes()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把语料原始件归档到 S3")
    parser.add_argument("--corpus-root", required=True, type=Path, help="语料根目录")
    parser.add_argument("--book-id", type=int, default=1, help="书籍 ID，M0 恒为 1")
    parser.add_argument(
        "--corpus-version",
        default=None,
        help="语料版本；缺省时取 index.jsonl 字节 sha256 前 12 位",
    )
    args = parser.parse_args(argv)

    writer = build_object_store(Settings())
    result = CorpusArchiver(writer, args.book_id).archive(args.corpus_root, args.corpus_version)
    summary = {
        "book_id": result.book_id,
        "object_count": len(result.keys),
        "corpus_manifest_hash": result.checksums["corpus_manifest_hash"],
        "keys": list(result.keys),
    }
    # 直接写 UTF-8 字节：Windows 控制台默认 GBK，json.dump 到 stdout 会把中文 key 转乱码。
    sys.stdout.buffer.write((json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
