package com.omniread.byok;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/** AES-GCM 加解密用户 API Key。存储格式 base64(iv[12] + ciphertext + tag)。主密钥缺失时启动失败。 */
@Service
public class CryptoService {

	private static final int IV_LENGTH = 12;
	private static final int TAG_BITS = 128;

	private final SecretKeySpec key;
	private final SecureRandom random = new SecureRandom();

	public CryptoService(@Value("${omniread.crypto.key:}") String base64Key) {
		if (base64Key == null || base64Key.isBlank()) {
			throw new IllegalStateException(
					"omniread.crypto.key 缺失：请把 src/main/resources/application-local.yml.example "
							+ "复制为同目录 application-local.yml 并填写 base64 编码的 32 字节主密钥");
		}
		byte[] decoded;
		try {
			decoded = Base64.getDecoder().decode(base64Key.trim());
		}
		catch (IllegalArgumentException e) {
			throw new IllegalStateException("omniread.crypto.key 必须是 base64 编码");
		}
		if (decoded.length != 32) {
			throw new IllegalStateException("omniread.crypto.key base64 解码后必须为 32 字节");
		}
		this.key = new SecretKeySpec(decoded, "AES");
	}

	public String encrypt(String plaintext) {
		try {
			byte[] iv = new byte[IV_LENGTH];
			random.nextBytes(iv);
			Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
			cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
			byte[] ciphertext = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));
			byte[] combined = new byte[iv.length + ciphertext.length];
			System.arraycopy(iv, 0, combined, 0, iv.length);
			System.arraycopy(ciphertext, 0, combined, iv.length, ciphertext.length);
			return Base64.getEncoder().encodeToString(combined);
		}
		catch (GeneralSecurityException e) {
			throw new BusinessException(ErrorCode.INTERNAL_ERROR, "密钥加密失败");
		}
	}

	public String decrypt(String stored) {
		try {
			byte[] combined = Base64.getDecoder().decode(stored);
			Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
			cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, combined, 0, IV_LENGTH));
			byte[] plaintext = cipher.doFinal(combined, IV_LENGTH, combined.length - IV_LENGTH);
			return new String(plaintext, StandardCharsets.UTF_8);
		}
		catch (GeneralSecurityException | IllegalArgumentException e) {
			throw new BusinessException(ErrorCode.INTERNAL_ERROR, "密钥解密失败");
		}
	}
}
