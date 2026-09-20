"""本地文件系统实现的插图存储，供单测与无 MinIO 的本地调试使用。

key 已经过 `paths.resolve_image_key` 的两道防护；这里再按解析后的真实路径复核一次
是否落在 root 内，防止符号链接把读取引出根目录（纵深防御）。
"""

from __future__ import annotations

from pathlib import Path

from omniread.application.ports import StoredObject
from omniread.infrastructure.objectstore.paths import image_media_type


class LocalFileSystemImageStorage:
    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def get(self, key: str) -> StoredObject | None:
        target = (self._root / key).resolve()
        if not target.is_relative_to(self._root):
            return None
        if not target.is_file():
            return None
        return StoredObject(data=target.read_bytes(), content_type=image_media_type(key))
