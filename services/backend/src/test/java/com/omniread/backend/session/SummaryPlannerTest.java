package com.omniread.backend.session;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 摘要区间的划法（`docs/m1/多轮会话落地方案.md` §三）。
 *
 * <p>纯函数：给定一串消息、一个旧摘要覆盖点和一份预算，结果必须完全确定。划错区间的症状是
 * 「关键事实在某一轮之后悄悄没了」，而它不会让任何东西报错——所以边界要一条条钉住。
 *
 * <p>**id 与 seq 故意错开 100**：`summary_upto` 记的是消息 id（契约与 `ChatSession` 的注释
 * 都这么说），而「取哪一段」是按 id 过滤的。两个都用 seq 写的话，测试会一路绿，
 * 直到某天 id 与 seq 不再同步增长（分叉会重排 seq）才暴露。
 */
class SummaryPlannerTest {

    private static final String SESSION = "s-1";

    private static ChatMessage message(int seq, String role, int tokens) {
        ChatMessage message = new ChatMessage();
        message.setId((long) seq + 100);
        message.setSessionId(SESSION);
        message.setSeq(seq);
        message.setRole(role);
        message.setContent(role + "-" + seq);
        message.setTokenCount(tokens);
        return message;
    }

    private static ChatMessage user(int seq, int tokens) {
        return message(seq, ChatMessage.ROLE_USER, tokens);
    }

    private static ChatMessage assistant(int seq, int tokens) {
        return message(seq, ChatMessage.ROLE_ASSISTANT, tokens);
    }

    /** 每轮 10 token 的 n 轮对话：seq 从 1 开始一问一答。 */
    private static List<ChatMessage> conversation(int turns) {
        List<ChatMessage> messages = new ArrayList<>();
        for (int turn = 1; turn <= turns; turn++) {
            messages.add(user(turn * 2 - 1, 5));
            messages.add(assistant(turn * 2, 5));
        }
        return messages;
    }

    /** 第一个数是**近轮原文的预算**，也就是触发线（SummaryPlanner 与 HistoryAssembler 共用它）。 */
    private static ContextBudget budget(int window, int keepRecent) {
        return new ContextBudget(window, 1, keepRecent);
    }

    @Test
    @DisplayName("攒下的还没超过一个窗口就不压：窗口是下限，不是「压到小于它」")
    void belowTheWindowIsNotCompressed() {
        // 6 轮 × 10 = 60；保留最近 4 轮（40），待压 2 轮 = 20。
        Optional<SummaryPlanner.Plan> plan =
                SummaryPlanner.plan(conversation(6), null, budget(60, 4));

        assertThat(plan).as("60 不「超过」60").isEmpty();
        assertThat(SummaryPlanner.plan(conversation(6), null, budget(59, 4))).isPresent();
    }

    @Test
    @DisplayName("最近 keepRecent 轮留在原文里，不进取摘要的那一段")
    void keepsTheMostRecentTurnsOut() {
        Optional<SummaryPlanner.Plan> plan =
                SummaryPlanner.plan(conversation(6), null, budget(30, 4));

        assertThat(plan).isPresent();
        assertThat(plan.get().messages()).extracting(ChatMessage::getSeq).containsExactly(1, 2, 3, 4);
        assertThat(plan.get().tokens()).isEqualTo(20);
    }

    @Test
    @DisplayName("覆盖点记的是消息 id，不是 seq")
    void uptoIsTheMessageId() {
        Optional<SummaryPlanner.Plan> plan =
                SummaryPlanner.plan(conversation(6), null, budget(10, 4));

        // seq 4 的那条消息 id 是 104（夹具里故意错开 100）。
        assertThat(plan.get().upto()).isEqualTo(104L);
    }

    @Test
    @DisplayName("已经进过摘要的那一段不再压：从 summary_upto 之后开始取")
    void alreadySummarizedPartIsSkipped() {
        // 压到 seq 4（id 104）之后又长了 4 轮：待压的 6 轮里，最近的 4 轮留在原文，
        // 于是取 seq 5..8。
        List<ChatMessage> messages = conversation(8);

        Optional<SummaryPlanner.Plan> plan = SummaryPlanner.plan(messages, 104L, budget(10, 4));

        assertThat(plan).isPresent();
        assertThat(plan.get().messages()).extracting(ChatMessage::getSeq).containsExactly(5, 6, 7, 8);
        assertThat(plan.get().upto()).isEqualTo(108L);
    }

    @Test
    @DisplayName("最近几轮之外没有内容时什么都不发——契约的 messages 有 minItems: 1")
    void nothingOutsideTheRecentWindowMeansNothingToSend() {
        // 4 轮，keep-recent 也是 4：待压区间为空。
        assertThat(SummaryPlanner.plan(conversation(4), null, budget(1, 4))).isEmpty();
        assertThat(SummaryPlanner.plan(conversation(9), 110L, budget(1, 4)))
                .as("summary_upto 已经追到只剩最近 4 轮")
                .isEmpty();
    }

    @Test
    @DisplayName("轮次比窗口还大时：每来一轮就压一轮——保留窗口自己就超过了窗口")
    void firesOnEveryTurnWhenTurnsAreLargerThanTheWindow() {
        // 每轮 100 token（一问一答各 50），窗口 100、保留最近 4 轮 = 400。
        List<ChatMessage> messages = new ArrayList<>();
        for (int seq = 1; seq <= 12; seq++) {
            messages.add(message(seq, seq % 2 == 1 ? ChatMessage.ROLE_USER : ChatMessage.ROLE_ASSISTANT, 50));
        }

        // 压到 seq 2 之后：未摘要 5 轮 = 500 > 100 → 触发；保留最近 4 轮，压的是刚掉出去的那一轮。
        Optional<SummaryPlanner.Plan> plan = SummaryPlanner.plan(messages, 102L, budget(100, 4));

        assertThat(plan).isPresent();
        assertThat(plan.get().messages()).extracting(ChatMessage::getSeq).containsExactly(3, 4);
        assertThat(plan.get().upto()).isEqualTo(104L);
    }

    @Test
    @DisplayName("残缺的轮次单独计一轮：把「有问没答」和后面那句并成一问一答会挪动边界")
    void incompleteTurnsStillCountAsTurns() {
        // seq 3 是上一轮失败留下的孤儿用户消息，紧接着 seq 4 又是一问。
        List<ChatMessage> messages = List.of(
                user(1, 5), assistant(2, 5), user(3, 5), user(4, 5), assistant(5, 5),
                user(6, 5), assistant(7, 5));

        Optional<SummaryPlanner.Plan> plan = SummaryPlanner.plan(messages, null, budget(1, 2));

        // 配成 4 轮：(1,2) / (3) / (4,5) / (6,7)；保留最近 2 轮，待压的是前两轮 = seq 1..3。
        // 按「下标两两配对」会得到 (3,4)，边界落在 seq 4——差一条消息，而两边都不报错。
        assertThat(plan).isPresent();
        assertThat(plan.get().messages()).extracting(ChatMessage::getSeq).containsExactly(1, 2, 3);
        assertThat(plan.get().upto()).isEqualTo(103L);
    }

    @Test
    @DisplayName("空会话没有可压的")
    void emptySessionHasNothingToCompress() {
        assertThat(SummaryPlanner.plan(List.of(), null, ContextBudget.DEFAULT)).isEmpty();
        assertThat(SummaryPlanner.plan(null, null, ContextBudget.DEFAULT)).isEmpty();
    }

    @Test
    @DisplayName("没记 token 数的消息按内容现算，不当成免费")
    void messagesWithoutTokenCountAreEstimated() {
        ChatMessage withoutCount = user(1, 0);
        withoutCount.setTokenCount(null);
        withoutCount.setContent("这是一句没有任何 token 计数的话");
        List<ChatMessage> messages = List.of(withoutCount, assistant(2, 0), user(3, 5), assistant(4, 5));

        Optional<SummaryPlanner.Plan> plan = SummaryPlanner.plan(messages, null, budget(1, 1));

        // 现算出来的是 13 × 0.81 ≈ 11，加上 0；当成 0 的话这里会是 0，永远触发不了摘要。
        assertThat(plan).isPresent();
        assertThat(plan.get().tokens()).isEqualTo(TokenEstimator.estimate(withoutCount.getContent()));
    }
}
