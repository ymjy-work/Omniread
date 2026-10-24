package com.omniread.backend.user;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 账户与登录的配置装配。
 *
 * <p>{@code @EnableScheduling} 放在这里而不是主类上：本进程唯一的定时任务是
 * {@link AuthSessionJanitor} 的登录会话清理，把它和它需要的开关放在一起，
 * 读的人不用去别处找「还有没有别的定时任务」。
 */
@Configuration
@EnableConfigurationProperties({AuthProperties.class, AccountProperties.class})
@EnableScheduling
public class UserConfig {
}
