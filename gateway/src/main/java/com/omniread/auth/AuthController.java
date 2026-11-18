package com.omniread.auth;

import com.omniread.auth.model.AuthResponseVO;
import com.omniread.auth.model.LoginRequestDTO;
import com.omniread.common.Result;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

	private final AuthService authService;

	public AuthController(AuthService authService) {
		this.authService = authService;
	}

	@PostMapping("/login")
	public Result<AuthResponseVO> login(@Valid @RequestBody LoginRequestDTO request,
			HttpServletRequest servletRequest) {
		return Result.ok(authService.login(request, servletRequest.getRemoteAddr()));
	}
}
