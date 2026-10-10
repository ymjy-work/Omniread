package com.omniread.backend.session;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 会话的列表项，与外部契约的 `ChatSessionSummary` 一致（手写而不是生成：外部契约不喂生成器，
 * 同 `progress/Progress`）。
 *
 * <p>**不含消息**：列表不为每条会话搬运全文，那是详情端点的事。
 *
 * <p>两个时间戳直接透传库里那份 ISO-8601 字符串，不做 `Instant` 转换——库里存的就是它，
 * 转一道只是多一次可能出错的解析，序列化出来的字节完全一样。
 */
public record ChatSessionSummary(
        String id,
        @JsonProperty("book_id") Integer bookId,
        String title,
        String level,
        @JsonProperty("forked_from") String forkedFrom,
        @JsonProperty("created_at") String createdAt,
        @JsonProperty("last_active_at") String lastActiveAt) {

    public static ChatSessionSummary of(ChatSession session) {
        return new ChatSessionSummary(
                session.getId(),
                session.getBookId(),
                session.getTitle(),
                session.getLevel(),
                session.getForkedFrom(),
                session.getCreatedAt(),
                session.getLastActiveAt());
    }
}
