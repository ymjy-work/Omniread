package com.omniread.backend.error;

import org.springframework.http.HttpStatusCode;

/**
 * 网关对外暴露的唯一异常类型：携带契约里的 code，**HTTP 状态由 code 派生**。
 *
 * <p>没有「另传一个状态」的构造器，是刻意的：一个事实一个来源。允许覆盖时能产出契约
 * 那张表里不存在的组合（例如 HTTP 404 配一个表里记 400 的码），而**前端按 code 分支**
 * ——表说这个码是 400，它就不会去处理 404 的语义。
 *
 * <p>上游带了契约形状的错误体时以它的 code 为准（那才是机器可判定的字段），
 * 状态仍然由那个码派生。
 */
public class RagException extends RuntimeException {

    private final ErrorCode code;

    public RagException(ErrorCode code, String message) {
        super(message);
        this.code = code;
    }

    public RagException(ErrorCode code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public ErrorCode code() {
        return code;
    }

    /** 由 {@link #code()} 派生，不另存一份。 */
    public HttpStatusCode httpStatus() {
        return code.httpStatus();
    }
}
