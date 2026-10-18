package com.omniread.backend.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * 护栏的装配点：阅读范围、一键下线。
 * 配额与限流的配置在 {@link QuotaConfig}——它还要出一个 `Clock`，所以单独一个类。
 */
@Configuration
@EnableConfigurationProperties({ReadingProperties.class, OfflineProperties.class})
public class GuardrailConfig {
}
