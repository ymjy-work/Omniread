package com.omniread.backend.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 给所有响应加 {@code X-Robots-Tag: noindex, nofollow}。
 *
 * <p>为什么 robots.txt 之外还要这一层：robots.txt 只约束**守规矩**的爬虫，而且它要求
 * 抓取方先去取那个文件；响应头对不取 robots.txt 的抓取方同样生效。部署验收要求两样都有。
 *
 * <p>挂在全局（含静态资源与 API）：站点里没有一处该被收录，逐个路径挑反而会漏。
 */
@Component
public class NoIndexHeaderFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Robots-Tag";

    private static final String VALUE = "noindex, nofollow";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        response.setHeader(HEADER, VALUE);
        chain.doFilter(request, response);
    }
}
