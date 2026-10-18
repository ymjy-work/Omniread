package com.omniread.backend.quota;

import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 一轮问答的额度凭据：占位成功才发得出来，请求收尾时用它释放并发位、必要时退还日额度。
 *
 * <p>`day` 记的是**占位那天**而不是退还那天：跨零点还在跑的那一轮，退还该落回它占的那一行，
 * 否则今天的计数会被退成负数（有守卫兜着，但那是掩盖而不是修正）。
 *
 * <p>`refunded` 是幂等的闸门：流式路径由控制器在收到错误帧时退一次，拦截器的收尾
 * 也可能按响应状态再退一次——两条路都可能走到，而**退两次就是白送一轮**。
 *
 * <p>**这里的 `final class` 不是「静态工具类」那个意思**（对照 {@code session/Turns} 与
 * {@code web/Streams}）：它是一个**有身份的对象**，每个请求一个，只是不该被继承——
 * 额度的判定与退还都靠它自己的状态，子类改掉 `claimRefund` 就等于绕开幂等闸门。
 * 之所以是 class 而不是 record：`refunded` 必须可变，而 record 的字段是 final 的。
 */
public final class QuotaLease {

    private final long userId;

    private final String day;

    private final AtomicBoolean refunded = new AtomicBoolean(false);

    QuotaLease(long userId, String day) {
        this.userId = userId;
        this.day = day;
    }

    public long getUserId() {
        return userId;
    }

    public String getDay() {
        return day;
    }

    /** 第一次调用返回 true（本次真的退了），之后一律 false。 */
    boolean claimRefund() {
        return refunded.compareAndSet(false, true);
    }
}
