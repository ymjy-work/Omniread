"""S3 协议实现的对象存储：生产是 AWS S3，本地是 MinIO，走同一个客户端。

逻辑 key 以 `books/` 开头，项目根前缀只在 `S3ObjectStore` 这一层加一次——
调用方拿到的、日志里出现的、测试断言的都还是逻辑 key。
凭据只从环境变量进 Settings，读的时候才取值，不落任何文件。
"""

from __future__ import annotations

import io
from collections.abc import Iterator

import certifi
import urllib3
from minio import Minio
from minio.error import S3Error

from omniread.application.ports import StoredObject
from omniread.config import Settings
from omniread.infrastructure.objectstore.paths import image_media_type

_MISSING_KEY_CODES = frozenset({"NoSuchKey", "NoSuchBucket"})


def normalize_prefix(prefix: str | None) -> str:
    """项目根前缀：去掉首尾斜杠后补一个尾斜杠；空串表示不加前缀。"""
    value = (prefix or "").strip().strip("/")
    return f"{value}/" if value else ""


class S3ObjectStore:
    """按项目前缀读写的对象存储；桶由部署侧预先创建。"""

    def __init__(self, client: Minio, bucket: str, prefix: str = "") -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = normalize_prefix(prefix)

    @property
    def prefix(self) -> str:
        return self._prefix

    def key(self, logical_key: str) -> str:
        """逻辑 key → 物理 key。前缀只在这里加。"""
        return f"{self._prefix}{logical_key}"

    def get(self, logical_key: str) -> StoredObject | None:
        try:
            response = self._client.get_object(self._bucket, self.key(logical_key))
        except S3Error as exc:
            if exc.code in _MISSING_KEY_CODES:
                return None
            raise
        try:
            data = response.read()
            content_type = response.headers.get("Content-Type") or image_media_type(logical_key)
        finally:
            response.close()
            response.release_conn()
        return StoredObject(data=data, content_type=content_type)

    def put(self, logical_key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            self._bucket,
            self.key(logical_key),
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    def exists(self, logical_key: str) -> bool:
        try:
            self._client.stat_object(self._bucket, self.key(logical_key))
        except S3Error as exc:
            if exc.code in _MISSING_KEY_CODES:
                return False
            raise
        return True

    def remove(self, logical_key: str) -> None:
        self._client.remove_object(self._bucket, self.key(logical_key))

    def list_keys(self, logical_prefix: str = "", recursive: bool = True) -> Iterator[str]:
        """列出逻辑 key（前缀已剥掉），供验证脚本核对归档结果。"""
        physical_prefix = self.key(logical_prefix)
        for obj in self._client.list_objects(
            self._bucket, prefix=physical_prefix, recursive=recursive
        ):
            yield obj.object_name[len(self._prefix) :]


def build_s3_client(settings: Settings) -> Minio:
    """按 Settings 构造 S3 客户端；缺凭据时直接失败，不做静默降级。"""
    if settings.object_store_access_key is None or settings.object_store_secret_key is None:
        raise RuntimeError(
            "缺少对象存储凭据：请注入 OMNIREAD_OBJECT_STORE_ACCESS_KEY 与 "
            "OMNIREAD_OBJECT_STORE_SECRET_KEY"
        )
    http_client = None
    if settings.object_store_proxy:
        http_client = urllib3.ProxyManager(
            settings.object_store_proxy,
            timeout=urllib3.Timeout(connect=5.0, read=60.0),
            maxsize=10,
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where(),
            retries=urllib3.Retry(
                total=5, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504]
            ),
        )
    return Minio(
        settings.object_store_endpoint,
        access_key=settings.object_store_access_key,
        secret_key=settings.object_store_secret_key.get_secret_value(),
        secure=settings.object_store_secure,
        region=settings.object_store_region or None,
        http_client=http_client,
    )


def build_object_store(settings: Settings) -> S3ObjectStore:
    """运行时对象存储：插图读取与语料归档共用同一个。"""
    return S3ObjectStore(
        build_s3_client(settings),
        settings.object_store_bucket,
        settings.object_store_prefix,
    )
