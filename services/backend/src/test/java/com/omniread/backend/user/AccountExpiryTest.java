package com.omniread.backend.user;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 「账户过没过期」的判据。纯函数，不连库。
 *
 * <p>三条要钉住：关闭时永远不过期；到期边界按「到点即过期」；时间戳坏了**当作没过期**
 * ——删账户不可逆，宁可少删一个。
 */
class AccountExpiryTest {

    private static final Instant NOW = Instant.parse("2026-10-24T12:00:00Z");

    private static AccountExpiry withTtl(Duration ttl) {
        return new AccountExpiry(
                new AccountProperties(ttl), Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private static User created(String createdAt) {
        User user = new User();
        user.setUsername("someone");
        user.setCreatedAt(createdAt);
        return user;
    }

    @Test
    @DisplayName("ttl 为 0 时永远不过期")
    void disabledNeverExpires() {
        AccountExpiry expiry = withTtl(Duration.ZERO);
        assertThat(expiry.isExpired(created("2020-01-01T00:00:00Z"))).isFalse();
    }

    @Test
    @DisplayName("未到期")
    void notYetExpired() {
        AccountExpiry expiry = withTtl(Duration.ofDays(14));
        assertThat(expiry.isExpired(created("2026-10-20T12:00:00Z"))).isFalse();
    }

    @Test
    @DisplayName("到点即过期（边界那一毫秒算过期）")
    void expiresExactlyAtTtl() {
        AccountExpiry expiry = withTtl(Duration.ofDays(14));
        assertThat(expiry.isExpired(created("2026-10-10T12:00:00Z"))).isTrue();
    }

    @Test
    @DisplayName("时间戳缺失或不是 ISO 串时当作没过期")
    void malformedCreatedAtIsTreatedAsNotExpired() {
        AccountExpiry expiry = withTtl(Duration.ofDays(1));
        assertThat(expiry.isExpired(created(null))).isFalse();
        assertThat(expiry.isExpired(created(""))).isFalse();
        assertThat(expiry.isExpired(created("2026/10/10 12:00"))).isFalse();
    }
}
