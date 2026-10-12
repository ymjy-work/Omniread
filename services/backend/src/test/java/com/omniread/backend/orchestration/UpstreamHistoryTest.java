package com.omniread.backend.orchestration;

import static org.assertj.core.api.Assertions.assertThat;

import com.omniread.backend.contract.model.HistoryMessage;
import com.omniread.backend.session.ChatMessage;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 出站信封：库里的消息 → 契约的 `HistoryMessage`。
 *
 * <p>问答的 `history` 与摘要的 `messages` 共用它，所以这里的每一条都是**两个功能一起**的约束：
 * 这里放宽一毫米，两个请求都会带上不该带的东西；这里收紧一毫米，两个请求都会少一段上下文。
 */
class UpstreamHistoryTest {

    private static ChatMessage message(String role, String content) {
        ChatMessage message = new ChatMessage();
        message.setRole(role);
        message.setContent(content);
        return message;
    }

    @Test
    @DisplayName("正常消息原样过，角色按契约枚举映射")
    void normalMessagesPassThrough() {
        List<HistoryMessage> contract = UpstreamHistory.of(List.of(
                message(ChatMessage.ROLE_USER, "她后来怎么样了？"),
                message(ChatMessage.ROLE_ASSISTANT, "她回去了[C1]。")));

        assertThat(contract).hasSize(2);
        assertThat(contract.get(0).getRole()).isEqualTo(HistoryMessage.RoleEnum.USER);
        assertThat(contract.get(0).getContent()).isEqualTo("她后来怎么样了？");
        assertThat(contract.get(1).getRole()).isEqualTo(HistoryMessage.RoleEnum.ASSISTANT);
    }

    @Test
    @DisplayName("超长正文截断到契约上限并补标记")
    void longContentIsTruncated() {
        String long_ = "字".repeat(UpstreamHistory.MAX_CONTENT + 500);

        String content = UpstreamHistory.of(List.of(message(ChatMessage.ROLE_USER, long_)))
                .get(0)
                .getContent();

        assertThat(content).hasSize(UpstreamHistory.MAX_CONTENT);
        assertThat(content).endsWith(UpstreamHistory.TRUNCATION_MARK);
    }

    @Test
    @DisplayName("空正文不进信封：契约的 content 有 minLength: 1，带出去整条请求被判 400")
    void blankContentIsDropped() {
        List<HistoryMessage> contract = UpstreamHistory.of(List.of(
                message(ChatMessage.ROLE_USER, "第一问"),
                message(ChatMessage.ROLE_ASSISTANT, ""),
                message(ChatMessage.ROLE_USER, "   "),
                message(ChatMessage.ROLE_ASSISTANT, "答上来了[C1]。")));

        assertThat(contract).extracting(HistoryMessage::getContent)
                .as("模型一个 token 都没吐的那一轮会落成空串；它是零信息，丢掉不损失什么，"
                        + "留着则整条请求被拒——而请求看上去没有任何问题")
                .containsExactly("第一问", "答上来了[C1]。");
    }

    @Test
    @DisplayName("全是空正文时给空列表（调用方要按契约的 minItems: 1 兜住）")
    void allBlankYieldsEmpty() {
        assertThat(UpstreamHistory.of(List.of(message(ChatMessage.ROLE_ASSISTANT, "")))).isEmpty();
        assertThat(UpstreamHistory.of(List.of())).isEmpty();
    }

    @Test
    @DisplayName("null 正文当作空正文，不抛")
    void nullContentIsTreatedAsBlank() {
        assertThat(UpstreamHistory.of(List.of(message(ChatMessage.ROLE_ASSISTANT, null)))).isEmpty();
    }
}
