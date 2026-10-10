package com.omniread.backend.session;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 对话会话表的读写。
 *
 * <p>**每个按 id 取会话的方法都带 `userId`**：跨用户访问要判 403，而判定的前提是能区分
 * 「不存在」与「不是你的」。把 `user_id` 放进 `WHERE` 里，越权查询自然返回空，
 * 上层再按「找不到」还是「找到了但不是你的」给不同响应——不需要先查出来再比对。
 */
@Mapper
public interface ChatSessionMapper {

    int insert(ChatSession session);

    ChatSession findById(@Param("id") String id);

    ChatSession findByIdForUser(@Param("id") String id, @Param("userId") long userId);

    /** 列表按最近活跃倒序；`last_active_at` 是会话被继续时刷新的那个字段。 */
    List<ChatSession> findByUserId(@Param("userId") long userId);

    /** 摘要与 `summary_upto` **必须在同一条 UPDATE 里**，分开写会让下次摘要重复或漏段。 */
    int updateSummary(
            @Param("id") String id,
            @Param("summary") String summary,
            @Param("summaryUpto") Long summaryUpto,
            @Param("summaryPromptVersion") String summaryPromptVersion);

    int touch(@Param("id") String id, @Param("lastActiveAt") String lastActiveAt);

    int updateTitle(@Param("id") String id, @Param("title") String title);

    int deleteForUser(@Param("id") String id, @Param("userId") long userId);

    /** 停用账户时级联清理（D15）；消息由外键 `ON DELETE CASCADE` 带走。 */
    int deleteByUserId(@Param("userId") long userId);
}
