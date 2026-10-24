package com.omniread.backend.user;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 演示账户的生命周期。
 *
 * <p>账户是**一次性**的：发放 → 用一阵 → 到期连同它的内容一起删掉，账户名随之释放。
 * 有效期从 {@code created_at} 起算，不另存一列——加列要动 {@code SCHEMA_VERSION}，
 * 而那道闸门对「库比代码旧」是直接拒绝启动、没有迁移路径。
 *
 * @param ttl 有效期。**{@code 0} 表示关闭**：不判过期、也不删账户。
 *     默认关闭，由部署侧显式打开——一个会删数据的定时任务不该因为漏写配置就跑起来。
 */
@ConfigurationProperties(prefix = "omniread.account")
public record AccountProperties(Duration ttl) {

    /** 关闭。测试与不依赖配置的构造点用这个。 */
    public static final AccountProperties DISABLED = new AccountProperties(Duration.ZERO);

    public AccountProperties {
        ttl = ttl == null ? Duration.ZERO : ttl;
        if (ttl.isNegative()) {
            throw new IllegalArgumentException("omniread.account.ttl 不能为负：" + ttl);
        }
    }

    public boolean enabled() {
        return !ttl.isZero();
    }
}
