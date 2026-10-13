package com.omniread.backend.quota;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;

/**
 * 只拨「现在」的时钟。时区固定由调用方给（测试里一律 UTC，免得跟着机器时区变）。
 *
 * <p>跨日额度恢复、分钟窗口过期、登录锁到期——这三件事真等要等 24 小时，
 * 而它们恰恰是最容易写错的地方（写错的表现是「一直锁着」或者「根本没锁」）。
 */
final class MutableClock extends Clock {

    private final ZoneId zone;

    private Instant now;

    MutableClock(Instant now, ZoneId zone) {
        this.now = now;
        this.zone = zone;
    }

    void advance(Duration amount) {
        now = now.plus(amount);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId other) {
        return new MutableClock(now, other);
    }

    @Override
    public Instant instant() {
        return now;
    }
}
