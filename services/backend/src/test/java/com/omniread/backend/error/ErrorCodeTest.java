package com.omniread.backend.error;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.List;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

/**
 * 错误映射表（M0-01 §7）是网关对外承诺的一部分：
 * code 决定 HTTP 状态，判错了前端就分不清「材料不足」与「服务坏了」。
 */
class ErrorCodeTest {

    @Test
    @DisplayName("每个 code 的 HTTP 状态：同码同状态，四个 429 不合成一个")
    void httpStatusMapping() {
        assertThat(ErrorCode.RAG_INVALID_REALM.httpStatus()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(ErrorCode.RAG_INVALID_REQUEST.httpStatus()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(ErrorCode.RAG_UNAUTHENTICATED.httpStatus()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(ErrorCode.RAG_FORBIDDEN.httpStatus()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(ErrorCode.RAG_NOT_FOUND.httpStatus()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(ErrorCode.RAG_SESSION_MISMATCH.httpStatus()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(ErrorCode.RAG_PROVIDER_ERROR.httpStatus()).isEqualTo(HttpStatus.BAD_GATEWAY);
        assertThat(ErrorCode.RAG_UNAVAILABLE.httpStatus()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(ErrorCode.RAG_TIMEOUT.httpStatus()).isEqualTo(HttpStatus.GATEWAY_TIMEOUT);

        // 四个 429 是同一状态、不同处置：分钟限流等一下、日额度等明天、并发等上一个回答结束、
        // 登录锁换 IP。前端按 code 分支，所以它们必须是四个不同的码。
        assertThat(List.of(
                        ErrorCode.RAG_RATE_LIMITED,
                        ErrorCode.RAG_DAILY_QUOTA_EXCEEDED,
                        ErrorCode.RAG_CONCURRENT_QUERY,
                        ErrorCode.RAG_LOGIN_LOCKED))
                .allSatisfy(code -> assertThat(code.httpStatus()).isEqualTo(HttpStatus.TOO_MANY_REQUESTS))
                .doesNotHaveDuplicates();
    }

    @Test
    @DisplayName("上游错误体带 code 时以 code 为准")
    void upstreamCodeWins() {
        assertThat(ErrorCode.fromUpstream(400, "RAG_INVALID_REALM")).isEqualTo(ErrorCode.RAG_INVALID_REALM);
        assertThat(ErrorCode.fromUpstream(502, "RAG_PROVIDER_ERROR")).isEqualTo(ErrorCode.RAG_PROVIDER_ERROR);
        assertThat(ErrorCode.fromUpstream(503, "RAG_UNAVAILABLE")).isEqualTo(ErrorCode.RAG_UNAVAILABLE);
        assertThat(ErrorCode.fromUpstream(504, "RAG_TIMEOUT")).isEqualTo(ErrorCode.RAG_TIMEOUT);
        // 状态与 code 不一致时仍信 code：它是契约里机器可判定的唯一字段。
        assertThat(ErrorCode.fromUpstream(500, "RAG_TIMEOUT")).isEqualTo(ErrorCode.RAG_TIMEOUT);
    }

    @Test
    @DisplayName("上游没有可识别 code 时按状态码兜底，且兜底码的默认状态就是那个状态")
    void upstreamStatusFallback() {
        // 兜底挑的就是那一行：状态与码对得上，契约那张表（REALM↦400、NOT_FOUND↦404）
        // 因此不会出现表外的组合。400 归 REQUEST 而不是 REALM——兜底拿不到 message，
        // 判不出是不是「超出你声明的进度」，而契约对「其余情形」的规定就是 REQUEST。
        assertThat(ErrorCode.fromUpstream(400, null)).isEqualTo(ErrorCode.RAG_INVALID_REQUEST);
        assertThat(ErrorCode.fromUpstream(404, null)).isEqualTo(ErrorCode.RAG_NOT_FOUND);
        assertThat(ErrorCode.fromUpstream(502, null)).isEqualTo(ErrorCode.RAG_PROVIDER_ERROR);
        assertThat(ErrorCode.fromUpstream(504, null)).isEqualTo(ErrorCode.RAG_TIMEOUT);
        assertThat(ErrorCode.fromUpstream(500, null)).isEqualTo(ErrorCode.RAG_UNAVAILABLE);
        assertThat(ErrorCode.fromUpstream(500, "NOT_A_CODE")).isEqualTo(ErrorCode.RAG_UNAVAILABLE);

        assertThat(ErrorCode.RAG_INVALID_REQUEST.httpStatus()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(ErrorCode.RAG_NOT_FOUND.httpStatus()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    @DisplayName("状态由 code 派生，不另存一份——上游多说一个状态也改不了它")
    void statusFollowsTheCode() {
        // 这条钉的是「一个事实一个来源」。原先允许把上游状态原样带出，于是能产出
        // 契约表里不存在的组合（HTTP 404 配一个表里记 400 的码），而前端按 code 分支
        // ——表说这个码是 400，它就不会去处理 404 的语义。
        assertThat(new RagException(ErrorCode.RAG_NOT_FOUND, "章节不存在").httpStatus())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(new RagException(ErrorCode.RAG_INVALID_REALM, "越界").httpStatus())
                .isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(new RagException(ErrorCode.RAG_TIMEOUT, "超时").httpStatus())
                .isEqualTo(HttpStatus.GATEWAY_TIMEOUT);
    }

    @Test
    @DisplayName("传输失败：超时类归 RAG_TIMEOUT，其余（连不上、熔断打开）归 RAG_UNAVAILABLE")
    void transportFailure() {
        assertThat(ErrorCode.fromTransportFailure(new SocketTimeoutException("read timed out")))
                .isEqualTo(ErrorCode.RAG_TIMEOUT);
        assertThat(ErrorCode.fromTransportFailure(new TimeoutException("response timeout")))
                .isEqualTo(ErrorCode.RAG_TIMEOUT);
        // Spring 把连接失败与读超时都包在 ResourceAccessException 里，原因在 cause 链上。
        assertThat(ErrorCode.fromTransportFailure(new RuntimeException("wrapped", new SocketTimeoutException())))
                .isEqualTo(ErrorCode.RAG_TIMEOUT);
        assertThat(ErrorCode.fromTransportFailure(new RuntimeException("connect refused", new ConnectException())))
                .isEqualTo(ErrorCode.RAG_UNAVAILABLE);
        assertThat(ErrorCode.fromTransportFailure(new IllegalStateException("circuit open")))
                .isEqualTo(ErrorCode.RAG_UNAVAILABLE);
    }
}
