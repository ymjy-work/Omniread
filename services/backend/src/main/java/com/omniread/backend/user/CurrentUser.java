package com.omniread.backend.user;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

/**
 * 当前账户的对外形状，与外部契约的 `CurrentUser` 一致。
 *
 * <p>**刻意不含账户 id**：前端用不到，而一旦发出去就成了事实上的契约的一部分，
 * 之后想收回就得再走一次契约变更。账户名在本系统内唯一，够用了。
 *
 * <p>`expiresAt` 是登录会话的到期时刻，前端据此做本地登出与提示，
 * 不必自己按 8 小时算——算的那份与服务端的那份迟早会不一样。
 */
public record CurrentUser(String username, @JsonProperty("expires_at") Instant expiresAt) {
}
