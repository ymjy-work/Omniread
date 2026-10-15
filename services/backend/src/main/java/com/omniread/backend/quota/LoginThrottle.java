package com.omniread.backend.quota;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.QuotaException;
import java.time.Clock;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * 登录失败按 **IP** 限次：窗口内失败到次数就锁一段时间（`docs/方案.md（配额与限流一节）` §二）。
 * 其余三项都按账户计，只有它按 IP——猜口令的人还没有账户，而锁账户等于让攻击者
 * 用几次失败把别人的账户锁死。
 *
 * <p>状态全在内存：单实例、且重启之后「谁失败过几次」本来就不值得留。
 * 成功一次就清空该 IP 的记录——那说明它就是本人，之前几次是手误。
 */
@Component
public class LoginThrottle {

    private static final class Attempts {
        /** 窗口内的失败时刻（ms） */
        private final Deque<Long> failures = new ArrayDeque<>();
        /** 锁到这个时刻为止；0 = 没锁 */
        private long lockedUntil;
    }

    private final Map<String, Attempts> byIp = new ConcurrentHashMap<>();

    private final QuotaProperties properties;

    private final Clock clock;

    public LoginThrottle(QuotaProperties properties, Clock clock) {
        this.properties = properties;
        this.clock = clock;
    }

    /** 尝试登录之前调：锁着就直接 429，连口令都不必验。 */
    public void check(String ip) {
        Attempts attempts = byIp.get(ip);
        if (attempts == null) {
            return;
        }
        synchronized (attempts) {
            long now = clock.millis();
            if (attempts.lockedUntil > now) {
                long waitSeconds = Math.max(1, (attempts.lockedUntil - now + 999) / 1000);
                throw new QuotaException(
                        ErrorCode.RAG_LOGIN_LOCKED,
                        "登录尝试过于频繁，请 " + waitSeconds + " 秒后再试",
                        waitSeconds);
            }
        }
    }

    /** 口令不对时记一笔；窗口内攒够次数就锁。 */
    public void onFailure(String ip) {
        long now = clock.millis();
        long windowMs = properties.loginWindow().toMillis();
        Attempts attempts = byIp.computeIfAbsent(ip, key -> new Attempts());
        synchronized (attempts) {
            while (!attempts.failures.isEmpty() && now - attempts.failures.peekFirst() >= windowMs) {
                attempts.failures.pollFirst();
            }
            attempts.failures.addLast(now);
            if (attempts.failures.size() >= properties.loginFailures()) {
                attempts.lockedUntil = now + properties.loginLock().toMillis();
            }
        }
    }

    /** 登录成功：这个 IP 之前那次「失败」是手误，清掉。 */
    public void onSuccess(String ip) {
        byIp.remove(ip);
    }
}
