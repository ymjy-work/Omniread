"""运行配置。

只从环境变量读，不读 `.env`：密钥经 keymgr 注入环境变量，写进任何文件都算泄漏
（M0-00 §6）。凭据字段默认缺省，缺省即「未配置」，由使用方显式失败，不做静默降级。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMNIREAD_", extra="ignore")

    service_name: Literal["omniread-rag"] = "omniread-rag"
    log_level: str = "INFO"

    # 联调/测试专用的 provider 开关，默认走真实适配器。
    # 取值 fake 时装配确定性假 provider，服务启动会把这件事打进日志；它不是降级路径——
    # 真 provider 缺凭据时构造即失败，端点以 503 暴露未接线，绝不因为缺 key 静默换成 fake。
    answer_provider: Literal["glm", "fake"] = "glm"
    retrieval_provider: Literal["ali", "fake"] = "ali"
    # 只在 answer_provider=fake 时生效的故障注入：让真实 Python 服务返回 502 / 504，
    # 用于验证 Java 网关的上游错误映射，不必依赖付费 provider。
    fake_answer_fault: Literal["none", "provider_error", "timeout"] = "none"
    # 只在 answer_provider=fake 时生效的逐块延迟（毫秒）：把 SSE 帧在时间上拉开，
    # 才能验证「逐帧到达、不等整条流跑完」。
    fake_answer_delay_ms: int = 0

    image_storage_backend: Literal["minio", "local"] = "minio"
    image_local_root: Path = Path("var/images")

    minio_endpoint: str = "127.0.0.1:9100"
    minio_bucket: str = "omniread-sources"
    minio_secure: bool = False
    minio_access_key: str | None = None
    minio_secret_key: SecretStr | None = None
