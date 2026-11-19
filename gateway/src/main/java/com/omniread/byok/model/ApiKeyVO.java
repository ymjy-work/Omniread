package com.omniread.byok.model;

import com.fasterxml.jackson.annotation.JsonInclude;

/** 只暴露掩码，绝不返回明文或密文。 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiKeyVO(String provider, String keyMask, String status, String createdAt,
		String lastCheckedAt) {

	public static ApiKeyVO of(UserApiKeyEntity entity) {
		return new ApiKeyVO(entity.getProvider(), entity.getKeyMask(), entity.getStatus(),
				entity.getCreatedAt(), entity.getLastCheckedAt());
	}
}
