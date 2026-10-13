package com.omniread.backend.web;

import com.omniread.backend.config.OfflineProperties;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * 一键下线：**整个 API 停在第一道**（健康检查除外，否则运维会以为进程死了）。
 *
 * <p>两种开关：配置项 `omniread.offline.enabled`，或者**标记文件存在**。
 * 标记文件那一条是「一键」的关键——配置项要重启才读得到，而这是应急预案里
 * 最不该多一步的动作：`touch var/OFFLINE` 之后，下一个请求就 503。
 *
 * <p>返回 503 + `RAG_UNAVAILABLE`：契约里它本来就是「服务暂不可用」，
 * 前端已经有一条现成的处置（显示一行错误），不必为下线另造一个码。
 */
@Component
public class OfflineInterceptor implements HandlerInterceptor {

    private static final Logger log = LoggerFactory.getLogger(OfflineInterceptor.class);

    private final OfflineProperties properties;

    public OfflineInterceptor(OfflineProperties properties) {
        this.properties = properties;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        if (isOffline()) {
            throw new RagException(ErrorCode.RAG_UNAVAILABLE, "站点已下线维护，暂停提供内容");
        }
        return true;
    }

    /**
     * 每次请求查一次文件（一次 `stat`，可忽略）。**不缓存**：缓存就把「改配置即生效」
     * 变成了「改配置，等下一次刷新缓存」——而这是应急开关。
     */
    private boolean isOffline() {
        if (properties.enabled()) {
            return true;
        }
        String marker = properties.markerFile();
        if (marker == null || marker.isBlank()) {
            return false;
        }
        return Files.exists(Paths.get(marker));
    }

    /** 启动时把状态打出来：运维要能一眼看出「现在是下线的」，而不是去猜。 */
    @EventListener(ApplicationReadyEvent.class)
    public void reportState() {
        Path marker = properties.markerFile() == null ? null : Paths.get(properties.markerFile());
        if (isOffline()) {
            log.warn("**站点处于下线状态**（配置={}、标记文件 {}={}）：除健康检查外一律 503",
                    properties.enabled(),
                    marker == null ? "(未配置)" : marker.toAbsolutePath(),
                    marker != null && Files.exists(marker));
        } else {
            log.info("站点在线；下线开关：配置 omniread.offline.enabled=true，或 touch {}",
                    marker == null ? "(未配置标记文件)" : marker.toAbsolutePath());
        }
    }
}
