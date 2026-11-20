package com.omniread.admin;

import com.omniread.admin.model.AdminAuthResponseVO;
import com.omniread.auth.AuthInterceptor;
import com.omniread.auth.TokenService;
import com.omniread.auth.model.LoginRequestDTO;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Result;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin/auth")
public class AdminAuthController {

	private final AdminAuthService adminAuthService;

	public AdminAuthController(AdminAuthService adminAuthService) {
		this.adminAuthService = adminAuthService;
	}

	@PostMapping("/login")
	public Result<AdminAuthResponseVO> login(@Valid @RequestBody LoginRequestDTO request,
			HttpServletRequest servletRequest) {
		return Result.ok(adminAuthService.login(request, servletRequest.getRemoteAddr()));
	}

	@PostMapping("/logout")
	public Result<Void> logout(@RequestAttribute(AuthInterceptor.USER_ROLE_ATTR) String role,
			@RequestAttribute(AuthInterceptor.CLAIMS_ATTR) TokenService.Claims claims) {
		if (!"admin".equals(role)) {
			throw new BusinessException(ErrorCode.FORBIDDEN);
		}
		adminAuthService.logout(claims);
		return Result.ok();
	}
}
