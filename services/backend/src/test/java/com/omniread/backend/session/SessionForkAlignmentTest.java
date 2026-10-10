package com.omniread.backend.session;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 分叉点的规整规则（`SessionService.alignToCompleteTurn`）。
 *
 * <p>纯函数测试：这几条规则全都**不会报错**，只会安静地少复制一段或多复制半轮——
 * 而「分叉少带一段上下文」和「分叉多带半轮」在界面上看起来都完全正常。
 */
class SessionForkAlignmentTest {

    @Test
    @DisplayName("空会话：分叉点是 0，复制 0 条")
    void emptySessionForksToNothing() {
        assertThat(SessionService.alignToCompleteTurn(List.of(), null)).isZero();
        assertThat(SessionService.alignToCompleteTurn(List.of(), 5)).isZero();
    }

    @Test
    @DisplayName("缺省取最后一条：完整的两轮取到第 4 条")
    void defaultsToTheLastMessage() {
        List<ChatMessage> history = twoTurns();

        assertThat(SessionService.alignToCompleteTurn(history, null)).isEqualTo(4);
    }

    @Test
    @DisplayName("落在 assistant 上就用它")
    void landsOnAnAssistant() {
        assertThat(SessionService.alignToCompleteTurn(twoTurns(), 2)).isEqualTo(2);
    }

    @Test
    @DisplayName("落在 user 上退到前一条 assistant——半轮会让 prompt 里出现连续两条 user")
    void landsOnAUserAndStepsBack() {
        assertThat(SessionService.alignToCompleteTurn(twoTurns(), 3)).isEqualTo(2);
    }

    @Test
    @DisplayName("落在只有 user 的开头上：前面没有 assistant，退到 0")
    void singleUserMessageForksToNothing() {
        List<ChatMessage> history = List.of(message(1, ChatMessage.ROLE_USER));

        assertThat(SessionService.alignToCompleteTurn(history, 1)).isZero();
        assertThat(SessionService.alignToCompleteTurn(history, null)).isZero();
    }

    @Test
    @DisplayName("越上界夹到最大值——前端一边拉消息一边点分叉时必然算大")
    void clampsBeyondTheEnd() {
        assertThat(SessionService.alignToCompleteTurn(twoTurns(), 999)).isEqualTo(4);
    }

    @Test
    @DisplayName("开头是 assistant（残缺形状）时，落在它上面仍然取它")
    void toleratesAMissingUserPrefix() {
        List<ChatMessage> history = new ArrayList<>();
        history.add(message(1, ChatMessage.ROLE_ASSISTANT));
        history.add(message(2, ChatMessage.ROLE_USER));
        history.add(message(3, ChatMessage.ROLE_ASSISTANT));

        assertThat(SessionService.alignToCompleteTurn(history, 1)).isEqualTo(1);
        assertThat(SessionService.alignToCompleteTurn(history, 2)).isEqualTo(1);
    }

    /** 一问一答两轮：seq 1..4。 */
    private static List<ChatMessage> twoTurns() {
        List<ChatMessage> history = new ArrayList<>();
        history.add(message(1, ChatMessage.ROLE_USER));
        history.add(message(2, ChatMessage.ROLE_ASSISTANT));
        history.add(message(3, ChatMessage.ROLE_USER));
        history.add(message(4, ChatMessage.ROLE_ASSISTANT));
        return history;
    }

    private static ChatMessage message(int seq, String role) {
        ChatMessage message = new ChatMessage();
        message.setSeq(seq);
        message.setRole(role);
        message.setContent(role + "-" + seq);
        return message;
    }
}
