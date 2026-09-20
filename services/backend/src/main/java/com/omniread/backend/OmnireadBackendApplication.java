package com.omniread.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

/**
 * Java 薄网关（M0-01 §7）。
 *
 * 职责：外部 API、前端静态资源托管、入参校验、request_id、超时/重试/熔断、错误映射。
 * 边界（M0-01 §1）：不直连 RAG 数据库；全部数据经 Python RAG 服务的内部契约取得。
 */
@SpringBootApplication
@ConfigurationPropertiesScan
public class OmnireadBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(OmnireadBackendApplication.class, args);
    }
}
