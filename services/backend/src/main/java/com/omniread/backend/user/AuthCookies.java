package com.omniread.backend.user;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import java.time.Duration;
import org.springframework.http.ResponseCookie;

/**
 * 登录 cookie 的唯一读写点：种下、读取、清除都经过这里，属性就只会有一份定义。
 *
 * <p>名字与外部契约的 `securitySchemes.sessionCookie.name` 是同一个字符串——它在契约里
 * 是写死的，所以这里也是常量而不是配置项。分散成两处定义，改了一处就会变成
 * 「登录成功但没有登录态」，而两边的日志都正常。
 *
 * <p>`HttpOnly` 不可配：token 读不到是这套方案的前提（读不到就写不进 localStorage、
 * 也带不走）。`SameSite=Strict` 是 CSRF 的第一道防线。
 */
public final class AuthCookies {

    public static final String NAME = "omniread_session";

    private static final String PATH = "/";

    private static final String SAME_SITE = "Strict";

    private AuthCookies() {
    }

    /** 没带 cookie、值是空串都当「没有」：空值不是凭据，不必拿去查库。 */
    public static String read(HttpServletRequest request) {
        Cookie[] cookies = request.getCookies();
        if (cookies == null) {
            return null;
        }
        for (Cookie cookie : cookies) {
            if (NAME.equals(cookie.getName())) {
                String value = cookie.getValue();
                return value == null || value.isBlank() ? null : value;
            }
        }
        return null;
    }

    /**
     * 种 cookie。`maxAge` 由调用方按**同一个** `expires_at` 算出来
     * （`Duration.between(now, expiresAt)`），不在这里自己加一遍 TTL——
     * 两处各算一次必然漂移，而漂移的表现是「cookie 还在但服务端已经判过期」。
     */
    public static ResponseCookie issue(String token, Duration maxAge, boolean secure) {
        return base(token, secure).maxAge(maxAge).build();
    }

    /** 清除：maxAge=0 让浏览器立刻丢掉它，属性与种下时一致，否则删的是另一个 cookie。 */
    public static ResponseCookie clear(boolean secure) {
        return base("", secure).maxAge(Duration.ZERO).build();
    }

    private static ResponseCookie.ResponseCookieBuilder base(String value, boolean secure) {
        return ResponseCookie.from(NAME, value)
                .httpOnly(true)
                .secure(secure)
                .sameSite(SAME_SITE)
                .path(PATH);
    }
}
