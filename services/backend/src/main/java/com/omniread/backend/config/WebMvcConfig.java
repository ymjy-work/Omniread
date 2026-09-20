package com.omniread.backend.config;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.PathResourceResolver;

/**
 * 前端静态资源托管。
 *
 * 前端与后端同源，所以没有 CORS 配置：构建产物由本进程直接发。
 * 前端数据一律经 /api/v1，静态资源不参与任何转发。
 */
@Configuration
public class WebMvcConfig implements WebMvcConfigurer {

    private static final Logger log = LoggerFactory.getLogger(WebMvcConfig.class);

    /** 向上查找构建产物目录的最大层数：从仓库根跑与从 services/backend 跑都能命中。 */
    private static final int MAX_SEARCH_DEPTH = 4;

    private final String distDir;

    private final Path dist;

    public WebMvcConfig(@Value("${omniread.web.dist-dir}") String distDir) {
        this.distDir = distDir;
        this.dist = resolveDistDir(distDir);
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        if (dist == null) {
            // 前端尚未构建不应让网关起不来：只托管 API，静态资源缺省为空。
            log.info("前端构建产物目录 {} 不存在，本次仅托管 API", distDir);
            return;
        }
        log.info("托管前端静态资源：{}", dist);
        registry.addResourceHandler("/**")
                .addResourceLocations(dist.toUri().toString())
                .resourceChain(true)
                .addResolver(new PathResourceResolver() {
                    @Override
                    protected Resource getResource(String resourcePath, Resource location) throws IOException {
                        // 无扩展名且不在 /api 下的路径都是前端路由（history 模式）。
                        // 这一层只在默认解析器找不到文件后才轮到：/api/** 的未知路径必须 404，
                        // 不能返回首页 HTML，否则前端会把打错的接口当成页面加载。
                        if (resourcePath.startsWith("api/") || resourcePath.indexOf('.') >= 0) {
                            Resource requested = location.createRelative(resourcePath);
                            return requested.isReadable() ? requested : null;
                        }
                        return indexHtml(location);
                    }
                });
    }

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        // 根路径在资源处理器里是空路径，默认解析器会把它解析成可读的目录，最终 404。
        // 显式转发到 index.html，不经资源路径推断。
        if (dist != null) {
            registry.addViewController("/").setViewName("forward:/index.html");
        }
    }

    private static Resource indexHtml(Resource location) throws IOException {
        Resource index = location.createRelative("index.html");
        return index.isReadable() ? index : null;
    }

    private static Path resolveDistDir(String distDir) {
        Path configured = Paths.get(distDir);
        if (configured.isAbsolute()) {
            return Files.isDirectory(configured) ? configured : null;
        }
        Path dir = Paths.get("").toAbsolutePath();
        for (int depth = 0; depth < MAX_SEARCH_DEPTH && dir != null; depth++, dir = dir.getParent()) {
            Path candidate = dir.resolve(configured);
            if (Files.isDirectory(candidate)) {
                return candidate;
            }
        }
        return null;
    }
}
