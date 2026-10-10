package com.omniread.backend.web;

import com.omniread.backend.user.AuthCookies;
import com.omniread.backend.user.AuthProperties;
import com.omniread.backend.user.AuthService;
import com.omniread.backend.user.AuthenticatedUser;
import com.omniread.backend.user.CurrentUser;
import com.omniread.backend.user.LoginRequest;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import java.time.Duration;
import java.time.Instant;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 登录 / 退出 / 当前账户。
 *
 * <p>**响应体里永远没有 token**：它只出现在 `Set-Cookie` 里。前端拿不到，
 * 也就不可能把它写进 localStorage 或随手贴进某个日志。
 */
@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final AuthService authService;
    private final AuthProperties properties;

    public AuthController(AuthService authService, AuthProperties properties) {
        this.authService = authService;
        this.properties = properties;
    }

    @PostMapping("/login")
    public ResponseEntity<CurrentUser> login(@RequestBody @Valid LoginRequest body) {
        AuthService.IssuedSession session = authService.login(body.username(), body.password());

        // Max-Age 由 expiresAt 反推，不在这里再算一次 TTL：两处各算一次必然差几毫秒，
        // 而差值的方向决定了是「cookie 先死」还是「cookie 还活着但服务端已判过期」。
        Duration maxAge = Duration.between(Instant.now(), session.expiresAt());
        ResponseCookie cookie = AuthCookies.issue(session.token(), maxAge, properties.cookieSecure());

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body(new CurrentUser(session.username(), session.expiresAt()));
    }

    /**
     * 退出：删掉服务端那一条登录会话行，并清 cookie。
     *
     * <p>走到这里时 cookie 一定是有效的（本端点也在登录门内），所以「没登录时返回 401」
     * 由拦截器负责，这里只管撤销。204 不带体。
     */
    @PostMapping("/logout")
    public ResponseEntity<Void> logout(HttpServletRequest request) {
        authService.logout(AuthCookies.read(request));
        ResponseCookie cleared = AuthCookies.clear(properties.cookieSecure());
        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, cleared.toString())
                .build();
    }

    /** 前端启动时用它判断登录态。未登录由拦截器给 401，不走「200 + null」。 */
    @GetMapping("/me")
    public CurrentUser me(@RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        return new CurrentUser(user.username(), user.expiresAt());
    }
}
