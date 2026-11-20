package com.omniread.auth;

import java.net.http.HttpResponse;

import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AuthFlowTest extends IntegrationTestBase {

	@Test
	void loginReturnsTokenAndUser() throws Exception {
		HttpResponse<String> response = send("POST", "/api/auth/login",
				"{\"username\":\"admin\",\"password\":\"admin-pass-123\"}", null);
		assertEquals(200, response.statusCode());
		JsonNode body = json(response);
		assertEquals(0, body.path("code").asInt());
		assertFalse(body.path("data").path("token").asString().isBlank());
		assertEquals("admin", body.path("data").path("user").path("username").asString());
	}

	@Test
	void wrongPasswordReturns401() throws Exception {
		HttpResponse<String> response = send("POST", "/api/auth/login",
				"{\"username\":\"admin\",\"password\":\"wrong-pass\"}", null);
		assertEquals(401, response.statusCode());
		assertEquals(40100, json(response).path("code").asInt());
	}

	@Test
	void blankUsernameReturns400() throws Exception {
		HttpResponse<String> response = send("POST", "/api/auth/login",
				"{\"username\":\"\",\"password\":\"x\"}", null);
		assertEquals(400, response.statusCode());
		assertEquals(40000, json(response).path("code").asInt());
	}

	@Test
	void booksRequireValidToken() throws Exception {
		HttpResponse<String> anonymous = send("GET", "/api/books", null, null);
		assertEquals(401, anonymous.statusCode());
		assertEquals(40100, json(anonymous).path("code").asInt());

		HttpResponse<String> forged = send("GET", "/api/books", null, "not-a-jwt");
		assertEquals(401, forged.statusCode());

		HttpResponse<String> authorized = send("GET", "/api/books", null, adminToken());
		assertEquals(200, authorized.statusCode());
		assertTrue(json(authorized).path("data").isArray());
	}

	@Test
	void logoutRevokesUserToken() throws Exception {
		createUserViaAdmin("logout-user-1", "pw-123456");
		String token = loginToken("logout-user-1", "pw-123456");

		assertEquals(200, send("POST", "/api/auth/logout", null, token).statusCode());
		assertEquals(401, send("GET", "/api/me/account", null, token).statusCode());
		assertEquals(401, send("POST", "/api/auth/logout", null, null).statusCode());
	}
}
