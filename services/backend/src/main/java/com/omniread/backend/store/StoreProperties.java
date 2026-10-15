package com.omniread.backend.store;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 本机 SQLite 的位置。
 *
 * <p>账户、会话、进度、配额都落这一个文件（`docs/方案.md（多轮会话一节）` §一：用户数据只在
 * Java 侧）。默认落在 `var/` 下，该目录已被 gitignore。
 *
 * @param file SQLite 文件路径；相对路径按进程工作目录解析
 */
@ConfigurationProperties(prefix = "omniread.store")
public record StoreProperties(String file) {
}
