package com.omniread.backend.config;

import com.omniread.backend.quota.QuotaProperties;
import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 配额与限流的装配。 */
@Configuration
@EnableConfigurationProperties(QuotaProperties.class)
public class QuotaConfig {

    /**
     * 时间从容器取，不在各处直接 `LocalDate.now()`：验收里「次日自动恢复，无需人工解锁」
     * 只能用一个**固定时钟**来验，而生产与测试必须是同一个来源，否则测的是另一份逻辑。
     */
    @Bean
    public Clock clock() {
        return Clock.systemDefaultZone();
    }
}
