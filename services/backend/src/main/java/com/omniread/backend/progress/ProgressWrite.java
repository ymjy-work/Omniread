package com.omniread.backend.progress;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

/**
 * 阅读进度的写入体，与外部契约的 ProgressWrite 一致。
 *
 * max_seq 的下界 1 由这里的注解与 {@code RealmValidator} 双重把关：注解管「缺字段 / 小于 1」，
 * 上界 chapter_count 只有拿到书目录后才能判，留在 Controller。
 */
public record ProgressWrite(
        @JsonProperty("max_seq") @NotNull @Min(1) Integer maxSeq) {
}
