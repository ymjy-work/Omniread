package com.omniread.auth;

import com.omniread.auth.model.AuthResponseVO;
import com.omniread.auth.model.LoginRequestDTO;
import com.omniread.auth.model.UserEntity;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

	private final AuthMapper authMapper;
	private final LoginThrottle loginThrottle;
	private final TokenService tokenService;
	private final PasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

	public AuthService(AuthMapper authMapper, LoginThrottle loginThrottle, TokenService tokenService) {
		this.authMapper = authMapper;
		this.loginThrottle = loginThrottle;
		this.tokenService = tokenService;
	}

	public AuthResponseVO login(LoginRequestDTO request, String ip) {
		loginThrottle.check(request.username(), ip);
		UserEntity user = authMapper.findUserByUsername(request.username());
		if (user == null || !passwordEncoder.matches(request.password(), user.getPasswordHash())) {
			loginThrottle.record(request.username(), ip, false);
			throw new BusinessException(ErrorCode.UNAUTHORIZED, "用户名或密码错误");
		}
		loginThrottle.record(request.username(), ip, true);
		String token = tokenService.issue(user.getId(), user.getUsername());
		return new AuthResponseVO(token,
				new AuthResponseVO.UserVO(user.getId(), user.getUsername(), user.getDisplayName()));
	}
}
