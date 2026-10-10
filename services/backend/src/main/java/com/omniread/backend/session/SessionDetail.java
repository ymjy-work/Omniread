package com.omniread.backend.session;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * 会话详情：`ChatSessionSummary` 的全部字段 + 消息，与外部契约的 `SessionDetail` 一致
 * （契约那边用 `allOf` 拼，这里是平的——序列化出来的 JSON 完全相同，
 * 而 Java 的 record 不能继承 record）。
 */
public record SessionDetail(
        String id,
        @JsonProperty("book_id") Integer bookId,
        String title,
        String level,
        @JsonProperty("forked_from") String forkedFrom,
        @JsonProperty("created_at") String createdAt,
        @JsonProperty("last_active_at") String lastActiveAt,
        List<ChatMessageView> messages) {

    public static SessionDetail of(ChatSession session, List<ChatMessageView> messages) {
        return new SessionDetail(
                session.getId(),
                session.getBookId(),
                session.getTitle(),
                session.getLevel(),
                session.getForkedFrom(),
                session.getCreatedAt(),
                session.getLastActiveAt(),
                messages);
    }
}
