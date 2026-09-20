package com.omniread.backend.error;

import java.net.SocketTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.concurrent.TimeoutException;
import org.springframework.http.HttpStatus;

/**
 * M0-01 §7 的四个错误码。
 *
 * HTTP 状态由 code 派生，不另存一份：客户端只按 code 分支，状态码是同一个判断的传输层表达。
 * 材料不足（insufficient_evidence）不在其中 —— 它是 200 的正常业务结果。
 */
public enum ErrorCode {
    RAG_INVALID_REALM(HttpStatus.BAD_REQUEST),
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
            // 404 也归到这里：它是「你要的东西不在这本书的有效范围内」，
            // 四个码里只有这一支属于客户端输入类，无非 2xx 的其它含义可选。
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
