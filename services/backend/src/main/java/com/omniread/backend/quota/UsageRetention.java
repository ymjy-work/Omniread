package com.omniread.backend.quota;

import java.time.Clock;
import java.time.LocalDate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/**
 * 每日计数的保留期：启动时清掉旧行（`docs/m1/配额与限流方案.md` §三）。
 * 不清也不影响正确性——超期的行不会再被读到——清的是只涨不落的表。
 *
 * <p>挂 {@link ApplicationReadyEvent} 而不是做成 {@code ApplicationRunner}：runner 与建表的
 * {@code SchemaInitializer} 是平级的，谁先谁后没有保证（登录会话清理为此踩过一次，
 * 见 {@code AuthSessionJanitor} 的类注释）。
 */
@Component
public class UsageRetention {

    private static final Logger log = LoggerFactory.getLogger(UsageRetention.class);

    private final UsageDailyMapper usage;

    private final QuotaProperties properties;

    private final Clock clock;

    public UsageRetention(UsageDailyMapper usage, QuotaProperties properties, Clock clock) {
        this.usage = usage;
        this.properties = properties;
        this.clock = clock;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        String cutoff = LocalDate.now(clock).minusDays(properties.retentionDays()).toString();
        int removed = usage.deleteBefore(cutoff);
        if (removed > 0) {
            log.info("清理 {} 之前的每日用量：{} 行", cutoff, removed);
        }
    }
}
