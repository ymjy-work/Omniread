package com.omniread.backend.progress;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotNull;

/**
 * 阅读进度的写入体，与外部契约的 ProgressWrite 一致。
 *
 * <p>只有 {@code @NotNull}，**范围检查全交给 {@code RealmValidator}**：上界 chapter_count
 * 要拿到书目录才能判，下界 1 却没有这个限制——两边各判一半的后果是同一个字段
 * 越下界返回 RAG_INVALID_REQUEST、越上界返回 RAG_INVALID_REALM，
 * 而前端按 code 分支，会把它当成两件不同的事。
 */
public record ProgressWrite(
        @JsonProperty("max_seq") @NotNull Integer maxSeq) {
}
