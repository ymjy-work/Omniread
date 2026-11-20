package com.omniread.auth;

import com.omniread.auth.model.AuthResponseVO;
import com.omniread.auth.model.LoginRequestDTO;
import com.omniread.auth.model.RegisterRequestDTO;
import com.omniread.auth.model.UserEntity;
import com.omniread.billing.LedgerMapper;
import com.omniread.billing.PlanCatalogMapper;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Timestamps;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

	private final AuthMapper authMapper;
	private final LoginThrottle loginThrottle;
	private final TokenService tokenService;
	private final PlanCatalogMapper planCatalogMapper;
	private final LedgerMapper ledgerMapper;
	private final PasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

	public AuthService(AuthMapper authMapper, LoginThrottle loginThrottle, TokenService tokenService,
			PlanCatalogMapper planCatalogMapper, LedgerMapper ledgerMapper) {
		this.authMapper = authMapper;
		this.loginThrottle = loginThrottle;
		this.tokenService = tokenService;
		this.planCatalogMapper = planCatalogMapper;
		this.ledgerMapper = ledgerMapper;
	}

	public AuthResponseVO login(LoginRequestDTO request, String ip) {
		loginThrottle.check(request.username(), ip);
		UserEntity user = authMapper.findUserByUsername(request.username());
		if (user == null || !passwordEncoder.matches(request.password(), user.getPasswordHash())) {
			loginThrottle.record(request.username(), ip, false);
			throw new BusinessException(ErrorCode.UNAUTHORIZED, "用户名或密码错误");
		}
		loginThrottle.record(request.username(), ip, true);
		String token = tokenService.issue(user.getId(), user.getUsername(), user.getRole());
		return new AuthResponseVO(token,
				new AuthResponseVO.UserVO(user.getId(), user.getUsername(), user.getDisplayName()));
	}

	/** 公开注册：固定 user/free/100 积分/0 余额，忽略请求中除 username/password/displayName 外的字段。 */
	@Transactional
	public AuthResponseVO register(RegisterRequestDTO request) {
		if (authMapper.findUserByUsername(request.username()) != null) {
			throw new BusinessException(ErrorCode.BAD_REQUEST, "用户名已存在");
		}
		String now = Timestamps.now();
		UserEntity user = new UserEntity();
		user.setUsername(request.username());
		user.setPasswordHash(passwordEncoder.encode(request.password()));
		user.setDisplayName(request.displayName() == null || request.displayName().isBlank()
				? request.username() : request.displayName());
		user.setCreatedAt(now);
		user.setRole("user");
		user.setPlan("free");
		user.setCredits(100L);
		user.setPlanStartedAt(now);
		user.setPlanExpiresAt(Timestamps.plusDays(now,
				planCatalogMapper.findByCode("free").getDurationDays()));
		user.setBalance(0.0);
		authMapper.insertUser(user);
		ledgerMapper.insertCredit(user.getId(), "init", 100, 100, "注册初始积分", now);
		String token = tokenService.issue(user.getId(), user.getUsername(), user.getRole());
		return new AuthResponseVO(token,
				new AuthResponseVO.UserVO(user.getId(), user.getUsername(), user.getDisplayName()));
	}

	/** 注销当前 token；按 jti 进程内吊销，重启后清空。 */
	public void logout(TokenService.Claims claims) {
		tokenService.revoke(claims);
	}
}
