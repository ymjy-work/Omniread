package com.omniread.backend.session;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/**
 * 切档位分叉的请求体，与外部契约的 `ForkRequest` 一致。
 *
 * <p>`at_seq` 缺省表示「继承到当前点」。**下界 1 由注解挡、越上界与半轮由服务端规整**
 * ——契约把这两件事分开写是刻意的：越界是前端「一边拉消息一边点分叉」必然算出来的，
 * 报错等于把一次时序竞争变成一次失败；而 0 或负数不是算出来的，是传错了。
 */
public record ForkRequest(
        @NotNull @Pattern(regexp = "past|full") String level,
        @JsonProperty("at_seq") @Min(1) Integer atSeq) {
}
