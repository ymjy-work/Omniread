package com.omniread.auth;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Timestamps;
import org.springframework.stereotype.Service;

/** 登录限流：同一用户名或 IP 在窗口内失败次数达到上限即拒绝。 */
@Service
public class LoginThrottle {

	private static final int MAX_FAILURES = 10;
	private static final Duration WINDOW = Duration.ofMinutes(10);
	private static final DateTimeFormatter FORMAT =
			DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC);

	private final AuthMapper authMapper;

	public LoginThrottle(AuthMapper authMapper) {
		this.authMapper = authMapper;
	}

	public void check(String username, String ip) {
		String since = FORMAT.format(Instant.now().minus(WINDOW));
		if (authMapper.countRecentFailures(username, ip, since) >= MAX_FAILURES) {
			throw new BusinessException(ErrorCode.TOO_MANY_REQUESTS);
		}
	}

	public void record(String username, String ip, boolean success) {
		authMapper.insertLoginAttempt(username, ip, success, Timestamps.now());
	}
}
