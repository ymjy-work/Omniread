package com.omniread.backend;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * 上下文能起来本身就是一条验收：超时/重试/熔断配置、生成的 DTO、
 * web/dist 不存在时不崩，这些都在装配阶段暴露问题。
 */
@SpringBootTest
class OmnireadBackendApplicationTests {

    @Test
    @DisplayName("应用上下文可加载")
    void contextLoads() {
    }
}
