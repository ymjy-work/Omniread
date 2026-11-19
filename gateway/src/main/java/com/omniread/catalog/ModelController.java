package com.omniread.catalog;

import com.omniread.auth.AuthInterceptor;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Result;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ModelController {

	private final ModelService modelService;

	public ModelController(ModelService modelService) {
		this.modelService = modelService;
	}

	@GetMapping("/api/models")
	public Result<?> listModels(@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId,
			@RequestParam String mode,
			@RequestParam(required = false) String provider) {
		if ("platform".equals(mode)) {
			return Result.ok(modelService.platformModels(userId, provider));
		}
		if ("byok".equals(mode)) {
			return Result.ok(modelService.byokProviders(provider));
		}
		throw new BusinessException(ErrorCode.BAD_REQUEST, "mode 只能是 platform 或 byok");
	}
}
