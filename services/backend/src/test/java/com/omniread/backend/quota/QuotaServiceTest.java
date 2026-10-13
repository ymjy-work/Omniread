package com.omniread.backend.quota;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.QuotaException;
import com.omniread.backend.user.AccountService;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 配额的三笔账：日额度（落库、可退还）、分钟窗口（内存）、并发（内存）。
 *
 * <p>**小阈值**（2 轮/日、2 轮/分、并发 1）是唯一能在一次测试里把三条都触发的办法；
 * 时间用一个可拨的时钟，所以「次日自动恢复」「窗口过期」这些不必真等。
 *
 * <p>每个用例**各用各的账户 id**：上下文与库是整个类共用的，共用 id 就会互相看见对方
 * 攒下的计数，而那种失败看起来像限额算错了。
 */
@SpringBootTest(properties = {
        "omniread.quota.turns-per-day=2",
        "omniread.quota.turns-per-minute=10",
        "omniread.quota.concurrent=1",
        "omniread.quota.login-failures=3",
        "omniread.quota.login-window=15m",
        "omniread.quota.login-lock=15m"
})
class QuotaServiceTest {

    private static final MutableClock CLOCK =
            new MutableClock(Instant.parse("2026-10-13T10:00:00Z"), ZoneOffset.UTC);

    private static final Path DB_PATH = createDbPath();

    static Path createDbPath() {
        try {
            return Files.createTempDirectory("omniread-quota-test").resolve("omniread.db");
        } catch (IOException e) {
            throw new IllegalStateException("建不了临时库目录", e);
        }
    }

    @DynamicPropertySource
    static void storeLocation(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", () -> DB_PATH.toString());
        registry.add("omniread.rag.base-url", () -> "http://127.0.0.1:1");
    }

    /** 可拨的时钟：跨日、窗口过期这些只能靠它验，而生产读的是同一个 Clock 抽象。 */
    @TestConfiguration
    static class TestClock {
        @Bean
        @Primary
        Clock mutableClock() {
            return CLOCK;
        }
    }

    @Autowired
    private QuotaService quota;

    @Autowired
    private LoginThrottle throttle;

    @Autowired
    private UsageDailyMapper usage;

    @Autowired
    private AccountService accounts;

    /**
     * 每个用例发一个真账户。**不能拿 101 这种数字直接当 user_id**：
     * 连接串里开着 `foreign_keys=on`，usage_daily 的 user_id 指向 users 表——
     * 凭空写的 id 会在插入时被外键拒绝（第一版就是这么红的）。
     */
    private long newUser(String name) {
        return accounts.create(name, "quota-test-password").getId();
    }

    @Test
    @DisplayName("日额度：用完即 429，退还后可以再问")
    void dailyQuotaBlocksAndRefundRestores() {
        long user = newUser("quota-daily");
        QuotaLease first = quota.acquire(user);
        quota.release(first);
        QuotaLease second = quota.acquire(user);
        quota.release(second);
        assertThat(quota.turnsToday(user)).isEqualTo(2);

        assertThatThrownBy(() -> quota.acquire(user))
                .isInstanceOf(QuotaException.class)
                .satisfies(failure -> {
                    QuotaException quotaFailure = (QuotaException) failure;
                    assertThat(quotaFailure.code()).isEqualTo(ErrorCode.RAG_DAILY_QUOTA_EXCEEDED);
                    // 到明天零点为止，落在 (0, 24h]
                    assertThat(quotaFailure.retryAfterSeconds()).isBetween(1L, 24 * 3600L);
                });

        quota.refund(second);
        assertThat(quota.turnsToday(user)).isEqualTo(1);
        quota.release(quota.acquire(user));
        assertThat(quota.turnsToday(user)).isEqualTo(2);
    }

    @Test
    @DisplayName("退还只生效一次：流式与拦截器两条路都可能退到同一次")
    void refundIsIdempotent() {
        long user = newUser("quota-refund");
        QuotaLease lease = quota.acquire(user);
        quota.release(lease);
        quota.refund(lease);
        quota.refund(lease);
        assertThat(quota.turnsToday(user)).isZero();
    }

    @Test
    @DisplayName("并发 1：上一轮没结束就再问 → 429；放掉之后又能问")
    void concurrentQueryIsRejected() {
        long user = newUser("quota-concurrent");
        QuotaLease running = quota.acquire(user);
        assertThatThrownBy(() -> quota.acquire(user))
                .isInstanceOf(QuotaException.class)
                .satisfies(failure -> assertThat(((QuotaException) failure).code())
                        .isEqualTo(ErrorCode.RAG_CONCURRENT_QUERY));

        quota.release(running);
        quota.release(quota.acquire(user));
    }

    @Test
    @DisplayName("跨日自动恢复：日界过了额度就回来了，不必人工解锁")
    void quotaResetsNextDay() {
        long user = newUser("quota-nextday");
        quota.release(quota.acquire(user));
        quota.release(quota.acquire(user));
        assertThatThrownBy(() -> quota.acquire(user)).isInstanceOf(QuotaException.class);

        CLOCK.advance(Duration.ofHours(24));
        quota.release(quota.acquire(user));
        assertThat(quota.turnsToday(user)).isEqualTo(1);
    }

    @Test
    @DisplayName("登录失败锁 IP：窗口内攒够次数即锁，锁到期放行，成功一次清空")
    void loginThrottleLocksByIp() {
        String ip = "203.0.113.9";
        throttle.check(ip);
        throttle.onFailure(ip);
        throttle.onFailure(ip);
        throttle.onFailure(ip);
        assertThatThrownBy(() -> throttle.check(ip))
                .isInstanceOf(QuotaException.class)
                .satisfies(failure -> {
                    QuotaException quotaFailure = (QuotaException) failure;
                    assertThat(quotaFailure.code()).isEqualTo(ErrorCode.RAG_LOGIN_LOCKED);
                    assertThat(quotaFailure.retryAfterSeconds()).isEqualTo(15 * 60L);
                });

        CLOCK.advance(Duration.ofMinutes(15));
        throttle.check(ip);
        throttle.onSuccess(ip);
        throttle.check(ip);
    }

    @Test
    @DisplayName("保留期：早于截止日的行清掉，当天的不动")
    void retentionDeletesOldRows() {
        long user = newUser("quota-retention");
        usage.bump("2020-01-01", user);
        usage.bump("2020-01-02", user);
        String today = CLOCK.instant().atZone(ZoneOffset.UTC).toLocalDate().toString();
        usage.bump(today, user);

        int removed = usage.deleteBefore("2020-01-02");
        assertThat(removed).isEqualTo(1);
        assertThat(usage.turns(today, user)).isEqualTo(1);
    }
}
