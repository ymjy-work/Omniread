package com.omniread.backend.session;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * 决定「现在要不要摘要、该压哪一段」（纯函数，`docs/m1/多轮会话落地方案.md` §三）。
 *
 * <p>**触发线挂在「近轮原文的预算」上：`summary_upto` 之后攒下的量超过它，就压。** 那句话
 * 说的是「已经有一段内容谁也看不见了」——{@link HistoryAssembler} 只把最新
 * {@code historyBudgetTokens} 的完整轮次发给模型，而摘要只覆盖到 `summary_upto`，中间那段
 * 两边都不在。于是**看不见的那一段最多就是一个窗口的量**（前一触发点到现在多出来的那点），
 * 这是可陈述的不变量。
 *
 * <p>区间：`summary_upto` 之后、**倒数第 {@code keepRecentOnSummarize} 轮之前**的消息。
 * 最近那几轮留在原文里不进摘要——它们是「这一轮正在说什么」的上下文，摘要会把细节磨平，
 * 而接下来几轮最需要的正是细节。
 *
 * <p>那条触发线**不是**阈值：越过之后每轮都还越着，所以只要有一轮老得掉出保留窗口，摘要就会
 * 再跑一次。这正是要的——晚一轮压，就多一轮文字在模型的上下文里缺席；而它压的只是掉出窗口的
 * 那一两轮，不是从头再来一遍（`summary_upto` 挡住了重复）。
 *
 * <p>纯函数：不查库、不看时间。摘要的边界算错时症状是「关键事实悄悄没了」，
 * 那是事后最难查的一类问题，所以这里必须能拿着同一份输入重放。
 */
public final class SummaryPlanner {

    private SummaryPlanner() {
    }

    /** 这一次要压的东西：哪几条、压到哪条为止、多少 token。 */
    public record Plan(List<ChatMessage> messages, long upto, int tokens) {
    }

    /**
     * 该压就给出这一段，否则 `empty`（攒下的还没超过一个窗口、或保留窗口之外没有内容）。
     *
     * @param messages    该会话的全部消息，按 `seq` 升序
     * @param summaryUpto 已有摘要覆盖到哪条消息 **id**；首次摘要时为 null
     */
    public static Optional<Plan> plan(List<ChatMessage> messages, Long summaryUpto, ContextBudget budget) {
        if (messages == null || messages.isEmpty()) {
            return Optional.empty();
        }

        List<ChatMessage> unsummarized = after(messages, summaryUpto);
        if (Turns.tokens(unsummarized) <= budget.historyBudgetTokens()) {
            return Optional.empty();
        }

        List<Turns.Turn> turns = Turns.of(unsummarized);
        int keep = Math.min(budget.keepRecentOnSummarize(), turns.size());
        List<ChatMessage> compressible = new ArrayList<>();
        for (Turns.Turn turn : turns.subList(0, turns.size() - keep)) {
            compressible.addAll(turn.messages());
        }
        if (compressible.isEmpty()) {
            return Optional.empty();
        }

        // 覆盖到本段最后一条为止；「覆盖到哪」记的是消息 id，不是 seq。
        long upto = compressible.get(compressible.size() - 1).getId();
        return Optional.of(new Plan(List.copyOf(compressible), upto, Turns.tokens(compressible)));
    }

    /** `summary_upto` 之后的消息。id 单调递增（自增主键），所以按 id 比就够了。 */
    private static List<ChatMessage> after(List<ChatMessage> messages, Long summaryUpto) {
        if (summaryUpto == null) {
            return messages;
        }
        return messages.stream().filter(message -> message.getId() > summaryUpto).toList();
    }
}
