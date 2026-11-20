package com.omniread.auth;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.exceptions.TokenExpiredException;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/** HS256 JWT 的签发与校验（auth0 java-jwt）。secret 缺失或过短时启动失败。 */
@Service
public class TokenService {

	private static final long TTL_SECONDS = 7L * 24 * 3600;

	private final Algorithm algorithm;
	private final JWTVerifier verifier;
	/** 已注销 token 的 jti → 过期时间；进程内有效，重启后清空。 */
	private final Map<String, Instant> revokedTokens = new ConcurrentHashMap<>();

	public TokenService(@Value("${omniread.jwt.secret:}") String secret) {
		if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
			throw new IllegalStateException(
					"omniread.jwt.secret 缺失或少于 32 字节：请把 src/main/resources/application-local.yml.example "
							+ "复制为同目录 application-local.yml 并填写 secret");
		}
		this.algorithm = Algorithm.HMAC256(secret.getBytes(StandardCharsets.UTF_8));
		this.verifier = JWT.require(algorithm).build();
	}

	public String issue(long userId, String username, String role) {
		Instant now = Instant.now();
		return JWT.create()
				.withSubject(String.valueOf(userId))
				.withJWTId(UUID.randomUUID().toString())
				.withClaim("username", username)
				.withClaim("role", role)
				.withIssuedAt(now)
				.withExpiresAt(now.plusSeconds(TTL_SECONDS))
				.sign(algorithm);
	}

	public Claims parse(String token) {
		try {
			DecodedJWT jwt = verifier.verify(token);
			String jti = jwt.getId();
			Instant expiresAt = jwt.getExpiresAt() == null ? null : jwt.getExpiresAt().toInstant();
			if (jti != null && isRevoked(jti)) {
				throw new BusinessException(ErrorCode.UNAUTHORIZED, "登录已失效，请重新登录");
			}
			return new Claims(Long.parseLong(jwt.getSubject()), jwt.getClaim("username").asString(),
					jwt.getClaim("role").asString(), jti, expiresAt);
		}
		catch (TokenExpiredException e) {
			throw new BusinessException(ErrorCode.UNAUTHORIZED, "登录已过期，请重新登录");
		}
		catch (JWTVerificationException | NumberFormatException e) {
			throw new BusinessException(ErrorCode.UNAUTHORIZED);
		}
	}

	/** 注销当前 token；只吊销这一个 jti，重启后吊销表清空。 */
	public void revoke(Claims claims) {
		if (claims.jti() != null && claims.expiresAt() != null) {
			revokedTokens.put(claims.jti(), claims.expiresAt());
		}
	}

	private boolean isRevoked(String jti) {
		Instant expiresAt = revokedTokens.get(jti);
		if (expiresAt == null) {
			return false;
		}
		if (expiresAt.isBefore(Instant.now())) {
			revokedTokens.remove(jti);
			return false;
		}
		return true;
	}

	public record Claims(long userId, String username, String role, String jti, Instant expiresAt) {
	}
}
