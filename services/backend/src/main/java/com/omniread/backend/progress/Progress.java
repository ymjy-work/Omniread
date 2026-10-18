package com.omniread.backend.progress;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 阅读进度的对外响应形状，与外部契约的 Progress 逐字段一致（book_id / progress）。
 * 持久化文件也用同一形状，排查时 JSON 与接口返回可以直接对读。
 *
 * <p>字段叫 `progress` 而不是旧名 `max_seq`：它是**已读到的章号**（= `chapter_index`），
 * 与查询请求里的 `QueryRequest.progress` **是同一个量、现在也是同一个名**。
 * 旧名与 `ChatMessage.seq`（**会话内消息的序号**，完全不相干的另一个量）共用 `seq` 词根，
 * 读的人容易把两者当成一回事——这是 2026-10-18 改名的唯一理由。
 */
public record Progress(
        @JsonProperty("book_id") int bookId,
        int progress) {
}
