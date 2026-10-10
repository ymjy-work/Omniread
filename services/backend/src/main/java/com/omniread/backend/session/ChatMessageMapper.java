package com.omniread.backend.session;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 会话消息表的读写。
 *
 * <p>`seq` 的赋值不在这里做——它要「读最大值 → 写 → 撞车重试」三步，属于编排而不是
 * 一条语句能表达的事。取号与重试都在 {@link ChatMessageStore}。
 */
@Mapper
public interface ChatMessageMapper {

    int insert(ChatMessage message);

    /** 取号用：当前会话的最大 `seq`，空会话返回 null（调用方按 0 处理）。 */
    Integer maxSeq(@Param("sessionId") String sessionId);

    List<ChatMessage> findBySession(@Param("sessionId") String sessionId);

    /** 分叉用：只取到某个 `seq` 为止（含）。 */
    List<ChatMessage> findBySessionUpTo(
            @Param("sessionId") String sessionId, @Param("uptoSeq") int uptoSeq);

    /** 摘要用：`summary_upto` 之后、某个 `seq` 之前的消息。 */
    List<ChatMessage> findBySessionBetween(
            @Param("sessionId") String sessionId,
            @Param("afterId") Long afterId,
            @Param("beforeSeq") Integer beforeSeq);

    /** 会话消息总量（条数），用于按需取全量。 */
    int countBySession(@Param("sessionId") String sessionId);

    int deleteBySession(@Param("sessionId") String sessionId);
}
