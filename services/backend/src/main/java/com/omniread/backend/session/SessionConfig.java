package com.omniread.backend.session;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * 会话 / 上下文的配置装配。
 *
 * <p>单独一个类而不是挂在 {@code StoreConfig} 上：那边管的是 SQLite 连接，
 * 这边管的是「一轮带多少历史」，两者没有任何关系，混在一起会让改一个的人看见另一个。
 */
@Configuration
@EnableConfigurationProperties(ContextBudget.class)
public class SessionConfig {
}
