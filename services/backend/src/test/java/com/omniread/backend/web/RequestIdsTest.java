package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * request_id 的格式是契约的一部分（pattern ^req_[0-9a-f]{32}$），
 * 它同时出现在请求头、错误体与 Python 的日志里，格式错了三边都对不上。
 */
class RequestIdsTest {

    @Test
    @DisplayName("生成的 id 是 req_ + 32 位小写十六进制，共 36 字符")
    void format() {
        String requestId = RequestIds.next();

        assertThat(requestId).hasSize(36).matches("^req_[0-9a-f]{32}$");
        assertThat(RequestIds.isValid(requestId)).isTrue();
    }

    @Test
    @DisplayName("反复生成不重复：随机源是 SecureRandom，16 字节空间足够")
    void unique() {
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < 10_000; i++) {
            assertThat(seen.add(RequestIds.next())).isTrue();
        }
    }

    @Test
    @DisplayName("拒收大小写/长度/前缀不符的值")
    void rejectsMalformed() {
        assertThat(RequestIds.isValid(null)).isFalse();
        assertThat(RequestIds.isValid("")).isFalse();
        assertThat(RequestIds.isValid("req_0123456789abcdef0123456789ABCDEF")).isFalse();
        assertThat(RequestIds.isValid("req_0123456789abcdef0123456789abcdef0")).isFalse();
        assertThat(RequestIds.isValid("0123456789abcdef0123456789abcdef")).isFalse();
    }
}
