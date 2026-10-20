package com.omniread.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 回答模型的展示参数。
 *
 * @param contextWindow 模型上下文窗口（token）。只用于前端算「会话内容 / 模型窗口」的占比；
 *                      换回答模型必须同步改它，否则分母是错的。它不是历史预算
 *                      （`omniread.context.history-budget-tokens`）——那两个数说的是两件事。
 */
@ConfigurationProperties(prefix = "omniread.answer")
public record AnswerProperties(int contextWindow) {

    public AnswerProperties {
        if (contextWindow <= 0) {
            throw new IllegalArgumentException("contextWindow 必须为正数，收到 " + contextWindow);
        }
    }
}
