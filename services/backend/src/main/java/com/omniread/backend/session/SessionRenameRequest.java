package com.omniread.backend.session;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;

/**
 * 改会话标题的请求体，与外部契约的 `SessionRenameRequest` 一致。
 *
 * <p>长度上限**不在这里用 `@Size`**：那个按 char 数算，而一个 emoji 占两个 char——
 * 20 个 emoji 会被它判成超长。上限按码点在服务里判，与首轮自动命名同一个数。
 */
public record SessionRenameRequest(@JsonProperty("title") @NotBlank String title) {
}
