package com.omniread.backend.user;

import java.time.Clock;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import org.springframework.stereotype.Component;

/**
 * 「账户过没过期」的唯一判据。
 *
 * <p>三个地方要问同一件事：登录（{@link AccountService#authenticate}）、每次请求解析
 * 登录态（{@link AuthService#resolve}）、每日清理（{@link AccountJanitor}）。
 * 各写一片判断，迟早出现「能登录但进不去」或者「已经删了还能用一天」这类错位。
 *
 * <p>有效期从 {@code created_at} 起算，**不另存一列**：加列要动 {@code SCHEMA_VERSION}，
 * 那道闸门对「库比代码旧」是直接拒绝启动，而本项目没有迁移框架。
 */
@Component
public class AccountExpiry {

    private final AccountProperties properties;
    private final Clock clock;

    public AccountExpiry(AccountProperties properties, Clock clock) {
        this.properties = properties;
        this.clock = clock;
    }

    /**
     * 时间戳解析不出来时**当作没过期**：删账户不可逆，宁可少删一个，
     * 也不要因为一行格式异常把还在用的账户清掉——那种错误查起来毫无线索。
     */
    public boolean isExpired(User user) {
        if (!properties.enabled()) {
            return false;
        }
        Instant createdAt = parse(user.getCreatedAt());
        if (createdAt == null) {
            return false;
        }
        return !createdAt.plus(properties.ttl()).isAfter(clock.instant());
    }

    private static Instant parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return Instant.parse(raw);
        } catch (DateTimeParseException ignored) {
            return null;
        }
    }
}
