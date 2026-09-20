package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

/**
 * MDC 是线程绑定状态：放进去的 request_id 必须在请求结束（含异常路径）时清掉，
 * 否则线程复用时后一个请求会顶着前一个的 id，日志里就串号了。
 */
class RequestIdFilterTest {

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    @Test
    @DisplayName("请求内 MDC 有 request_id，与响应头一致，结束后清理")
    void putsAndClearsMdc() throws Exception {
        RequestIdFilter filter = new RequestIdFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        String[] seenInChain = new String[1];

        FilterChain chain = (req, res) -> seenInChain[0] = MDC.get(RequestIds.MDC_KEY);
        filter.doFilter(request, response, chain);

        assertThat(seenInChain[0]).matches("^req_[0-9a-f]{32}$");
        assertThat(response.getHeader(RequestIds.HEADER)).isEqualTo(seenInChain[0]);
        assertThat(MDC.get(RequestIds.MDC_KEY)).isNull();
    }

    @Test
    @DisplayName("链路抛异常也清理 MDC")
    void clearsMdcOnFailure() {
        RequestIdFilter filter = new RequestIdFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = (req, res) -> {
            throw new IllegalStateException("boom");
        };

        assertThatThrownBy(() -> filter.doFilter(request, response, chain))
                .isInstanceOf(IllegalStateException.class);
        assertThat(MDC.get(RequestIds.MDC_KEY)).isNull();
    }
}
