package com.omniread.backend.web;

import com.omniread.backend.audit.AuditLog;
import com.omniread.backend.quota.QuotaLease;
import com.omniread.backend.quota.QuotaProperties;
import com.omniread.backend.quota.QuotaService;
import com.omniread.backend.user.AuthenticatedUser;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * 问答端点的额度闸门：进来先占位（不通过就是 429），收尾时还并发位、必要时退还日额度。
 *
 * <p>挂成拦截器而不是写进控制器：两个问答入口（同步 / 流式）都要它，而写两处
 * 迟早只改一处。它只挂在问答路径上，其余接口（书目录、会话增删）不受限——
 * 配额的口径是「一轮 = 一次问答请求」。
 *
 * <p>退还的判据是**响应状态 ≥ 500**，不是「有没有异常」：异常被
 * `@RestControllerAdvice` 处理掉之后，`afterCompletion` 拿到的 `ex` 是 null，
 * 而 502/503/504 还留在响应上。流式路径更特殊——它在开流时就把状态写成了 200，
 * 中途的 provider 故障以 `error` 帧表达，那一侧的退还在控制器里补
 * （看 {@code AnswerStreamRecorder.failed()}）。
 */
@Component
public class QuotaInterceptor implements HandlerInterceptor {

    /** 本轮额度的凭据放在请求属性上的键（控制器退还时取它）。 */
    public static final String LEASE_ATTRIBUTE = "omniread.quota.lease";

    private final QuotaService quota;

    private final QuotaProperties properties;

    private final AuditLog audit;

    public QuotaInterceptor(QuotaService quota, QuotaProperties properties, AuditLog audit) {
        this.quota = quota;
        this.properties = properties;
        this.audit = audit;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        Object attribute = request.getAttribute(AuthInterceptor.USER_ATTRIBUTE);
        if (!(attribute instanceof AuthenticatedUser user)) {
            // 未登录的请求由登录门先拦下（它挂在前面）。走到这里说明注册顺序被改过了。
            return true;
        }
        QuotaLease lease = quota.acquire(user.userId());
        request.setAttribute(LEASE_ATTRIBUTE, lease);
        audit.query(user.username(), quota.turnsToday(user.userId()), properties.turnsPerDay());
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler,
            Exception failure) {
        QuotaLease lease = leaseOf(request);
        if (lease == null) {
            return;
        }
        quota.release(lease);
        if (response.getStatus() >= 500) {
            quota.refund(lease);
        }
    }

    /** 本轮凭据；没经过闸门（或闸门没放行）时是 null。控制器补退还时也用它。 */
    public static QuotaLease leaseOf(HttpServletRequest request) {
        return request.getAttribute(LEASE_ATTRIBUTE) instanceof QuotaLease lease ? lease : null;
    }
}
