package com.omniread.backend.user;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 账户表的读写。语句在 {@code resources/mapper/UserMapper.xml}，
 * namespace 与语句 id 必须与这里逐字一致（`Invalid bound statement` 九成出在对不上）。
 *
 * <p>**没有按 username 改口令的方法**：口令重置是管理方动作，等「停用即清理」
 * 一起做，不在这里先开一个没人用的口子。
 */
@Mapper
public interface UserMapper {

    /** `id` 由 `useGeneratedKeys` 回填进参对象。 */
    int insert(User user);

    User findById(@Param("id") long id);

    User findByUsername(@Param("username") String username);

    List<User> findAll();

    int updateStatus(@Param("id") long id, @Param("status") String status);

    int updateLastLogin(@Param("id") long id, @Param("lastLoginAt") String lastLoginAt);

    /**
     * 整行删除。子表（登录会话 / 对话会话 / 消息 / 进度 / 用量）都是
     * {@code ON DELETE CASCADE}，一条 DELETE 就够——不必像
     * {@link AccountService#disableAndPurge} 那样逐表删。
     */
    int deleteById(@Param("id") long id);
}
