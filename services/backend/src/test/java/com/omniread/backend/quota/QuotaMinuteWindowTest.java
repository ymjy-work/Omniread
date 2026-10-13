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
 * 分钟窗口单独一个类：**它的阈值必须小于日额度**，否则日额度那条检查总是先命中
 * （检查顺序是日额度 → 并发 → 分钟），这条用例就永远测不到分钟限流——
 * 第一版把两个阈值都设成 2，跑出来的正是 `RAG_DAILY_QUOTA_EXCEEDED`。
 */
@SpringBootTest(properties = {
        "omniread.quota.turns-per-minute=2",
        "omniread.quota.turns-per-day=10",
        "omniread.quota.concurrent=1"
})
class QuotaMinuteWindowTest {

    private static final MutableClock CLOCK =
            new MutableClock(Instant.parse("2026-10-13T10:00:00Z"), ZoneOffset.UTC);

    private static final Path DB_PATH = createDbPath();

    static Path createDbPath() {
        try {
            return Files.createTempDirectory("omniread-quota-minute-test").resolve("omniread.db");
        } catch (IOException e) {
            throw new IllegalStateException("建不了临时库目录", e);
        }
    }

    @DynamicPropertySource
    static void storeLocation(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", () -> DB_PATH.toString());
        registry.add("omniread.rag.base-url", () -> "http://127.0.0.1:1");
    }

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
    private AccountService accounts;

    @Test
    @DisplayName("分钟窗口：到点 429 并给出等待秒数，窗口滑过去就恢复")
    void minuteWindowBlocksThenSlides() {
        long user = accounts.create("quota-minute", "quota-test-password").getId();
        quota.release(quota.acquire(user));
        quota.release(quota.acquire(user));
        // 日额度是 10，所以这里挡下它的只可能是分钟窗口
        assertThat(quota.turnsToday(user)).isEqualTo(2);

        assertThatThrownBy(() -> quota.acquire(user))
                .isInstanceOf(QuotaException.class)
                .satisfies(failure -> {
                    QuotaException quotaFailure = (QuotaException) failure;
                    assertThat(quotaFailure.code()).isEqualTo(ErrorCode.RAG_RATE_LIMITED);
                    assertThat(quotaFailure.retryAfterSeconds()).isBetween(1L, 60L);
                });
        // 被挡下的那一轮**不计数**：它没有占位成功
        assertThat(quota.turnsToday(user)).isEqualTo(2);

        CLOCK.advance(Duration.ofSeconds(61));
        quota.release(quota.acquire(user));
        assertThat(quota.turnsToday(user)).isEqualTo(3);
    }
}
