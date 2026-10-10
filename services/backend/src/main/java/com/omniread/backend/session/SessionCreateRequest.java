package com.omniread.backend.session;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/**
 * 新建会话的请求体，与外部契约的 `SessionCreateRequest` 一致。
 *
 * <p>`level` 用字符串加正则而不是枚举：库里存的就是 TEXT（`ChatSession.level`），
 * 加一个枚举就要在两处之间来回转，而这里只有两个取值。**范围由正则挡住**，
 * 越界即 400 `RAG_INVALID_REQUEST`（缺字段与取值非法同一出口）。
 */
public record SessionCreateRequest(
        @JsonProperty("book_id") @NotNull Integer bookId,
        @NotNull @Pattern(regexp = "past|full") String level) {
}
