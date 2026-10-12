package com.omniread.backend.session;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 上下文拼装的五条规则（`docs/m1/多轮会话落地方案.md` §三）。
 *
 * <p>纯函数，所以这里不需要 Spring、不需要库：给定一串消息与一份预算，结果必须完全确定。
 * 多轮出问题时最常见的就是「这一轮带了哪些历史」，能拿同一份输入重放才查得动。
 */
class HistoryAssemblerTest {

    private static final String SESSION = "s-1";

    private static ChatMessage message(int seq, String role, int tokens) {
        ChatMessage message = new ChatMessage();
        message.setSessionId(SESSION);
        message.setSeq(seq);
        message.setRole(role);
        message.setContent(role + "-" + seq);
        message.setTokenCount(tokens);
        message.setCreatedAt(Instant.now().toString());
        return message;
    }

    private static ChatMessage user(int seq, int tokens) {
        return message(seq, ChatMessage.ROLE_USER, tokens);
    }

    private static ChatMessage assistant(int seq, int tokens) {
        return message(seq, ChatMessage.ROLE_ASSISTANT, tokens);
    }

    private static ContextBudget budget(int historyTokens, int minRecentTurns) {
        return new ContextBudget(historyTokens, minRecentTurns, 4);
    }

    @Test
    @DisplayName("没有历史时是空结果，不报错")
    void emptyHistory() {
        assertThat(HistoryAssembler.assemble(List.of(), ContextBudget.DEFAULT).isEmpty()).isTrue();
        assertThat(HistoryAssembler.assemble(null, ContextBudget.DEFAULT).isEmpty()).isTrue();
    }

    @Test
    @DisplayName("规则 1：装得下就整轮带上，按 seq 升序")
    void keepsWholeTurnsWhenTheyFit() {
        List<ChatMessage> messages = List.of(
                user(1, 10), assistant(2, 10), user(3, 10), assistant(4, 10));

        HistorySelection selection = HistoryAssembler.assemble(messages, budget(1000, 1));

        assertThat(selection.messages()).extracting(ChatMessage::getSeq).containsExactly(1, 2, 3, 4);
        assertThat(selection.turnsIncluded()).isEqualTo(2);
        assertThat(selection.turnsDropped()).isZero();
        assertThat(selection.estimatedTokens()).isEqualTo(40);
        assertThat(selection.anchorAdded()).isFalse();
    }

    @Test
    @DisplayName("规则 1：超预算时从最旧的开始整轮丢，不切半个轮次")
    void dropsOldestWholeTurnsFirst() {
        // 第一轮特别大（510），后两轮各 20；预算 100。
        List<ChatMessage> messages = List.of(
                user(1, 10), assistant(2, 500), user(3, 10), assistant(4, 10),
                user(5, 10), assistant(6, 10));

        HistorySelection selection = HistoryAssembler.assemble(messages, budget(100, 1));

        // 留下的是最近两轮，且每一轮都是完整的问 + 答。
        assertThat(selection.messages()).extracting(ChatMessage::getSeq).containsExactly(1, 3, 4, 5, 6);
        assertThat(selection.turnsIncluded()).isEqualTo(2);
        assertThat(selection.turnsDropped()).isEqualTo(1);
        assertThat(selection.estimatedTokens()).isEqualTo(40);
    }

    @Test
    @DisplayName("规则 2：首轮用户消息是锚点，被裁掉时单独补回来，且不计入预算")
    void anchorIsAlwaysKeptAndNotCounted() {
        List<ChatMessage> messages = List.of(
                user(1, 10), assistant(2, 500), user(3, 10), assistant(4, 10));

        HistorySelection selection = HistoryAssembler.assemble(messages, budget(100, 1));

        assertThat(selection.anchorAdded()).isTrue();
        assertThat(selection.messages().get(0).getSeq()).isEqualTo(1);
        assertThat(selection.messages().get(0).getRole()).isEqualTo(ChatMessage.ROLE_USER);
        // 预算里只有留下来的那一轮（20），锚点的 10 不算——算进去会随锚点大小挤掉真实历史。
        assertThat(selection.estimatedTokens()).isEqualTo(20);
    }

    @Test
    @DisplayName("规则 2：锚点在保留范围内时不重复添加")
    void anchorIsNotDuplicated() {
        List<ChatMessage> messages = List.of(user(1, 10), assistant(2, 10));

        HistorySelection selection = HistoryAssembler.assemble(messages, budget(1000, 1));

        assertThat(selection.anchorAdded()).isFalse();
        assertThat(selection.messages()).extracting(ChatMessage::getSeq).containsExactly(1, 2);
    }

    @Test
    @DisplayName("规则 3：至少留 minRecentTurns 轮，即使单轮就超预算")
    void keepsMinimumTurnsEvenOverBudget() {
        List<ChatMessage> messages = List.of(
                user(1, 20), assistant(2, 20), user(3, 20), assistant(4, 20),
                user(5, 20), assistant(6, 20));

        // 预算是 10，任何一轮都装不下；下限是 2 轮，所以最近两轮必须留下。
        HistorySelection selection = HistoryAssembler.assemble(messages, budget(10, 2));

        assertThat(selection.turnsIncluded()).isEqualTo(2);
        assertThat(selection.messages()).extracting(ChatMessage::getSeq)
                .contains(3, 4, 5, 6)
                .doesNotContain(2);
        assertThat(selection.estimatedTokens()).isEqualTo(80);
    }

    @Test
    @DisplayName("残缺形状不丢内容：没有回答的用户消息自成一轮")
    void unpairedUserMessageBecomesItsOwnTurn() {
        // 上一轮失败留下的：有问没答。
        List<ChatMessage> messages = List.of(user(1, 10), assistant(2, 10), user(3, 10));

        HistorySelection selection = HistoryAssembler.assemble(messages, budget(1000, 1));

        assertThat(selection.messages()).extracting(ChatMessage::getSeq).containsExactly(1, 2, 3);
        assertThat(selection.turnsIncluded()).isEqualTo(2);
    }

    @Test
    @DisplayName("残缺形状不丢内容：前面没有用户的助手消息也自成一轮")
    void orphanAssistantMessageBecomesItsOwnTurn() {
        List<ChatMessage> messages = List.of(assistant(1, 10), user(2, 10), assistant(3, 10));

        HistorySelection selection = HistoryAssembler.assemble(messages, budget(1000, 1));

        assertThat(selection.messages()).extracting(ChatMessage::getSeq).containsExactly(1, 2, 3);
        // 一条用户消息都没有，所以没有锚点可补。
        assertThat(selection.anchorAdded()).isFalse();
    }

    @Test
    @DisplayName("没记 token 数的消息按内容现算，不当成免费")
    void messagesWithoutTokenCountAreEstimated() {
        ChatMessage noCount = user(1, 0);
        noCount.setTokenCount(null);
        noCount.setContent("这是一句没有任何 token 计数的话"); // 13 个汉字
        ChatMessage answer = assistant(2, 5);

        HistorySelection selection =
                HistoryAssembler.assemble(List.of(noCount, answer), budget(1000, 1));

        // 13 × 0.81 ≈ 11，而不是 0。当成 0 会让这类消息变成「免费历史」，一路把预算撑爆。
        assertThat(selection.estimatedTokens()).isEqualTo(TokenEstimator.estimate(noCount.getContent()) + 5);
        assertThat(selection.estimatedTokens()).isGreaterThan(5);
    }

    @Test
    @DisplayName("结果不可变：拿到手之后改不动")
    void returnedListIsUnmodifiable() {
        List<ChatMessage> messages = new ArrayList<>(List.of(user(1, 10), assistant(2, 10)));

        HistorySelection selection = HistoryAssembler.assemble(messages, budget(1000, 1));

        assertThat(selection.messages()).isUnmodifiable();
    }
}
