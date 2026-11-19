package com.omniread.byok.model;

/** user_api_key 表行；encrypted_key 只在进程内解密使用，不对外。 */
public class UserApiKeyEntity {

	private Long id;
	private Long userId;
	private String provider;
	private String encryptedKey;
	private String keyMask;
	private String status;
	private String createdAt;
	private String lastCheckedAt;

	public Long getId() {
		return id;
	}

	public void setId(Long id) {
		this.id = id;
	}

	public Long getUserId() {
		return userId;
	}

	public void setUserId(Long userId) {
		this.userId = userId;
	}

	public String getProvider() {
		return provider;
	}

	public void setProvider(String provider) {
		this.provider = provider;
	}

	public String getEncryptedKey() {
		return encryptedKey;
	}

	public void setEncryptedKey(String encryptedKey) {
		this.encryptedKey = encryptedKey;
	}

	public String getKeyMask() {
		return keyMask;
	}

	public void setKeyMask(String keyMask) {
		this.keyMask = keyMask;
	}

	public String getStatus() {
		return status;
	}

	public void setStatus(String status) {
		this.status = status;
	}

	public String getCreatedAt() {
		return createdAt;
	}

	public void setCreatedAt(String createdAt) {
		this.createdAt = createdAt;
	}

	public String getLastCheckedAt() {
		return lastCheckedAt;
	}

	public void setLastCheckedAt(String lastCheckedAt) {
		this.lastCheckedAt = lastCheckedAt;
	}
}
