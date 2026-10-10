package com.omniread.backend.session;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 一条消息的对外形状，与外部契约的 `ChatMessage` 一致。
 *
 * <p>名字不叫 `ChatMessage`：那个名字是**表实体**（多 `sessionId` / `tokenCount` / `meta`
 * 三个字段）。给对外形状换个名字，比给实体改名要动的面小得多。
 *
 * <p>**不带 `meta`**：那一列是内部诊断用的（引用编号、`context_chapters`、改写前后、
 * 模型与 prompt 版本）。下发出去它就会变成前端依赖的事实契约，而那四样随时可能变。
 */
public record ChatMessageView(
        Long id,
        Integer seq,
        String role,
        String content,
        @JsonProperty("created_at") String createdAt) {

    public static ChatMessageView of(ChatMessage message) {
        return new ChatMessageView(
                message.getId(),
                message.getSeq(),
                message.getRole(),
                message.getContent(),
                message.getCreatedAt());
    }
}
