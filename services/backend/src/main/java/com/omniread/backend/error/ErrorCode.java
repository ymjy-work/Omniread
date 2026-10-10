package com.omniread.backend.error;

import java.net.SocketTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.concurrent.TimeoutException;
import org.springframework.http.HttpStatus;

/**
 * 契约 `ErrorBody.code` 的 Java 侧全集（`contracts/openapi/rag-internal-v1.yaml`）。
 *
 * HTTP 状态由 code 派生，不另存一份：客户端只按 code 分支，状态码是同一个判断的传输层表达。
 * 材料不足（insufficient_evidence）不在其中 —— 它是 200 的正常业务结果。
 *
 * 本枚举与契约里的那份**逐项一致**（`ErrorCodeContractTest` 读契约比对）；契约那张
 * 「谁产生 / HTTP」表说的是每个码归谁发 —— 两侧列同一套，但不是每一侧都会产生全部。
 * 少一个的后果不是编译错，而是 `ErrorBody.CodeEnum.valueOf` 在运行时抛异常。
 *
 * 四个 429 分开而不是合成一个，是因为**处置不同**：分钟限流等一下重试、日额度要等明天、
 * 并发要等上一个回答结束、登录锁要换来源 IP。合成一个，前端就只能显示一句笼统的「太频繁」。
 */
public enum ErrorCode {
    /** 问题超出调用者声明的进度：前端该提示用户改档位或改进度。 */
    RAG_INVALID_REALM(HttpStatus.BAD_REQUEST),
    /** 请求本身不合法（缺字段 / 类型错 / 缺 CSRF 头 / book_id 不存在 / 分叉到同档位）：前端该修自己。 */
    RAG_INVALID_REQUEST(HttpStatus.BAD_REQUEST),
    RAG_UNAUTHENTICATED(HttpStatus.UNAUTHORIZED),
    RAG_FORBIDDEN(HttpStatus.FORBIDDEN),
    RAG_NOT_FOUND(HttpStatus.NOT_FOUND),
    RAG_SESSION_MISMATCH(HttpStatus.CONFLICT),
    RAG_RATE_LIMITED(HttpStatus.TOO_MANY_REQUESTS),
    RAG_DAILY_QUOTA_EXCEEDED(HttpStatus.TOO_MANY_REQUESTS),
    RAG_CONCURRENT_QUERY(HttpStatus.TOO_MANY_REQUESTS),
    RAG_LOGIN_LOCKED(HttpStatus.TOO_MANY_REQUESTS),
    RAG_PROVIDER_ERROR(HttpStatus.BAD_GATEWAY),
    RAG_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE),
    RAG_TIMEOUT(HttpStatus.GATEWAY_TIMEOUT);

    private final HttpStatus httpStatus;

    ErrorCode(HttpStatus httpStatus) {
        this.httpStatus = httpStatus;
    }

    public HttpStatus httpStatus() {
        return httpStatus;
    }

    /**
     * 上游（Python）响应 → 本网关错误码。
     *
     * body 里的 code 优先：它是契约中机器可判定的唯一字段，且能区分同为 5xx 的
     * provider 故障与超时。code 缺失或不可识别时按 HTTP 状态兜底。
     */
    public static ErrorCode fromUpstream(int upstreamStatus, String upstreamCode) {
        for (ErrorCode candidate : values()) {
            if (candidate.name().equals(upstreamCode)) {
                return candidate;
            }
        }
        return switch (upstreamStatus) {
            // 404 也归到这里：Python 对「章节 / 图片不在合法范围内」用的就是 RAG_INVALID_REALM
            // （它没有 RAG_NOT_FOUND 这条分支），所以按状态兜底时要还原成同一个码，
            // 否则同一件事会随「上游有没有带 body」而变成两种 code。
            case 400, 404 -> RAG_INVALID_REALM;
            case 502 -> RAG_PROVIDER_ERROR;
            case 504 -> RAG_TIMEOUT;
            default -> RAG_UNAVAILABLE;
        };
    }

    /**
     * 传输层失败 → 错误码：超时类单独归类，其余（连不上 Python、熔断打开）都是不可用。
     */
    public static ErrorCode fromTransportFailure(Throwable failure) {
        for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
            if (cause instanceof SocketTimeoutException
                    || cause instanceof HttpTimeoutException
                    || cause instanceof TimeoutException) {
                return RAG_TIMEOUT;
            }
        }
        return RAG_UNAVAILABLE;
    }
}
