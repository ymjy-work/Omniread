package com.omniread.backend.error;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.ConnectException;
import java.net.SocketTimeoutException;
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
    @DisplayName("四个 code 各自的 HTTP 状态：400 / 502 / 503 / 504")
    void httpStatusMapping() {
        assertThat(ErrorCode.RAG_INVALID_REALM.httpStatus()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(ErrorCode.RAG_PROVIDER_ERROR.httpStatus()).isEqualTo(HttpStatus.BAD_GATEWAY);
        assertThat(ErrorCode.RAG_UNAVAILABLE.httpStatus()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(ErrorCode.RAG_TIMEOUT.httpStatus()).isEqualTo(HttpStatus.GATEWAY_TIMEOUT);
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
    @DisplayName("上游没有可识别 code 时按状态码兜底，未知状态归不可用")
    void upstreamStatusFallback() {
        assertThat(ErrorCode.fromUpstream(400, null)).isEqualTo(ErrorCode.RAG_INVALID_REALM);
        assertThat(ErrorCode.fromUpstream(404, null)).isEqualTo(ErrorCode.RAG_INVALID_REALM);
        assertThat(ErrorCode.fromUpstream(502, null)).isEqualTo(ErrorCode.RAG_PROVIDER_ERROR);
        assertThat(ErrorCode.fromUpstream(504, null)).isEqualTo(ErrorCode.RAG_TIMEOUT);
        assertThat(ErrorCode.fromUpstream(500, null)).isEqualTo(ErrorCode.RAG_UNAVAILABLE);
        assertThat(ErrorCode.fromUpstream(500, "NOT_A_CODE")).isEqualTo(ErrorCode.RAG_UNAVAILABLE);
    }

    @Test
    @DisplayName("上游明确给出的状态原样带出：目录端点的 404 不被压成 code 的默认状态")
    void upstreamStatusIsPreserved() {
        RagException notFound = new RagException(ErrorCode.RAG_INVALID_REALM, "章节不存在", HttpStatus.NOT_FOUND);

        assertThat(notFound.code()).isEqualTo(ErrorCode.RAG_INVALID_REALM);
        assertThat(notFound.httpStatus()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(new RagException(ErrorCode.RAG_TIMEOUT, "超时").httpStatus()).isEqualTo(HttpStatus.GATEWAY_TIMEOUT);
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
