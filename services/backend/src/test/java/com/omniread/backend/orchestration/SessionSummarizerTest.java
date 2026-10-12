package com.omniread.backend.orchestration;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.omniread.backend.gateway.RagGatewayClient;
import com.omniread.backend.session.ChatMessageMapper;
import com.omniread.backend.session.ChatSession;
import com.omniread.backend.session.ChatSessionMapper;
import com.omniread.backend.session.ContextBudget;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 触发路径**不许抛异常**。
 *
 * <p>它跑在用户那一轮的尾巴上，而那一轮的回答**已经落库**：在这里抛出去，用户看到的是一个
 * 失败的响应然后重试——于是同一轮写重了。这条约定写在 {@code SessionSummarizer} 的类注释里，
 * 但**没有别的用例能走到它**：`/summarize` 的失败发生在后台任务内部，被 `summarize` 自己的
 * catch 吃掉。所以这里直接把「读库」那一步弄炸，断言它不外抛。
 */
class SessionSummarizerTest {

    @Test
    @DisplayName("读会话炸了也不外抛（库忙、库损坏、列与实体对不上）")
    void sessionReadFailureDoesNotEscape() {
        ChatSessionMapper sessions = mock(ChatSessionMapper.class);
        when(sessions.findById("s-1")).thenThrow(new IllegalStateException("库读不出来"));

        assertThatCode(() -> summarizer(sessions, mock(ChatMessageMapper.class)).maybeSummarize("s-1"))
                .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("读消息炸了也不外抛")
    void messageReadFailureDoesNotEscape() {
        ChatSessionMapper sessions = mock(ChatSessionMapper.class);
        when(sessions.findById("s-1")).thenReturn(session());
        ChatMessageMapper messages = mock(ChatMessageMapper.class);
        when(messages.findBySession("s-1")).thenThrow(new IllegalStateException("库读不出来"));

        assertThatCode(() -> summarizer(sessions, messages).maybeSummarize("s-1"))
                .doesNotThrowAnyException();
    }

    private static SessionSummarizer summarizer(ChatSessionMapper sessions, ChatMessageMapper messages) {
        return new SessionSummarizer(
                sessions,
                messages,
                mock(RagGatewayClient.class),
                ContextBudget.DEFAULT,
                new SummaryExecutor(Runnable::run));
    }

    private static ChatSession session() {
        ChatSession session = new ChatSession();
        session.setId("s-1");
        session.setUserId(1L);
        session.setBookId(1);
        session.setLevel(ChatSession.LEVEL_FULL);
        return session;
    }
}
