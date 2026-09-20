package com.omniread.backend.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Python RAG 服务的访问参数：地址、超时、重试、熔断。
 *
 * 集中在这里（application.yml 的 omniread.rag）而不是散在调用点，
 * 是为了让「多久算超时、失败几次算熔断」只有一个可读的地方。
 */
@ConfigurationProperties(prefix = "omniread.rag")
public record RagProperties(
        String baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        Retry retry,
        CircuitBreaker circuitBreaker) {

    /** 重试只针对传输失败，业务错误（RagException）不重试。 */
    public record Retry(int maxAttempts, Duration waitDuration) {
    }

    public record CircuitBreaker(
            float failureRateThreshold,
            int slidingWindowSize,
            int minimumNumberOfCalls,
            Duration waitDurationInOpenState) {
    }
}
