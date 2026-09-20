package com.omniread.backend.progress;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 阅读进度的对外响应形状，与外部契约的 Progress 逐字段一致（book_id / max_seq）。
 * 持久化文件也用同一形状，排查时 JSON 与接口返回可以直接对读。
 */
public record Progress(
        @JsonProperty("book_id") int bookId,
        @JsonProperty("max_seq") int maxSeq) {
}
