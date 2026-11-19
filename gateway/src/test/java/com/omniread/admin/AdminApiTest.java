package com.omniread.admin;

import java.net.http.HttpResponse;

import com.omniread.auth.AdminInitializer;
import com.omniread.auth.AuthMapper;
import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AdminApiTest extends IntegrationTestBase {

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private AuthMapper authMapper;

	@Test
	void createUserDefaultsAndList() throws Exception {
		String token = adminToken();
		HttpResponse<String> created = send("POST", "/api/admin/users",
				"{\"username\":\"admin-created-1\",\"password\":\"pw-123456\",\"displayName\":\"小读\"}", token);
		assertEquals(200, created.statusCode());
		JsonNode user = json(created).path("data");
		long userId = user.path("id").asLong();
		assertEquals("user", user.path("role").asString());
		assertEquals("free", user.path("plan").asString());
		assertEquals(100, user.path("credits").asInt());
		assertEquals(20.0, user.path("balance").asDouble());
		assertFalse(user.path("planExpiresAt").asString().isBlank());

		JsonNode account = json(send("GET", "/api/me/account", null,
				loginToken("admin-created-1", "pw-123456")));
		assertEquals("free", account.path("data").path("plan").asString());
		assertEquals(100, account.path("data").path("credits").asInt());

		JsonNode list = json(send("GET", "/api/admin/users", null, token));
		boolean found = false;
		for (JsonNode node : list.path("data")) {
			found |= node.path("id").asLong() == userId;
		}
		assertTrue(found);

		HttpResponse<String> duplicate = send("POST", "/api/admin/users",
				"{\"username\":\"admin-created-1\",\"password\":\"x12345678\"}", token);
		assertEquals(400, duplicate.statusCode());
	}

	@Test
	void grantBalanceWritesLedger() throws Exception {
		long userId = createUserViaAdmin("grant-user", "pw-123456");
		HttpResponse<String> granted = send("POST", "/api/admin/users/" + userId + "/balance",
				"{\"amount\":50,\"reason\":\"测试发放\"}", adminToken());
		assertEquals(200, granted.statusCode());
		assertEquals(70.0, json(granted).path("data").path("balance").asDouble());

		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM balance_ledger WHERE user_id = ? AND type = 'grant' "
						+ "AND amount = 50 AND balance_after = 70 AND ref = '测试发放'",
				Integer.class, userId));

		HttpResponse<String> invalid = send("POST", "/api/admin/users/" + userId + "/balance",
				"{\"amount\":-5}", adminToken());
		assertEquals(400, invalid.statusCode());
	}

	@Test
	void nonAdminGets403() throws Exception {
		createUserViaAdmin("plain-user", "pw-123456");
		String token = loginToken("plain-user", "pw-123456");
		assertEquals(403, send("GET", "/api/admin/users", null, token).statusCode());
		assertEquals(403, send("POST", "/api/admin/users",
				"{\"username\":\"x\",\"password\":\"y12345678\"}", token).statusCode());
		assertEquals(403, send("POST", "/api/admin/users/1/balance",
				"{\"amount\":10}", token).statusCode());
		assertEquals(40300, json(send("GET", "/api/admin/users", null, token)).path("code").asInt());
	}

	@Test
	void existingAdminRoleIsRepaired() throws Exception {
		jdbcTemplate.update("UPDATE user SET role = 'user' WHERE username = 'admin'");
		new AdminInitializer(authMapper, "admin", "admin-pass-123").run(null);
		assertEquals("admin", authMapper.findUserByUsername("admin").getRole());
	}
}
