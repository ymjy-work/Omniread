package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

/** `X-Robots-Tag` 是部署验收项：所有响应（含静态资源与 API）都要带上。 */
class NoIndexHeaderFilterTest {

    @Test
    @DisplayName("任何响应都带 X-Robots-Tag: noindex, nofollow")
    void everyResponseCarriesTheHeader() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/health");
        MockHttpServletResponse response = new MockHttpServletResponse();

        new NoIndexHeaderFilter().doFilter(request, response, (req, res) -> {
            // 下游不写这个头，验证的是过滤器自己加的
        });

        assertThat(response.getHeader("X-Robots-Tag")).isEqualTo("noindex, nofollow");
    }
}
