package com.omniread.backend.progress;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

/**
 * 阅读进度的写入体，与外部契约的 ProgressWrite 一致。
 *
 * <p>**两个边界归两个码，判据是「这条约束写没写在 schema 里」**：
 * 下界 1 是契约写明的（`minimum: 1`），越界即请求本身不合法 → `RAG_INVALID_REQUEST`；
 * 上界 chapter_count 只有拿到书目录才判得了，那是语义检查 → `RAG_INVALID_REALM`。
 *
 * <p>看着像「同一个字段分了两个码」，其实分的是两件事：`1` 是任何人都知道的合法下界，
 * `193` 是**这本书**的上界。Python 那一侧同一条口径（`progress` 的 `ge/le` 归 REQUEST、
 * 「超出本书章节数」归 REALM），两侧对同一个值给同一个码。
 */
public record ProgressWrite(@NotNull @Min(1) Integer progress) {
}
