package com.omniread.backend.user;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 删除过期账户：**启动时一次、之后每日一次**。有效期关闭时整个类不做事。
 *
 * <p>与 {@link AuthSessionJanitor} 分工不同：那个删的是登录会话行，账户还在；
 * 这个删的是账户本身，连同它的会话、消息、进度、用量（子表都是 {@code ON DELETE CASCADE}）。
 * 账户是一次性的演示账户，删掉之后**账户名释放、可以重新发放**。
 *
 * <p>**不能只靠这个定时任务**：它一天才跑一次，过期账户在这之间仍能登录。
 * 登录与解析登录态两处都各自判过期（{@link AccountExpiry}），这里只是把废行收掉。
 *
 * <p>挂在 {@link ApplicationReadyEvent} 而不是 {@code ApplicationRunner}：后者与建表的
 * {@code SchemaInitializer} 平级、先后无保证，实测会先跑在「表还没建」上。
 */
@Component
public class AccountJanitor {

    private static final Logger log = LoggerFactory.getLogger(AccountJanitor.class);

    private final UserMapper userMapper;
    private final AccountExpiry expiry;

    public AccountJanitor(UserMapper userMapper, AccountExpiry expiry) {
        this.userMapper = userMapper;
        this.expiry = expiry;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        sweep();
    }

    /** 排在登录会话清理之后，两者没有依赖，分开只为日志好读。 */
    @Scheduled(cron = "0 43 4 * * *")
    public void sweep() {
        try {
            purgeExpired();
        } catch (RuntimeException ex) {
            // 清理失败不该把进程带下去：账户过期判定在请求路径上还有一道，功能不受影响。
            log.warn("清理过期账户失败：{}", ex.toString());
        }
    }

    /** 返回删掉的账户数。 */
    public int purgeExpired() {
        List<User> users = userMapper.findAll();
        int deleted = 0;
        for (User user : users) {
            if (!expiry.isExpired(user)) {
                continue;
            }
            userMapper.deleteById(user.getId());
            log.info("删除过期账户：{}（id={}）", user.getUsername(), user.getId());
            deleted++;
        }
        if (deleted > 0) {
            log.info("过期账户清理完成：共删除 {} 个", deleted);
        }
        return deleted;
    }
}
