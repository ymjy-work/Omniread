"""插图 key 的解析与两道防护。

`path` 由客户端传来，不能信。防护见 M0-02 §8.8：
1. 目录穿越——归一化后判是否仍落在该书的 images 前缀内；
2. 扩展名白名单——只放行图片后缀。

key 形如 `books/{book_id}/images/{语料内相对路径}`。
"""

from __future__ import annotations

import posixpath
import re

from omniread.domain.errors import UnsafeImagePath

# 白名单只列 MinIO 里实际可能出现的图片格式，不认识的扩展名一律拒绝。
IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})

_MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")

# index.jsonl[].images 里的语料内相对路径都带这一层前缀；对象 key 与对外 url 都不重复它。
CORPUS_IMAGES_PREFIX = "images/"


def strip_corpus_images_prefix(corpus_relative: str) -> str:
    """去掉语料自带的 `images/` 前缀，得到不含第二层前缀的相对路径。"""
    return corpus_relative.removeprefix(CORPUS_IMAGES_PREFIX)


def image_key_prefix(book_id: int) -> str:
    return f"books/{book_id}/images/"


def resolve_image_key(book_id: int, raw_path: str) -> str:
    """把客户端传来的相对路径解析成对象存储 key，非法即抛 UnsafeImagePath。

    百分号转义在这里直接拒绝而不是解码：客户端框架可能已经解过一次码，
    残留的转义序列无法判断是哪一层解出来的，二次解码会把 `%2e%2e` 变成 `..`。
    """
    if not raw_path or "\x00" in raw_path:
        raise UnsafeImagePath("图片路径为空或含非法字符")
    if _PERCENT_ESCAPE.search(raw_path):
        raise UnsafeImagePath("图片路径含未解码的转义序列")
    if "\\" in raw_path or raw_path.startswith("/") or _WINDOWS_DRIVE.match(raw_path):
        raise UnsafeImagePath("图片路径必须是相对路径，且只用正斜杠")

    normalized = posixpath.normpath(raw_path)
    if normalized in (".", "..") or normalized.startswith("../"):
        raise UnsafeImagePath("图片路径越出该书目录")

    prefix = image_key_prefix(book_id)
    key = prefix + normalized
    # 归一化后仍以前缀开头才算落在该书内；这一步是目录穿越的判定点。
    if not key.startswith(prefix):
        raise UnsafeImagePath("图片路径越出该书目录")

    extension = posixpath.splitext(key)[1].lower()
    if extension not in IMAGE_EXTENSIONS:
        raise UnsafeImagePath("图片扩展名不在白名单内")
    return key


def image_media_type(key: str) -> str:
    return _MEDIA_TYPES.get(posixpath.splitext(key)[1].lower(), "application/octet-stream")
