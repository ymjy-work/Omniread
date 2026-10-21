package com.omniread.backend.session;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 一条消息的对外形状，与外部契约的 `ChatMessage` 一致。
 *
 * <p>名字不叫 `ChatMessage`：那个名字是**表实体**（多 `sessionId` / `tokenCount` / `meta`
 * 三个字段）。给对外形状换个名字，比给实体改名要动的面小得多。
 *
 * <p>**仍然不带整列 `meta`**：那一列是内部诊断用的（改写前后、模型与 prompt 版本）。
 * 只有 `context_chapters` 被单独挑出来下发——它是刷新后恢复「检索依据」引用条的**唯一**来源，
 * 不下发的话恢复出来的历史就只剩正文。解析失败按空处理：一条消息的展示不该因为
 * 诊断列写坏了而让整个请求失败。
 */
public record ChatMessageView(
        Long id,
        Integer seq,
        String role,
        String content,
        @JsonProperty("context_chapters") List<Integer> contextChapters,
        @JsonProperty("created_at") String createdAt) {

    private static final ObjectMapper MAPPER = JsonMapper.builder().build();

    public static ChatMessageView of(ChatMessage message) {
        return new ChatMessageView(
                message.getId(),
                message.getSeq(),
                message.getRole(),
                message.getContent(),
                contextChaptersOf(message.getMeta()),
                message.getCreatedAt());
    }

    @SuppressWarnings("unchecked")
    private static List<Integer> contextChaptersOf(String meta) {
        if (meta == null || meta.isBlank()) {
            return List.of();
        }
        try {
            Map<String, Object> parsed = MAPPER.readValue(meta, Map.class);
            if (!(parsed.get("context_chapters") instanceof List<?> items)) {
                return List.of();
            }
            List<Integer> indexes = new ArrayList<>();
            for (Object item : items) {
                if (item instanceof Number number) {
                    indexes.add(number.intValue());
                }
            }
            return indexes;
        } catch (JacksonException e) {
            return List.of();
        }
    }
}
