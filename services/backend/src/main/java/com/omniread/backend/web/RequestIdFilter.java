package com.omniread.backend.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 每个入站请求生成一个 request_id，放进请求属性（供 Controller/错误体使用）、响应头与 MDC。
 *
 * 客户端带来的 X-Request-Id 一律忽略：request_id 必须由本进程生成，
 * 才能保证「响应里的 id」与「下游 Python 收到的 id」是同一个，而不是客户端编造的值。
 * MDC 是线程绑定状态，请求结束必须清掉，否则线程复用时后一个请求会顶着前一个的 id。
 */
@Component
public class RequestIdFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RequestIdFilter.class);

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String requestId = RequestIds.next();
        request.setAttribute(RequestIds.ATTRIBUTE, requestId);
        response.setHeader(RequestIds.HEADER, requestId);
        MDC.put(RequestIds.MDC_KEY, requestId);
        long startNanos = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            // 在 MDC.remove 之前记，否则这条访问日志自己就丢了 request_id
            long elapsedMs = (System.nanoTime() - startNanos) / 1_000_000;
            log.info("{} {} -> {} ({} ms)", request.getMethod(), request.getRequestURI(),
                    response.getStatus(), elapsedMs);
            MDC.remove(RequestIds.MDC_KEY);
        }
    }
}
