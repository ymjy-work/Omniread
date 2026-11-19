package com.omniread.byok;

import java.util.List;

import com.omniread.auth.AuthInterceptor;
import com.omniread.byok.model.ApiKeySaveDTO;
import com.omniread.byok.model.ApiKeyVO;
import com.omniread.common.Result;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/me/api-keys")
public class ApiKeyController {

	private final ApiKeyService apiKeyService;

	public ApiKeyController(ApiKeyService apiKeyService) {
		this.apiKeyService = apiKeyService;
	}

	@GetMapping
	public Result<List<ApiKeyVO>> list(@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId) {
		return Result.ok(apiKeyService.list(userId));
	}

	@PostMapping
	public Result<ApiKeyVO> save(@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId,
			@Valid @RequestBody ApiKeySaveDTO request) {
		return Result.ok(apiKeyService.save(userId, request));
	}

	@DeleteMapping
	public Result<Void> delete(@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId,
			@RequestParam String provider) {
		apiKeyService.delete(userId, provider);
		return Result.ok();
	}
}
