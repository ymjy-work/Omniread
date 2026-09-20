"""领域错误：错误码与 HTTP 状态码的唯一映射点。

错误码集合由 `contracts/openapi/rag-internal-v1.yaml` 的 `ErrorBody.code` 冻结，
四种取值之外不新增；HTTP 状态码是权威判别位，响应体里不重复携带状态。
`message` 只放短句，不得含密钥、堆栈、文件路径、provider 原始响应体或章节正文。
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    RAG_INVALID_REALM = "RAG_INVALID_REALM"
    RAG_PROVIDER_ERROR = "RAG_PROVIDER_ERROR"
    RAG_UNAVAILABLE = "RAG_UNAVAILABLE"
    RAG_TIMEOUT = "RAG_TIMEOUT"


class RagError(Exception):
    """对外暴露的所有错误都是本类型的子类。"""

    code: ErrorCode
    http_status: int

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RagInvalidRealm(RagError):
    """入参非法：level / progress 越界，或请求体校验失败。"""

    code = ErrorCode.RAG_INVALID_REALM
    http_status = 400


class RagProviderError(RagError):
    """provider 返回错误。provider 故障不降级为拒答。"""

    code = ErrorCode.RAG_PROVIDER_ERROR
    http_status = 502


class RagUnavailable(RagError):
    """RAG 服务不可用。"""

    code = ErrorCode.RAG_UNAVAILABLE
    http_status = 503


class RagTimeout(RagError):
    """provider 超时。"""

    code = ErrorCode.RAG_TIMEOUT
    http_status = 504


class ResourceNotFound(RagError):
    """目标资源不存在（章节、图片）。

    契约的 404 复用统一错误体，而 `code` 只有四个取值，取 `RAG_INVALID_REALM`：
    请求指向的章节 / 图片不在合法范围内。
    """

    code = ErrorCode.RAG_INVALID_REALM
    http_status = 404


class UnsafeImagePath(RagError):
    """图片路径未通过目录穿越或扩展名白名单校验。"""

    code = ErrorCode.RAG_INVALID_REALM
    http_status = 400


_BY_CODE: dict[ErrorCode, type[RagError]] = {
    ErrorCode.RAG_INVALID_REALM: RagInvalidRealm,
    ErrorCode.RAG_PROVIDER_ERROR: RagProviderError,
    ErrorCode.RAG_UNAVAILABLE: RagUnavailable,
    ErrorCode.RAG_TIMEOUT: RagTimeout,
}


def error_from_wire(code: str, message: str) -> RagError:
    """把事件流里的 `code` / `message` 还原成带 HTTP 状态码的异常。

    未知 code 一律按不可用处理：契约的取值集合是封闭的，出现未知值说明对端越界，
    不能把它当成某类已知错误。
    """
    try:
        known = ErrorCode(code)
    except ValueError:
        return RagUnavailable(message)
    return _BY_CODE[known](message)
