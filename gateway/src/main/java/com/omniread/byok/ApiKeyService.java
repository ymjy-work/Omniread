package com.omniread.byok;

import java.util.List;

import com.omniread.byok.model.ApiKeySaveDTO;
import com.omniread.byok.model.ApiKeyVO;
import com.omniread.byok.model.UserApiKeyEntity;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Timestamps;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ApiKeyService {

	private final ApiKeyMapper apiKeyMapper;
	private final CryptoService cryptoService;

	public ApiKeyService(ApiKeyMapper apiKeyMapper, CryptoService cryptoService) {
		this.apiKeyMapper = apiKeyMapper;
		this.cryptoService = cryptoService;
	}

	@Transactional
	public ApiKeyVO save(long userId, ApiKeySaveDTO request) {
		requireValidProvider(request.provider());
		UserApiKeyEntity entity = new UserApiKeyEntity();
		entity.setUserId(userId);
		entity.setProvider(request.provider());
		entity.setEncryptedKey(cryptoService.encrypt(request.key()));
		entity.setKeyMask(mask(request.key()));
		entity.setCreatedAt(Timestamps.now());
		apiKeyMapper.upsert(entity);
		return ApiKeyVO.of(apiKeyMapper.findByUserAndProvider(userId, request.provider()));
	}

	public List<ApiKeyVO> list(long userId) {
		return apiKeyMapper.listByUser(userId).stream().map(ApiKeyVO::of).toList();
	}

	@Transactional
	public void delete(long userId, String provider) {
		requireValidProvider(provider);
		if (apiKeyMapper.deleteByUserAndProvider(userId, provider) == 0) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "该提供商未保存 Key");
		}
	}

	/** ask byok 模式取已存 Key；不存在即业务错误。 */
	public UserApiKeyEntity requireStoredKey(long userId, String provider) {
		requireValidProvider(provider);
		UserApiKeyEntity entity = apiKeyMapper.findByUserAndProvider(userId, provider);
		if (entity == null) {
			throw new BusinessException(ErrorCode.BAD_REQUEST, "请先保存该提供商的 API Key");
		}
		return entity;
	}

	public String decryptKey(UserApiKeyEntity entity) {
		return cryptoService.decrypt(entity.getEncryptedKey());
	}

	private void requireValidProvider(String provider) {
		if (!ByokProviders.contains(provider)) {
			throw new BusinessException(ErrorCode.BAD_REQUEST,
					"provider 只能是 " + String.join("/", ByokProviders.ALL));
		}
	}

	private static String mask(String key) {
		if (key.length() < 8) {
			return "***";
		}
		return key.substring(0, 3) + "…" + key.substring(key.length() - 4);
	}
}
