package com.omniread.backend.session;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 多轮上下文的四个预算参数（`docs/m1/多轮会话落地方案.md` §三）。
 *
 * <p>前两个管**拼装**（{@link HistoryAssembler}），后两个管**摘要触发**（D3 阶段用）。
 * 放在一起是因为它们互相牵制：调大 {@code historyBudgetTokens} 就推迟了摘要触发，
 * 两个数分开看会以为是两件独立的事。
 *
 * @param historyBudgetTokens 分给「近轮原文」的预算
 * @param minRecentTurns 至少保留最近几轮完整对话，即使超预算
 * @param summarizeThresholdTokens 会话消息总量超过它就触发摘要
 * @param keepRecentOnSummarize 触发摘要时最近几轮不进摘要、留原文
 */
@ConfigurationProperties(prefix = "omniread.context")
public record ContextBudget(
        int historyBudgetTokens,
        int minRecentTurns,
        int summarizeThresholdTokens,
        int keepRecentOnSummarize) {

    /** 与方案 §三 的默认值一致；测试与纯函数用这个，不必起 Spring 上下文。 */
    public static final ContextBudget DEFAULT = new ContextBudget(1500, 1, 4000, 4);

    public ContextBudget {
        // 都必须在构造时挡住：0 或负数不会报错，只会让拼装静默产出空历史或无限循环。
        requirePositive(historyBudgetTokens, "historyBudgetTokens");
        requirePositive(minRecentTurns, "minRecentTurns");
        requirePositive(summarizeThresholdTokens, "summarizeThresholdTokens");
        requirePositive(keepRecentOnSummarize, "keepRecentOnSummarize");
    }

    private static void requirePositive(int value, String name) {
        if (value <= 0) {
            throw new IllegalArgumentException(name + " 必须为正数，收到 " + value);
        }
    }
}
