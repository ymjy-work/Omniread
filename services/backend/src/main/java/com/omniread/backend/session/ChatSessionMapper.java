package com.omniread.backend.session;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 对话会话表的读写。
 *
 * <p>**鉴权路径是「先按 id 取、再比 `userId`」，不是把 `user_id` 放进 `WHERE`**：
 * 跨用户访问要判 403、不存在要判 404，而「带 userId 的按 id 查询」会把这两种情况都变成
 * 「查不到」，上层就再也分不开了。所以按 id 取单个会话一律用 {@link #findById}，
 * 取出来自己比 `userId`（`SessionService` 里那几条 403 / 404 用例钉的就是这件事）。
 * **没有 `findByIdForUser` 这个方法**，别再把它加回来。
 *
 * <p>反过来，**批量与列表操作按用户过滤是对的**：它们不需要区分「哪一条不是你的」，
 * 用 `WHERE user_id = ?` 一条 SQL 收口，比取出来再筛更省也更容易写对。
 */
@Mapper
public interface ChatSessionMapper {

    int insert(ChatSession session);

    ChatSession findById(@Param("id") String id);

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
