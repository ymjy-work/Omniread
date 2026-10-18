package com.omniread.backend.user;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 清理过期的登录会话行：**启动时一次、之后每日一次**。
 *
 * <p>不清理也不影响正确性——{@link AuthService#resolve} 自己会判过期——清的是磁盘上
 * 越积越多的废行。所以定时任务排在凌晨四点十七分这种没有含义的时刻，
 * 它错过一次也无所谓，不必为它做补偿。
 *
 * <p>启动那次挂在 {@link ApplicationReadyEvent} 而不是做成 {@code ApplicationRunner}：
 * 后者与建表的 {@code SchemaInitializer} 是两个平级的 runner，谁先谁后没有保证，
 * 实测就是清理先跑、库还没建，启动直接失败在 `no such table: auth_sessions`。
 * 「就绪之后再清」在语义上也更准——它本来就不该是启动路径的一部分。
 */
@Component
public class AuthSessionJanitor {

    private static final Logger log = LoggerFactory.getLogger(AuthSessionJanitor.class);

    private final AuthService authService;

    public AuthSessionJanitor(AuthService authService) {
        this.authService = authService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        purge();
    }

    @Scheduled(cron = "0 17 4 * * *")
    public void purge() {
        int removed = authService.purgeExpired();
        if (removed > 0) {
            log.info("清理过期的登录会话 {} 条", removed);
        }
    }
}
