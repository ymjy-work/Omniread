package com.omniread.admin;

import com.omniread.admin.model.AdminAuthResponseVO;
import com.omniread.auth.AuthMapper;
import com.omniread.auth.LoginThrottle;
import com.omniread.auth.TokenService;
import com.omniread.auth.model.LoginRequestDTO;
import com.omniread.auth.model.UserEntity;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

/** 管理员后台登录：只允许 role=admin 账号，令牌与用户体系共用同一 JWT 签发。 */
@Service
public class AdminAuthService {

	private final AuthMapper authMapper;
	private final LoginThrottle loginThrottle;
	private final TokenService tokenService;
	private final PasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

	public AdminAuthService(AuthMapper authMapper, LoginThrottle loginThrottle,
			TokenService tokenService) {
		this.authMapper = authMapper;
		this.loginThrottle = loginThrottle;
		this.tokenService = tokenService;
	}

	public AdminAuthResponseVO login(LoginRequestDTO request, String ip) {
		loginThrottle.check(request.username(), ip);
		UserEntity user = authMapper.findUserByUsername(request.username());
		if (user == null || !passwordEncoder.matches(request.password(), user.getPasswordHash())) {
			loginThrottle.record(request.username(), ip, false);
			throw new BusinessException(ErrorCode.UNAUTHORIZED, "用户名或密码错误");
		}
		if (!"admin".equals(user.getRole())) {
			loginThrottle.record(request.username(), ip, true);
			throw new BusinessException(ErrorCode.FORBIDDEN, "该账号不是管理员");
		}
		loginThrottle.record(request.username(), ip, true);
		String token = tokenService.issue(user.getId(), user.getUsername(), user.getRole());
		return AdminAuthResponseVO.of(token, user);
	}

	public void logout(TokenService.Claims claims) {
		tokenService.revoke(claims);
	}
}
