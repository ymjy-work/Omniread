package com.omniread.billing;

import java.util.List;

import com.omniread.auth.AuthInterceptor;
import com.omniread.billing.model.AccountVO;
import com.omniread.billing.model.PlanCatalogEntity;
import com.omniread.billing.model.PlanPurchaseDTO;
import com.omniread.common.Result;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

	private final AccountService accountService;

	public AccountController(AccountService accountService) {
		this.accountService = accountService;
	}

	@GetMapping("/api/plans")
	public Result<List<PlanCatalogEntity>> listPlans() {
		return Result.ok(accountService.listPlans());
	}

	@GetMapping("/api/me/account")
	public Result<AccountVO> getAccount(@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId) {
		return Result.ok(accountService.getAccount(userId));
	}

	@PostMapping("/api/me/plan")
	public Result<AccountVO> purchase(@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId,
			@Valid @RequestBody PlanPurchaseDTO request) {
		return Result.ok(accountService.purchase(userId, request.plan()));
	}
}
