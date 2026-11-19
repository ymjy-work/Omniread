package com.omniread.catalog;

import java.util.ArrayList;
import java.util.List;

import com.omniread.auth.AuthMapper;
import com.omniread.auth.model.UserEntity;
import com.omniread.billing.AccountService;
import com.omniread.byok.ByokProviders;
import com.omniread.catalog.model.ModelCatalogEntity;
import com.omniread.catalog.model.ModelVO;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import org.springframework.stereotype.Service;

@Service
public class ModelService {

	private final ModelCatalogMapper modelCatalogMapper;
	private final AuthMapper authMapper;
	private final AccountService accountService;

	public ModelService(ModelCatalogMapper modelCatalogMapper, AuthMapper authMapper,
			AccountService accountService) {
		this.modelCatalogMapper = modelCatalogMapper;
		this.authMapper = authMapper;
		this.accountService = accountService;
	}

	/** platform：当前 plan 可用的目录模型；free 档不可选模型，返回空。 */
	public List<ModelVO> platformModels(long userId, String provider) {
		UserEntity user = authMapper.findUserById(userId);
		if (user == null) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "用户不存在");
		}
		accountService.ensureCurrent(user);
		if ("free".equals(user.getPlan())) {
			return List.of();
		}
		List<ModelCatalogEntity> models = modelCatalogMapper.listForPlan(user.getPlan());
		if (provider != null && !provider.isBlank()) {
			models = models.stream().filter(m -> provider.equals(m.getProvider())).toList();
		}
		return models.stream().map(ModelVO::of).toList();
	}

	/** byok：固定提供商清单 + 建议模型（可空）；实际模型允许自由填写。 */
	public List<ByokProviderVO> byokProviders(String provider) {
		if (provider != null && !provider.isBlank() && !ByokProviders.contains(provider)) {
			throw new BusinessException(ErrorCode.BAD_REQUEST,
					"provider 只能是 " + String.join("/", ByokProviders.ALL));
		}
		List<ByokProviderVO> result = new ArrayList<>();
		for (String item : ByokProviders.ALL) {
			if (provider != null && !provider.isBlank() && !provider.equals(item)) {
				continue;
			}
			List<String> suggestions = "bailian".equals(item)
					? modelCatalogMapper.listByProvider(item).stream()
							.map(ModelCatalogEntity::getModel).toList()
					: List.of();
			result.add(new ByokProviderVO(item, suggestions));
		}
		return result;
	}

	public record ByokProviderVO(String provider, List<String> models) {
	}
}
