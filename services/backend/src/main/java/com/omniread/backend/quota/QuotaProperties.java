package com.omniread.backend.quota;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 配额与限流的可调项（`docs/方案.md（配额与限流一节）` §二）。
 *
 * <p>值都进配置的理由是**验收**：要逐项触发四类 429，得在 2 轮/日、1 轮/分这种小阈值下跑，
 * 拿默认值测就得等一整天。`login-*` 三个按**IP** 计，其余按**账户**计。
 *
 * <p>`retention-days` 只管 usage_daily 的旧行：日额度表按天累加，不清的话它只涨不落。
 */
@ConfigurationProperties(prefix = "omniread.quota")
public record QuotaProperties(
        int turnsPerMinute,
        int turnsPerDay,
        int concurrent,
        int loginFailures,
        Duration loginWindow,
        Duration loginLock,
        int retentionDays) {
}
