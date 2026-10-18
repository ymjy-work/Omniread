package com.omniread.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 一键下线开关。
 *
 * <p>`markerFile` 是给「不必重新部署」那半句话准备的：配置项改完要重启进程，
 * 而 `/opt/omniread` 下 `touch` 一个文件是一次 `stat` 就能查到的动作。
 * 两个开关是**或**的关系，取哪个都行。
 */
@ConfigurationProperties(prefix = "omniread.offline")
public record OfflineProperties(boolean enabled, String markerFile) {
}
