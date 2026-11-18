package com.omniread.auth;

import com.omniread.auth.model.UserEntity;
import com.omniread.common.Timestamps;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

/** 启动时按 application-local.yml 的 omniread.admin 配置创建管理员；不开放注册。 */
@Component
@Order(1)
public class AdminInitializer implements ApplicationRunner {

	private static final Logger log = LoggerFactory.getLogger(AdminInitializer.class);

	private final AuthMapper authMapper;
	private final String username;
	private final String password;

	public AdminInitializer(AuthMapper authMapper,
			@Value("${omniread.admin.username:}") String username,
			@Value("${omniread.admin.password:}") String password) {
		this.authMapper = authMapper;
		this.username = username;
		this.password = password;
	}

	@Override
	public void run(ApplicationArguments args) {
		if (username == null || username.isBlank() || password == null || password.isBlank()) {
			log.warn("omniread.admin.username/password 未配置，跳过管理员创建（将无法登录）");
			return;
		}
		if (authMapper.findUserByUsername(username) != null) {
			return;
		}
		UserEntity user = new UserEntity();
		user.setUsername(username);
		user.setPasswordHash(new BCryptPasswordEncoder().encode(password));
		user.setDisplayName(username);
		user.setCreatedAt(Timestamps.now());
		authMapper.insertUser(user);
		log.info("已创建管理员用户 {}", username);
	}
}
