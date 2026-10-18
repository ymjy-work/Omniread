package com.omniread.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 阅读范围：**阅读页只开放这一卷**，问答不受限。
 *
 * <p>只配卷号、不配章号区间：区间由 `ReadingRange` 从章节表推导——
 * 章号会随语料重导入变，卷号是人对这本书的说法。
 */
@ConfigurationProperties(prefix = "omniread.reading")
public record ReadingProperties(int volumeIndex) {
}
