package com.omniread.backend.config;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

/**
 * 调用 Python 的 HTTP 客户端与容错策略。
 *
 * 用 RestClient 而不是 WebClient：本网关全是同步转发，没有一条链需要响应式调度；
 * 引入 WebClient 只会多一套线程模型。
 */
@Configuration
public class RagClientConfig {

    /**
     * 只配请求工厂，不配 baseUrl：图片端点的下游路径必须由我们自己拼（见 RagGatewayClient），
     * 那里需要绝对 URI，baseUrl 若同时存在就有两个真相源。
     *
     * 用 SimpleClientHttpRequestFactory 而不是 JDK HttpClient 工厂：后者的读超时落在
     * HttpRequest.timeout 上，那是**整次请求**的总预算，SSE 会被它按总时长掐断；
     * 前者是 socket 级空闲超时（两次读之间多久算超时），才符合「流式透传」要的语义。
     */
    @Bean
    public RestClient ragRestClient(RagProperties properties) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(properties.connectTimeout());
        requestFactory.setReadTimeout(properties.readTimeout());
        return RestClient.builder().requestFactory(requestFactory).build();
    }

    /**
     * 重试的边界是「传输没成功」：连不上、读超时。
     * 业务错误（RagException，含输入非法与 provider 报错）重试没有意义，明确忽略。
     */
    @Bean
    public Retry ragRetry(RagProperties properties) {
        RagProperties.Retry retry = properties.retry();
        RetryConfig config = RetryConfig.custom()
                .maxAttempts(retry.maxAttempts())
                .waitDuration(retry.waitDuration())
                .retryExceptions(ResourceAccessException.class, IOException.class)
                .ignoreExceptions(com.omniread.backend.error.RagException.class)
                .build();
        return Retry.of("rag", config);
    }

    /**
     * 熔断只统计传输失败：Python 挂掉时快速失败，不再堆请求。
     * 输入非法（400）不算 Python 的故障，不能让它把断路器打开。
     */
    @Bean
    public CircuitBreaker ragCircuitBreaker(RagProperties properties) {
        RagProperties.CircuitBreaker breaker = properties.circuitBreaker();
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .failureRateThreshold(breaker.failureRateThreshold())
                .slidingWindowSize(breaker.slidingWindowSize())
                .minimumNumberOfCalls(breaker.minimumNumberOfCalls())
                .waitDurationInOpenState(breaker.waitDurationInOpenState())
                .recordExceptions(ResourceAccessException.class, IOException.class)
                .ignoreExceptions(com.omniread.backend.error.RagException.class)
                .build();
        return CircuitBreaker.of("rag", config);
    }
}
