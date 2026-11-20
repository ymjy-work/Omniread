package com.omniread.auth;

import java.net.http.HttpResponse;

import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class RegisterTest extends IntegrationTestBase {

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Test
	void registerCreatesFreeUserWithToken() throws Exception {
		HttpResponse<String> response = send("POST", "/api/auth/register",
				"{\"username\":\"reg-user-1\",\"password\":\"pw-123456\",\"displayName\":\"书友\"}",
				null);
		assertEquals(200, response.statusCode());
		JsonNode body = json(response);
		assertEquals(0, body.path("code").asInt());
		String token = body.path("data").path("token").asString();
		assertFalse(token.isBlank());
		assertEquals("reg-user-1", body.path("data").path("user").path("username").asString());
		assertEquals("书友", body.path("data").path("user").path("displayName").asString());

		JsonNode account = json(send("GET", "/api/me/account", null, token));
		assertEquals("free", account.path("data").path("plan").asString());
		assertEquals(100, account.path("data").path("credits").asInt());
		assertEquals(0.0, account.path("data").path("balance").asDouble());

		assertEquals("user", jdbcTemplate.queryForObject(
				"SELECT role FROM user WHERE username = 'reg-user-1'", String.class));
		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM credit_ledger WHERE user_id = "
						+ "(SELECT id FROM user WHERE username = 'reg-user-1') AND type = 'init' "
						+ "AND amount = 100", Integer.class));
	}

	@Test
	void registerDefaultsDisplayNameToUsername() throws Exception {
		HttpResponse<String> response = send("POST", "/api/auth/register",
				"{\"username\":\"reg-user-2\",\"password\":\"pw-123456\"}", null);
		assertEquals(200, response.statusCode());
		assertEquals("reg-user-2", json(response).path("data").path("user").path("displayName").asString());
	}

	@Test
	void registerIgnoresRolePlanCreditsBalanceFields() throws Exception {
		HttpResponse<String> response = send("POST", "/api/auth/register",
				"{\"username\":\"reg-user-3\",\"password\":\"pw-123456\","
						+ "\"role\":\"admin\",\"plan\":\"ultra\",\"credits\":9999,\"balance\":999}",
				null);
		assertEquals(200, response.statusCode());
		assertEquals("user", jdbcTemplate.queryForObject(
				"SELECT role FROM user WHERE username = 'reg-user-3'", String.class));
		assertEquals("free", jdbcTemplate.queryForObject(
				"SELECT plan FROM user WHERE username = 'reg-user-3'", String.class));
		assertEquals(100, jdbcTemplate.queryForObject(
				"SELECT credits FROM user WHERE username = 'reg-user-3'", Integer.class));
		assertEquals(0.0, jdbcTemplate.queryForObject(
				"SELECT balance FROM user WHERE username = 'reg-user-3'", Double.class));
	}

	@Test
	void duplicateUsernameReturns400() throws Exception {
		assertEquals(200, send("POST", "/api/auth/register",
				"{\"username\":\"reg-user-4\",\"password\":\"pw-123456\"}", null).statusCode());
		HttpResponse<String> duplicate = send("POST", "/api/auth/register",
				"{\"username\":\"reg-user-4\",\"password\":\"pw-123456\"}", null);
		assertEquals(400, duplicate.statusCode());
		assertEquals(40000, json(duplicate).path("code").asInt());
		assertEquals("用户名已存在", json(duplicate).path("message").asString());
	}

	@Test
	void blankUsernameReturns400() throws Exception {
		HttpResponse<String> response = send("POST", "/api/auth/register",
				"{\"username\":\"\",\"password\":\"x\"}", null);
		assertEquals(400, response.statusCode());
		assertEquals(40000, json(response).path("code").asInt());
	}
}
