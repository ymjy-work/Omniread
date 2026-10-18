package com.omniread.backend;

import com.omniread.backend.config.RagProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

/**
 * Java 薄网关。
 *
 * 职责：外部 API、前端静态资源托管、入参校验、request_id、超时/重试/熔断、错误映射。
 * 边界：不直连 RAG 数据库；全部数据经 Python RAG 服务的内部契约取得。
 *
 * <p>**属性类一律显式 `@EnableConfigurationProperties` 注册，不用 `@ConfigurationPropertiesScan`**：
 * 两者做同一件事，同时开着就是两套机制。显式那条更好读——每个属性类由谁启用写在它自己的
 * 装配点旁边（`GuardrailConfig` / `QuotaConfig` / `SessionConfig` / `StoreConfig` / `UserConfig`），
 * 只有 {@code RagProperties} 没有对应的装配类，挂在这里。
 */
@SpringBootApplication
@EnableConfigurationProperties(RagProperties.class)
public class OmnireadBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(OmnireadBackendApplication.class, args);
    }
}
