package com.omniread.backend.web;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import com.omniread.backend.user.AuthCookies;
import com.omniread.backend.user.AuthService;
import com.omniread.backend.user.AuthenticatedUser;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Set;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * 登录门：`/api/v1/**` 未登录一律 401，健康检查与登录除外（例外名单在
 * {@code WebMvcConfig} 的注册处，和路径模式写在一起）。
 *
 * <p>拒绝时抛 {@link RagException} 而不是自己写响应：DispatcherServlet 会把
 * `preHandle` 抛出的异常交给 {@code @RestControllerAdvice}，于是 401 的响应体与其它错误
 * 是同一个 {request_id, code, message} 形状。自己写一份就会成为第二个形状。
 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

    /** 当前账户放在请求属性上的键；控制器用 `@RequestAttribute` 取（同 {@link RequestIds}）。 */
    public static final String USER_ATTRIBUTE = "omniread.auth.user";

    /** 写操作必须带的头。前端统一带，值不参与判断。 */
    public static final String CSRF_HEADER = "X-Omniread-Csrf";

    private static final Set<String> SAFE_METHODS = Set.of("GET", "HEAD", "OPTIONS");

    private final AuthService authService;

    public AuthInterceptor(AuthService authService) {
        this.authService = authService;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        // 顺序是「先身份、后 CSRF」而不是反过来：反过来的话，一个既没登录、也没带头的 POST
        // 会拿到 403，而部署验收写的是「未登录请求 /api/v1/* 均返回 401，逐个验证」——
        // 一条能被机械验证的规则，比一个更「正确」的优先级顺序值钱。
        AuthenticatedUser user = authService
                .resolve(AuthCookies.read(request))
                .orElseThrow(() -> new RagException(ErrorCode.RAG_UNAUTHENTICATED, "未登录或登录已过期"));

        // SameSite=Strict 之外再加一道：要求发起方能设置自定义头，而跨站页面做不到
        // （要发这样的请求就绕不开 CORS 预检，而预检不会带上 cookie）。
        // 两道都在，才不必引 Spring Security 的过滤器链（java-依赖与选型 §三）。
        if (!SAFE_METHODS.contains(request.getMethod()) && request.getHeader(CSRF_HEADER) == null) {
            throw new RagException(ErrorCode.RAG_FORBIDDEN, "缺少 " + CSRF_HEADER + " 请求头");
        }

        request.setAttribute(USER_ATTRIBUTE, user);
        return true;
    }
}
