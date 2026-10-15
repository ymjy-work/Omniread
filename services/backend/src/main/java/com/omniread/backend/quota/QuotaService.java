package com.omniread.backend.quota;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.QuotaException;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZonedDateTime;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

/**
 * 单账户的限频 / 日额度 / 并发（`docs/方案.md（配额与限流一节）`）。判断全在网关这一层：
 * 身份已经在手，超限不必调下游。
 *
 * <p>三笔账的存放位置不同，各有各的理由：
 *
 * - **日额度落库**（`usage_daily`）：跨重启保留。清掉它等于白送额度。
 * - **分钟窗口在内存**：单实例、重启清零可接受——重启本来就少见，而每分钟 5 轮这条
 *   约束的窗口只有一分钟，代价比多一张表小。
 * - **并发数在内存**：它描述的是「此刻在跑几轮」，重启后本来就没有在跑的轮次。
 *
 * <p>检查顺序是**日额度 → 并发 → 分钟**。三者同时命中时先说日额度：它是唯一
 * 「等一会儿也没用」的，另外两条都可以重试。
 */
@Component
public class QuotaService {

    private static final long MINUTE_MS = 60_000L;

    /** 账户 → 最近一分钟内每一轮的发起时刻 */
    private final Map<Long, Deque<Long>> minuteWindows = new ConcurrentHashMap<>();

    /** 账户 → 正在跑的轮数。**并发 1 就是靠它挡住的**：占位时才加一，收尾时减一。 */
    private final Map<Long, AtomicInteger> inFlight = new ConcurrentHashMap<>();

    private final UsageDailyMapper usage;

    private final QuotaProperties properties;

    private final Clock clock;

    public QuotaService(UsageDailyMapper usage, QuotaProperties properties, Clock clock) {
        this.usage = usage;
        this.properties = properties;
        this.clock = clock;
    }

    /**
     * 占位：通过则返回凭据，不通过直接抛 429。**占位与计数在同一步**——
     * 先判断再计数的话，两个并发请求会同时看到同一个「还剩一轮」。
     */
    public QuotaLease acquire(long userId) {
        int used = turnsToday(userId);
        if (used >= properties.turnsPerDay()) {
            throw new QuotaException(
                    ErrorCode.RAG_DAILY_QUOTA_EXCEEDED,
                    "今日额度已用完（" + used + "/" + properties.turnsPerDay() + "），明天再来",
                    secondsUntilTomorrow());
        }

        AtomicInteger slot = inFlight.computeIfAbsent(userId, key -> new AtomicInteger());
        if (slot.incrementAndGet() > properties.concurrent()) {
            slot.decrementAndGet();
            throw new QuotaException(
                    ErrorCode.RAG_CONCURRENT_QUERY,
                    "上一个回答还在生成，等它结束再问",
                    5);
        }

        try {
            reserveMinute(userId);
            usage.bump(today(), userId);
        } catch (RuntimeException failure) {
            // 占位没成功就不能留下并发位：漏掉的话那个账户再也问不出下一句（没有超时回收）
            slot.decrementAndGet();
            throw failure;
        }
        return new QuotaLease(userId, today());
    }

    /**
     * 一轮结束，归还并发位。**这一步无论如何都要走到**（拦截器的 `afterCompletion`），
     * 漏了它那个账户就会永远卡在「上一个回答还在生成」。
     */
    public void release(QuotaLease lease) {
        if (lease == null) {
            return;
        }
        AtomicInteger slot = inFlight.get(lease.userId());
        if (slot != null) {
            slot.decrementAndGet();
        }
    }

    /**
     * 退还日额度：provider 故障（5xx）那一轮不该吃掉面试账户的额度。
     *
     * <p>只退日额度、不退分钟窗口——窗口是一分钟内的滑动计数，为一次故障去挪它
     * 换不来任何东西，而「退还」这件事用一个幂等闸门挡住重复调用（见 {@link QuotaLease}）。
     */
    public void refund(QuotaLease lease) {
        if (lease == null || !lease.claimRefund()) {
            return;
        }
        usage.refund(lease.day(), lease.userId());
    }

    /** 今天已经问了几轮。审计与提示都用它。 */
    public int turnsToday(long userId) {
        Integer turns = usage.turns(today(), userId);
        return turns == null ? 0 : turns;
    }

    private void reserveMinute(long userId) {
        long now = clock.millis();
        Deque<Long> window = minuteWindows.computeIfAbsent(userId, key -> new ArrayDeque<>());
        synchronized (window) {
            while (!window.isEmpty() && now - window.peekFirst() >= MINUTE_MS) {
                window.pollFirst();
            }
            if (window.size() >= properties.turnsPerMinute()) {
                long waitSeconds = Math.max(1, (window.peekFirst() + MINUTE_MS - now + 999) / 1000);
                throw new QuotaException(
                        ErrorCode.RAG_RATE_LIMITED,
                        "问得太快了（限 " + properties.turnsPerMinute() + " 轮/分），" + waitSeconds + " 秒后再试",
                        waitSeconds);
            }
            window.addLast(now);
        }
    }

    private String today() {
        return LocalDate.now(clock).toString();
    }

    /** 到本地时区的下一个零点还有多少秒——日额度的 `Retry-After`。 */
    private long secondsUntilTomorrow() {
        ZonedDateTime now = ZonedDateTime.now(clock);
        ZonedDateTime midnight = now.toLocalDate().plusDays(1).atStartOfDay(now.getZone());
        return Math.max(1, Duration.between(now, midnight).toSeconds());
    }
}
