package com.omniread.backend.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * E 阶段那几件护栏的装配点（`docs/方案.md（部署一节）` §三-4）：阅读范围、一键下线。
 * 配额与限流的配置在 {@link QuotaConfig}——它还要出一个 `Clock`，所以单独一个类。
 */
@Configuration
@EnableConfigurationProperties({ReadingProperties.class, OfflineProperties.class})
public class GuardrailConfig {
}
