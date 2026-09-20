"""语料归档：对象布局、清单 / 校验和、路径防护与失败即报。

MinIO 用内存实现替身，验证 key 与字节；真起 MinIO 的端到端另由 CLI 跑（见 notes）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from omniread.config import Settings
from omniread.domain.text import chapter_content_hash
from omniread.infrastructure.objectstore.corpus import (
    CorpusFormatError,
    build_checksums,
    corpus_manifest_hash,
    read_corpus,
)
from omniread.infrastructure.objectstore.corpus_archive import (
    ArchiveResult,
    CorpusArchiver,
    build_minio_writer,
    corpus_image_key,
)

_IMAGE_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


class InMemoryWriter:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.bucket_ready = False

    def ensure_bucket(self) -> None:
        self.bucket_ready = True

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)


def _write_corpus(root: Path, *, second_text: str = "正文[插图007]\n") -> Path:
    (root / "images" / "01_第1卷").mkdir(parents=True)
    (root / "images" / "01_第1卷" / "007.jpg").write_bytes(_IMAGE_BYTES)
    rows = [
        {
            "id": "1",
            "vol": "第一卷",
            "title": "序章",
            "url": "https://example.test/1.htm",
            "images": [],
            "text": "第一段  \r\n\r\n第二段\r\n",
        },
        {
            "id": "2",
            "vol": "第一卷",
            "title": "第一话",
            "url": "https://example.test/2.htm",
            "images": ["images/01_第1卷/007.jpg"],
            "text": second_text,
        },
        {
            "id": "3",
            "vol": "第二卷",
            "title": "第二话",
            "url": "https://example.test/3.htm",
            "images": [],
            "text": "另一段\n",
        },
    ]
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    (root / "index.jsonl").write_bytes(payload.encode("utf-8"))
    (root / "说明.md").write_text(
        "# 《测试书名》文库精校版\n\n> 作者：测试作者　插画：某人\n> 来源：某站\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def corpus_root(tmp_path: Path) -> Path:
    return _write_corpus(tmp_path / "corpus")


def _archive(corpus_root: Path) -> tuple[InMemoryWriter, ArchiveResult]:
    writer = InMemoryWriter()
    result = CorpusArchiver(writer, book_id=1).archive(
        corpus_root,
        imported_at=datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC),
    )
    return writer, result


def test_archive_writes_expected_object_layout(corpus_root: Path) -> None:
    writer, result = _archive(corpus_root)

    assert writer.bucket_ready is True
    assert set(writer.objects) == {
        "books/1/source/index.jsonl",
        "books/1/source/说明.md",
        "books/1/images/01_第1卷/007.jpg",
        "books/1/manifest.json",
        "books/1/checksums.json",
    }
    assert result.keys == (
        "books/1/source/index.jsonl",
        "books/1/source/说明.md",
        "books/1/images/01_第1卷/007.jpg",
        "books/1/manifest.json",
        "books/1/checksums.json",
    )


def test_index_jsonl_is_archived_byte_for_byte(corpus_root: Path) -> None:
    writer, _ = _archive(corpus_root)

    stored, content_type = writer.objects["books/1/source/index.jsonl"]
    assert stored == (corpus_root / "index.jsonl").read_bytes()
    assert content_type == "application/x-ndjson"


def test_image_key_has_single_images_prefix(corpus_root: Path) -> None:
    writer, _ = _archive(corpus_root)

    stored, content_type = writer.objects["books/1/images/01_第1卷/007.jpg"]
    assert stored == _IMAGE_BYTES
    assert content_type == "image/jpeg"


def test_manifest_carries_book_identity_and_counts(corpus_root: Path) -> None:
    writer, _ = _archive(corpus_root)

    manifest = json.loads(writer.objects["books/1/manifest.json"][0])
    assert manifest["title"] == "测试书名"
    assert manifest["author"] == "测试作者"
    assert manifest["chapter_count"] == 3
    assert manifest["volume_count"] == 2
    assert manifest["imported_at"] == "2026-09-19T12:00:00Z"
    assert manifest["corpus_version"].startswith("corpus-")


def test_checksums_match_shared_normalization_contract(corpus_root: Path) -> None:
    writer, _ = _archive(corpus_root)

    checksums = json.loads(writer.objects["books/1/checksums.json"][0])
    assert checksums["normalization"] == "m0-minimal-v1"
    assert checksums["algorithm"] == "sha256"
    assert checksums["chapters"][0]["chapter_id"] == "book:1:chapter:1"
    # CRLF 与行尾空白被规范化掉，两个写法必须同 hash。
    first_hash = checksums["chapters"][0]["content_hash"]
    assert first_hash == chapter_content_hash("第一段  \r\n\r\n第二段\r\n")
    assert first_hash == chapter_content_hash("第一段\n\n第二段\n")
    assert checksums["corpus_manifest_hash"] == corpus_manifest_hash(checksums["chapters"])


def test_corpus_manifest_hash_changes_with_content(tmp_path: Path) -> None:
    first = _write_corpus(tmp_path / "a")
    second = _write_corpus(tmp_path / "b", second_text="不同的正文\n")

    assert (
        build_checksums(read_corpus(first))["corpus_manifest_hash"]
        != build_checksums(read_corpus(second))["corpus_manifest_hash"]
    )


@pytest.mark.parametrize(
    "relative",
    ["../secret.jpg", "01_第1卷/../../secret.jpg", "images/01_第1卷/007.txt"],
)
def test_image_key_rejects_traversal_and_non_whitelisted(relative: str) -> None:
    with pytest.raises(CorpusFormatError):
        corpus_image_key(1, relative)


def test_image_key_rejects_missing_corpus_prefix() -> None:
    with pytest.raises(CorpusFormatError):
        corpus_image_key(1, "01_第1卷/007.jpg")


def test_referenced_image_missing_on_disk_raises(tmp_path: Path) -> None:
    root = _write_corpus(tmp_path / "corpus")
    (root / "images" / "01_第1卷" / "007.jpg").unlink()

    with pytest.raises(CorpusFormatError, match="引用的文件不存在"):
        _archive(root)


def test_missing_text_field_is_rejected(tmp_path: Path) -> None:
    root = _write_corpus(tmp_path / "corpus")
    rows = [json.loads(line) for line in (root / "index.jsonl").read_text("utf-8").splitlines()]
    del rows[1]["text"]
    (root / "index.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), "utf-8"
    )

    with pytest.raises(CorpusFormatError, match="缺少字段：text"):
        read_corpus(root)


def test_blank_line_breaks_one_to_one_index(tmp_path: Path) -> None:
    root = _write_corpus(tmp_path / "corpus")
    # 末尾多一个换行 = 多一个空行；行号与 chapter_index 不再一一对应。
    (root / "index.jsonl").write_bytes((root / "index.jsonl").read_bytes() + b"\n")

    with pytest.raises(CorpusFormatError, match="空行"):
        read_corpus(root)


def test_missing_index_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CorpusFormatError, match="缺少语料索引"):
        read_corpus(tmp_path / "empty")


def test_missing_credentials_fail_closed() -> None:
    settings = Settings(minio_access_key=None, minio_secret_key=None)

    with pytest.raises(RuntimeError, match="缺少 MinIO 凭据"):
        build_minio_writer(settings)


_REAL_CORPUS = (
    Path(__file__).resolve().parents[3]
    / "asset"
    / "《不时轻声地以俄语遮羞的邻座艾莉同学》"
)


@pytest.mark.skipif(not (_REAL_CORPUS / "index.jsonl").is_file(), reason="本机无正式语料")
def test_real_corpus_parses_to_frozen_counts() -> None:
    corpus = read_corpus(_REAL_CORPUS)

    assert len(corpus.chapters) == 193
    assert len(corpus.volume_titles) == 15
    assert sum(len(chapter.image_paths) for chapter in corpus.chapters) == 134
    assert corpus.title == "不时轻声地以俄语遮羞的邻座艾莉同学"
    assert corpus.author == "灿灿SUN"
