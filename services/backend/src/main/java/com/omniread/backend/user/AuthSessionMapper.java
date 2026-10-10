package com.omniread.backend.user;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 登录会话表的读写。
 *
 * <p>查一条会话是**每个受保护请求都要做**的事，所以它的语句要能走主键索引——
 * `findByTokenHash` 打的是主键，不是全表扫描。
 */
@Mapper
public interface AuthSessionMapper {

    int insert(AuthSession session);

    AuthSession findByTokenHash(@Param("tokenHash") String tokenHash);

    /** 退出登录：只删自己那一条。 */
    int deleteByTokenHash(@Param("tokenHash") String tokenHash);

    /**
     * 停用账户时按用户批量吊销（D15）。
     *
     * <p>这正是选「自建会话表」而不是 JWT 的理由：JWT 要做到这一点必须再加一张黑名单表。
     */
    int deleteByUserId(@Param("userId") long userId);

    /** 过期行清理：启动时一次，之后每日一次。 */
    int deleteExpired(@Param("now") String now);

    int touch(@Param("tokenHash") String tokenHash, @Param("lastSeenAt") String lastSeenAt);
}
