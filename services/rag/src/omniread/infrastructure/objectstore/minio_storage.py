"""MinIO 实现的插图存储（运行时用）。

key 由 `paths.resolve_image_key` 产出，本类不再接受客户端传入的原始路径。
凭据只从环境变量进 Settings，读的时候才取值，不落任何文件。
"""

from __future__ import annotations

from minio import Minio
from minio.error import S3Error

from omniread.application.ports import StoredObject
from omniread.config import Settings
from omniread.infrastructure.objectstore.paths import image_media_type

_MISSING_KEY_CODES = frozenset({"NoSuchKey", "NoSuchBucket"})


class MinioImageStorage:
    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def get(self, key: str) -> StoredObject | None:
        try:
            response = self._client.get_object(self._bucket, key)
        except S3Error as exc:
            if exc.code in _MISSING_KEY_CODES:
                return None
            raise
        try:
            data = response.read()
            content_type = response.headers.get("Content-Type") or image_media_type(key)
        finally:
            response.close()
            response.release_conn()
        return StoredObject(data=data, content_type=content_type)


def build_minio_client(settings: Settings) -> Minio:
    """按 Settings 构造 MinIO 客户端；缺凭据时直接失败，不做静默降级。"""
    if settings.minio_access_key is None or settings.minio_secret_key is None:
        raise RuntimeError(
            "缺少 MinIO 凭据：请经 keymgr 注入 OMNIREAD_MINIO_ACCESS_KEY 与 "
            "OMNIREAD_MINIO_SECRET_KEY"
        )
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key.get_secret_value(),
        secure=settings.minio_secure,
    )


def build_minio_storage(settings: Settings) -> MinioImageStorage:
    """运行时插图存储。"""
    return MinioImageStorage(build_minio_client(settings), settings.minio_bucket)
