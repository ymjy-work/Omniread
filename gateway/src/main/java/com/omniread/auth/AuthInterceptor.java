package com.omniread.auth;

import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/** 校验 Authorization: Bearer，把 userId 放进请求属性供 Controller 取用。 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

	public static final String USER_ID_ATTR = "userId";
	public static final String USER_ROLE_ATTR = "userRole";

	private final TokenService tokenService;

	public AuthInterceptor(TokenService tokenService) {
		this.tokenService = tokenService;
	}

	@Override
	public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
		if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
			return true;
		}
		String authorization = request.getHeader("Authorization");
		if (authorization == null || !authorization.startsWith("Bearer ")) {
			throw new BusinessException(ErrorCode.UNAUTHORIZED);
		}
		TokenService.Claims claims = tokenService.parse(authorization.substring(7).trim());
		request.setAttribute(USER_ID_ATTR, claims.userId());
		request.setAttribute(USER_ROLE_ATTR, claims.role() == null ? "" : claims.role());
		return true;
	}
}
