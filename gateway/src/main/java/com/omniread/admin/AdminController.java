package com.omniread.admin;

import java.util.List;

import com.omniread.admin.model.AdminUserCreateDTO;
import com.omniread.admin.model.AdminUserVO;
import com.omniread.admin.model.BalanceGrantDTO;
import com.omniread.auth.AuthInterceptor;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Result;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

	private final AdminService adminService;

	public AdminController(AdminService adminService) {
		this.adminService = adminService;
	}

	@PostMapping("/users")
	public Result<AdminUserVO> createUser(@RequestAttribute(AuthInterceptor.USER_ROLE_ATTR) String role,
			@Valid @RequestBody AdminUserCreateDTO request) {
		requireAdmin(role);
		return Result.ok(adminService.createUser(request));
	}

	@GetMapping("/users")
	public Result<List<AdminUserVO>> listUsers(
			@RequestAttribute(AuthInterceptor.USER_ROLE_ATTR) String role) {
		requireAdmin(role);
		return Result.ok(adminService.listUsers());
	}

	@PostMapping("/users/{id}/balance")
	public Result<AdminUserVO> grantBalance(@RequestAttribute(AuthInterceptor.USER_ROLE_ATTR) String role,
			@PathVariable long id, @Valid @RequestBody BalanceGrantDTO request) {
		requireAdmin(role);
		return Result.ok(adminService.grantBalance(id, request));
	}

	private void requireAdmin(String role) {
		if (!"admin".equals(role)) {
			throw new BusinessException(ErrorCode.FORBIDDEN);
		}
	}
}
