package com.omniread.backend.user;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 按账户的阅读进度：一个账户一本书一行。 */
@Mapper
public interface UserProgressMapper {

    /** 有则更新、无则插入；复合主键就是冲突目标。 */
    int upsert(UserProgress progress);

    UserProgress find(@Param("userId") long userId, @Param("bookId") int bookId);

    List<UserProgress> findByUserId(@Param("userId") long userId);

    /** 停用账户时随会话一起清理（D15）。 */
    int deleteByUserId(@Param("userId") long userId);
}
