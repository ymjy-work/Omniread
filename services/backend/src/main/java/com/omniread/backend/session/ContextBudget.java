package com.omniread.backend.session;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 多轮上下文的三个预算参数（`docs/m1/多轮会话落地方案.md` §三）。
 *
 * <p>它们不是三件独立的事：{@code historyBudgetTokens} **同时**是「分给近轮原文的预算」
 * 与「摘要的触发线」（{@link SummaryPlanner}），因为这两句话说的是同一件事——
 * 攒下的对话超过了拼装能给模型看的量，就有一段谁也看不见。{@code keepRecentOnSummarize}
 * 再决定那一段从哪里切开。
 *
 * <p>**{@code keepRecentOnSummarize} 要明显小于窗口装得下的轮数。** 取大了（保留的几轮
 * 本身就填满窗口）会出现「既不在摘要里、也不在窗口里」的一段——那一轮的话模型完全看不到；
 * 取小了只是把还看得见的原文也压一遍，多花一次模型调用，不丢东西。所以取值上**宁可小**。
 * 每轮多少 token 是运行时才知道的量，这条只能靠保守取值：默认窗口 12000（≈ 十来轮）、
 * {@code keep = 8}，即便每轮 1500 token，8 轮也只占满窗口、不留缺口。
 *
 * @param historyBudgetTokens 分给「近轮原文」的预算；同时是摘要的触发线
 * @param minRecentTurns 至少保留最近几轮完整对话，即使超预算
 * @param keepRecentOnSummarize 触发摘要时最近几轮不进摘要、留原文
 */
@ConfigurationProperties(prefix = "omniread.context")
public record ContextBudget(
        int historyBudgetTokens, int minRecentTurns, int keepRecentOnSummarize) {

    /** 与方案 §三 的默认值一致；测试与纯函数用这个，不必起 Spring 上下文。 */
    public static final ContextBudget DEFAULT = new ContextBudget(12000, 2, 8);

    public ContextBudget {
        // 都必须在构造时挡住：0 或负数不会报错，只会让拼装静默产出空历史或无限循环。
        requirePositive(historyBudgetTokens, "historyBudgetTokens");
        requirePositive(minRecentTurns, "minRecentTurns");
        requirePositive(keepRecentOnSummarize, "keepRecentOnSummarize");
    }

    private static void requirePositive(int value, String name) {
        if (value <= 0) {
            throw new IllegalArgumentException(name + " 必须为正数，收到 " + value);
        }
    }
}
