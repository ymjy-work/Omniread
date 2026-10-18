package com.omniread.backend.user;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 登录会话的两个可调参数。cookie 名**不在其中**——它由外部契约的 `securitySchemes` 钉死，
 * 是可配置就意味着可以被改成契约之外的值，而后端改了前端不会跟着改，
 * 症状是「登录成功但没有登录态」。
 *
 * @param cookieSecure 是否给 cookie 带上 `Secure`。默认 true；
 *     只有在本机用 http 调试、且浏览器不把 localhost 当可信来源时才关掉——
 *     关掉之后 cookie 会走明文，**不能进部署环境**。
 * @param sessionTtl 登录态有效期；默认 8 小时
 */
@ConfigurationProperties(prefix = "omniread.auth")
public record AuthProperties(Boolean cookieSecure, Duration sessionTtl) {

    /** 与默认配置一致；测试与不依赖配置的构造点用这个。 */
    public static final AuthProperties DEFAULT = new AuthProperties(true, Duration.ofHours(8));

    public AuthProperties {
        // 缺省即安全：配置里漏写 Secure 时按 true 处理，而不是悄悄降级成明文 cookie。
        cookieSecure = cookieSecure == null || cookieSecure;
        sessionTtl = sessionTtl == null ? DEFAULT.sessionTtl() : sessionTtl;
        if (sessionTtl.isZero() || sessionTtl.isNegative()) {
            throw new IllegalArgumentException("sessionTtl 必须为正数，收到 " + sessionTtl);
        }
    }
}
