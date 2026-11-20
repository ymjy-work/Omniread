package com.omniread.admin;

import java.net.http.HttpResponse;

import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class AdminAuthTest extends IntegrationTestBase {

	private HttpResponse<String> adminLogin(String username, String password)
			throws Exception {
		return send("POST", "/api/admin/auth/login",
				MAPPER.writeValueAsString(java.util.Map.of("username", username, "password", password)),
				null);
	}

	@Test
	void adminLoginReturnsAdminSession() throws Exception {
		HttpResponse<String> response = adminLogin("admin", "admin-pass-123");
		assertEquals(200, response.statusCode());
		JsonNode body = json(response);
		assertEquals(0, body.path("code").asInt());
		assertEquals("admin", body.path("data").path("user").path("role").asString());

		String token = body.path("data").path("token").asString();
		assertFalse(token.isBlank());
		assertEquals(200, send("GET", "/api/admin/users", null, token).statusCode());
	}

	@Test
	void wrongPasswordReturns401() throws Exception {
		HttpResponse<String> response = adminLogin("admin", "wrong-pass");
		assertEquals(401, response.statusCode());
		assertEquals(40100, json(response).path("code").asInt());
	}

	@Test
	void nonAdminReturns403() throws Exception {
		createUserViaAdmin("admin-login-plain-1", "pw-123456");
		HttpResponse<String> response = adminLogin("admin-login-plain-1", "pw-123456");
		assertEquals(403, response.statusCode());
		assertEquals(40300, json(response).path("code").asInt());
		assertEquals("该账号不是管理员", json(response).path("message").asString());
	}

	@Test
	void logoutRevokesAdminToken() throws Exception {
		String token = json(adminLogin("admin", "admin-pass-123"))
				.path("data").path("token").asString();
		assertEquals(200, send("POST", "/api/admin/auth/logout", null, token).statusCode());
		assertEquals(401, send("GET", "/api/admin/users", null, token).statusCode());
	}

	@Test
	void logoutRejectsNonAdminToken() throws Exception {
		createUserViaAdmin("admin-logout-plain-1", "pw-123456");
		String token = loginToken("admin-logout-plain-1", "pw-123456");
		assertEquals(403, send("POST", "/api/admin/auth/logout", null, token).statusCode());
	}
}
