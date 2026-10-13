package com.omniread.backend.error;

/**
 * 超限（契约里的四个 429）。除了 code 还带一个 **`Retry-After`（秒）**——
 * 四种超限的处置不同，而「还要等多久」是唯一能直接告诉客户端的那部分：
 * 分钟限流等一下、日额度要等明天、并发要等上一个回答结束、登录锁要换来源 IP。
 *
 * <p>秒数在这里就夹到「至少 1」：`Retry-After: 0` 的意思是「立刻重试」，
 * 而那正是我们不想让它做的事。
 */
public class QuotaException extends RagException {

    private final long retryAfterSeconds;

    public QuotaException(ErrorCode code, String message, long retryAfterSeconds) {
        super(code, message);
        this.retryAfterSeconds = Math.max(1, retryAfterSeconds);
    }

    public long retryAfterSeconds() {
        return retryAfterSeconds;
    }
}
