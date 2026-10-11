"""领域错误：错误码与 HTTP 状态码的唯一映射点。

错误码集合由 `contracts/openapi/rag-internal-v1.yaml` 的 `ErrorBody.code` 冻结——那份枚举是
**两侧的并集**，本服务只产生其中六个（网关那些登录 / 会话 / 配额的码不在这里，也不该在这里：
Python 不感知账户）。HTTP 状态码是权威判别位，响应体里不重复携带状态。
`message` 只放短句，不得含密钥、堆栈、文件路径、provider 原始响应体或章节正文。

两个 400 的分工与网关那一侧同一条口径：`RAG_INVALID_REALM` 是「问题超出你声明的进度」
（前端该提示用户改档位），`RAG_INVALID_REQUEST` 是「请求本身不合法」（前端该修自己）。
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    RAG_INVALID_REALM = "RAG_INVALID_REALM"
    RAG_INVALID_REQUEST = "RAG_INVALID_REQUEST"
    RAG_NOT_FOUND = "RAG_NOT_FOUND"
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
    """level / progress 越界：问题超出了调用者声明的进度。"""

    code = ErrorCode.RAG_INVALID_REALM
    http_status = 400


class RagInvalidRequest(RagError):
    """请求本身不合法：请求体校验失败、图片路径未通过防护、参数类型不对。

    与 `RagInvalidRealm` 同为 400 但是两件事：前者的处置是提示用户改档位或改进度，
    后者是前端改自己。前端按 code 分支，混在一起就分不出该提示谁。
    """

    code = ErrorCode.RAG_INVALID_REQUEST
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

    契约的 404 复用统一错误体，取 `RAG_NOT_FOUND`——它与网关那边的「会话不存在」是同一件事，
    没有理由因为实现方不同而分成两个码：前端按码分支，同一个处置两码就是两条分支，
    而两条分支迟早只改一条。
    """

    code = ErrorCode.RAG_NOT_FOUND
    http_status = 404


class UnsafeImagePath(RagError):
    """图片路径未通过目录穿越或扩展名白名单校验。

    这是「请求本身不合法」而不是「超出你声明的进度」：它跟用户读到第几章没有关系。
    """

    code = ErrorCode.RAG_INVALID_REQUEST
    http_status = 400


_BY_CODE: dict[ErrorCode, type[RagError]] = {
    ErrorCode.RAG_INVALID_REALM: RagInvalidRealm,
    ErrorCode.RAG_INVALID_REQUEST: RagInvalidRequest,
    ErrorCode.RAG_NOT_FOUND: ResourceNotFound,
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
