package com.omniread.auth;

import java.nio.charset.StandardCharsets;
import java.time.Instant;

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
				.withClaim("username", username)
				.withClaim("role", role)
				.withIssuedAt(now)
				.withExpiresAt(now.plusSeconds(TTL_SECONDS))
				.sign(algorithm);
	}

	public Claims parse(String token) {
		try {
			DecodedJWT jwt = verifier.verify(token);
			return new Claims(Long.parseLong(jwt.getSubject()), jwt.getClaim("username").asString(),
					jwt.getClaim("role").asString());
		}
		catch (TokenExpiredException e) {
			throw new BusinessException(ErrorCode.UNAUTHORIZED, "登录已过期，请重新登录");
		}
		catch (JWTVerificationException | NumberFormatException e) {
			throw new BusinessException(ErrorCode.UNAUTHORIZED);
		}
	}

	public record Claims(long userId, String username, String role) {
	}
}
