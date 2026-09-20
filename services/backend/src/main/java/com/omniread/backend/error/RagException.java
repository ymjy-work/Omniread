package com.omniread.backend.error;

import org.springframework.http.HttpStatusCode;

/**
 * 网关对外暴露的唯一异常类型：携带契约里的 code，HTTP 状态默认由 code 派生。
 *
 * 上游带了明确状态时以它为准（构造器允许覆盖）：目录端点的 404 是外部契约里写明的
 * 响应，把它压成四个 code 对应的状态会让前端分不清「这一章不存在」和「服务坏了」。
 */
public class RagException extends RuntimeException {

    private final ErrorCode code;

    private final HttpStatusCode httpStatus;

    public RagException(ErrorCode code, String message) {
        this(code, message, code.httpStatus(), null);
    }

    public RagException(ErrorCode code, String message, Throwable cause) {
        this(code, message, code.httpStatus(), cause);
    }

    public RagException(ErrorCode code, String message, HttpStatusCode httpStatus) {
        this(code, message, httpStatus, null);
    }

    private RagException(ErrorCode code, String message, HttpStatusCode httpStatus, Throwable cause) {
        super(message, cause);
        this.code = code;
        this.httpStatus = httpStatus;
    }

    public ErrorCode code() {
        return code;
    }

    public HttpStatusCode httpStatus() {
        return httpStatus;
    }
}
