package com.omniread.byok;

import java.net.http.HttpResponse;

import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ByokTest extends IntegrationTestBase {

	private static final String PLAINTEXT_KEY = "sk-test-1234567890abcdef6789";

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private CryptoService cryptoService;

	private String byokUserToken(String username) throws Exception {
		createUserViaAdmin(username, "user-pass-1");
		return loginToken(username, "user-pass-1");
	}

	@Test
	void saveEncryptsAndReturnsMaskOnly() throws Exception {
		String token = byokUserToken("byok-user-1");
		HttpResponse<String> saved = send("POST", "/api/me/api-keys",
				"{\"provider\":\"openai\",\"key\":\"" + PLAINTEXT_KEY + "\"}", token);
		assertEquals(200, saved.statusCode());
		assertFalse(saved.body().contains(PLAINTEXT_KEY));
		assertEquals("sk-…6789", json(saved).path("data").path("keyMask").asString());

		HttpResponse<String> list = send("GET", "/api/me/api-keys", null, token);
		assertFalse(list.body().contains(PLAINTEXT_KEY));
		assertFalse(list.body().contains("encryptedKey"));
		assertEquals(1, json(list).path("data").size());

		long userId = jdbcTemplate.queryForObject(
				"SELECT id FROM user WHERE username = 'byok-user-1'", Long.class);
		String encrypted = jdbcTemplate.queryForObject(
				"SELECT encrypted_key FROM user_api_key WHERE user_id = ? AND provider = 'openai'",
				String.class, userId);
		assertNotEquals(PLAINTEXT_KEY, encrypted);
		assertEquals(PLAINTEXT_KEY, cryptoService.decrypt(encrypted));
	}

	@Test
	void sameProviderOverwritesAndDeleteRemoves() throws Exception {
		String token = byokUserToken("byok-user-2");
		send("POST", "/api/me/api-keys",
				"{\"provider\":\"openai\",\"key\":\"" + PLAINTEXT_KEY + "\"}", token);
		send("POST", "/api/me/api-keys",
				"{\"provider\":\"openai\",\"key\":\"sk-test-new-key-zzzz\"}", token);
		JsonNode list = json(send("GET", "/api/me/api-keys", null, token));
		assertEquals(1, list.path("data").size());
		assertEquals("sk-…zzzz", list.path("data").get(0).path("keyMask").asString());

		assertEquals(200, send("DELETE", "/api/me/api-keys?provider=openai", null, token).statusCode());
		assertEquals(0, json(send("GET", "/api/me/api-keys", null, token)).path("data").size());
		assertEquals(404, send("DELETE", "/api/me/api-keys?provider=openai", null, token).statusCode());
	}

	@Test
	void invalidProviderAndShortKey() throws Exception {
		String token = byokUserToken("byok-user-3");
		assertEquals(400, send("POST", "/api/me/api-keys",
				"{\"provider\":\"unknown\",\"key\":\"y12345678\"}", token).statusCode());
		HttpResponse<String> shortKey = send("POST", "/api/me/api-keys",
				"{\"provider\":\"deepseek\",\"key\":\"abc\"}", token);
		assertEquals(200, shortKey.statusCode());
		assertEquals("***", json(shortKey).path("data").path("keyMask").asString());
		assertTrue(json(send("GET", "/api/me/api-keys", null, token)).path("data").size() >= 1);
	}
}
