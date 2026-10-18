package com.omniread.backend.user;

import java.time.Instant;

/**
 * 拦截器校验通过后放进请求属性的当前账户。
 *
 * <p>只有这三样，且**不含口令哈希**——它会被 `@RequestAttribute` 取进控制器，
 * 随手写进日志或响应体的机会很多，所以这里不放任何不该外流的东西。
 * `expiresAt` 是登录会话的到期时刻，`/auth/me` 要原样回给前端。
 */
public record AuthenticatedUser(long userId, String username, Instant expiresAt) {
}
