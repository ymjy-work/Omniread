"""Provider 错误：适配器内部异常与其到领域错误码的映射点。

适配器只抛 `ProviderError` 子类，核心业务不识别 `httpx` 异常；`to_rag_error()` 是唯一
映射到领域错误码（`RAG_PROVIDER_ERROR` / `RAG_TIMEOUT`）的入口，HTTP 状态码由领域异常
给出。`message` 只放短句，不带密钥、请求 URL 查询串或 provider 原始响应体。
"""

from __future__ import annotations

from omniread.domain.errors import RagError, RagProviderError, RagTimeout


class ProviderError(Exception):
    """provider 调用失败。所有适配器错误都是本类型的子类。"""

    def __init__(self, message: str, *, provider: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        # provider 侧的 HTTP 状态码；无响应（超时 / 连接失败）时为 None。
        self.status_code = status_code


class ProviderConfigError(ProviderError):
    """配置缺失（如凭据未注入）。构造适配器时即失败，不静默降级。"""


class ProviderTimeoutError(ProviderError):
    """请求超时。与其它失败分开，映射到 `RAG_TIMEOUT`。"""


class ProviderResponseError(ProviderError):
    """响应结构与端点约定不符（字段缺失、维度不符、条数不符）。"""


def to_rag_error(exc: ProviderError) -> RagError:
    """把适配器异常还原成带 HTTP 状态码的领域异常。

    非超时的 provider 故障一律 `RAG_PROVIDER_ERROR`（502）：provider 故障不降级为拒答。
    """
    if isinstance(exc, ProviderTimeoutError):
        return RagTimeout(exc.message)
    return RagProviderError(exc.message)
