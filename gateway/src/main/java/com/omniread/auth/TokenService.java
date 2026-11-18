package com.omniread.auth;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** HS256 JWT 的签发与校验。secret 缺失或过短时启动失败。 */
@Service
public class TokenService {

	private static final long TTL_SECONDS = 7L * 24 * 3600;
	private static final String HEADER_JSON = "{\"alg\":\"HS256\",\"typ\":\"JWT\"}";

	private final SecretKeySpec key;
	private final ObjectMapper mapper = JsonMapper.builder().build();

	public TokenService(@Value("${omniread.jwt.secret:}") String secret) {
		if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
			throw new IllegalStateException(
					"omniread.jwt.secret 缺失或少于 32 字节：请把 src/main/resources/application-local.yml.example "
							+ "复制为同目录 application-local.yml 并填写 secret");
		}
		this.key = new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
	}

	public String issue(long userId, String username) {
		long now = Instant.now().getEpochSecond();
		ObjectNode payload = mapper.createObjectNode();
		payload.put("sub", userId);
		payload.put("username", username);
		payload.put("iat", now);
		payload.put("exp", now + TTL_SECONDS);
		String signingInput = base64(HEADER_JSON.getBytes(StandardCharsets.UTF_8))
				+ "." + base64(mapper.writeValueAsBytes(payload));
		return signingInput + "." + base64(sign(signingInput));
	}

	public Claims parse(String token) {
		try {
			String[] parts = token.split("\\.");
			if (parts.length != 3) {
				throw new BusinessException(ErrorCode.UNAUTHORIZED);
			}
			byte[] expected = sign(parts[0] + "." + parts[1]);
			if (!MessageDigest.isEqual(expected, Base64.getUrlDecoder().decode(parts[2]))) {
				throw new BusinessException(ErrorCode.UNAUTHORIZED);
			}
			JsonNode payload = mapper.readTree(Base64.getUrlDecoder().decode(parts[1]));
			if (Instant.now().getEpochSecond() >= payload.get("exp").asLong()) {
				throw new BusinessException(ErrorCode.UNAUTHORIZED, "登录已过期，请重新登录");
			}
			return new Claims(payload.get("sub").asLong(), payload.get("username").asString());
		}
		catch (BusinessException e) {
			throw e;
		}
		catch (Exception e) {
			throw new BusinessException(ErrorCode.UNAUTHORIZED);
		}
	}

	private byte[] sign(String input) {
		try {
			Mac mac = Mac.getInstance("HmacSHA256");
			mac.init(key);
			return mac.doFinal(input.getBytes(StandardCharsets.UTF_8));
		}
		catch (GeneralSecurityException e) {
			throw new IllegalStateException("HmacSHA256 不可用", e);
		}
	}

	private static String base64(byte[] bytes) {
		return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
	}

	public record Claims(long userId, String username) {
	}
}
