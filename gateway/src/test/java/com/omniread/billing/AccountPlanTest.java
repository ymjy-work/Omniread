package com.omniread.billing;

import java.net.http.HttpResponse;

import com.omniread.common.Timestamps;
import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AccountPlanTest extends IntegrationTestBase {

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Test
	void adminAccountIsUltra() throws Exception {
		JsonNode account = json(send("GET", "/api/me/account", null, adminToken()));
		assertEquals("admin", account.path("data").path("role").asString());
		assertEquals("ultra", account.path("data").path("plan").asString());
		assertEquals(4000, account.path("data").path("credits").asInt());
		assertEquals(0.0, account.path("data").path("balance").asDouble());

		JsonNode plans = json(send("GET", "/api/plans", null, adminToken()));
		assertEquals(4, plans.path("data").size());
	}

	@Test
	void plansCatalogIsPublicButPurchaseRequiresLogin() throws Exception {
		HttpResponse<String> response = send("GET", "/api/plans", null, null);
		assertEquals(200, response.statusCode());
		assertEquals(4, json(response).path("data").size());

		assertEquals(401, send("POST", "/api/me/plan", "{\"plan\":\"plus\"}", null).statusCode());
	}

	@Test
	void purchaseDeductsBalanceAndResetsCredits() throws Exception {
		long userId = createUserViaAdmin("buyer-1", "pw-123456");
		String token = loginToken("buyer-1", "pw-123456");

		HttpResponse<String> bought = send("POST", "/api/me/plan", "{\"plan\":\"plus\"}", token);
		assertEquals(200, bought.statusCode());
		JsonNode account = json(bought).path("data");
		assertEquals("plus", account.path("plan").asString());
		assertEquals(500, account.path("credits").asInt());
		assertEquals(0.0, account.path("balance").asDouble());
		assertTrue(account.path("planExpiresAt").asString().compareTo(Timestamps.now()) > 0);

		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM purchase_record WHERE user_id = ? AND plan = 'plus' AND amount = 20",
				Integer.class, userId));
		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM balance_ledger WHERE user_id = ? AND type = 'purchase' AND amount = -20",
				Integer.class, userId));
		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM credit_ledger WHERE user_id = ? AND type = 'purchase' AND balance_after = 500",
				Integer.class, userId));

		HttpResponse<String> insufficient = send("POST", "/api/me/plan", "{\"plan\":\"pro\"}", token);
		assertEquals(400, insufficient.statusCode());
		assertEquals(40202, json(insufficient).path("code").asInt());

		assertEquals(400, send("POST", "/api/me/plan", "{\"plan\":\"free\"}", token).statusCode());
		assertEquals(400, send("POST", "/api/me/plan", "{\"plan\":\"vip\"}", token).statusCode());
	}

	@Test
	void freeCycleRenewsAfterExpiry() throws Exception {
		long userId = createUserViaAdmin("free-renew", "pw-123456");
		String token = loginToken("free-renew", "pw-123456");
		jdbcTemplate.update("UPDATE user SET credits = 3, plan_expires_at = ? WHERE id = ?",
				"2026-01-01T00:00:00.000Z", userId);

		JsonNode account = json(send("GET", "/api/me/account", null, token)).path("data");
		assertEquals("free", account.path("plan").asString());
		assertEquals(100, account.path("credits").asInt());
		assertTrue(account.path("planExpiresAt").asString().compareTo(Timestamps.now()) > 0);
		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM credit_ledger WHERE user_id = ? AND type = 'renew' AND balance_after = 100",
				Integer.class, userId));
	}

	@Test
	void expiredPaidPlanFallsBackToFree() throws Exception {
		long userId = createUserViaAdmin("paid-expire", "pw-123456");
		String token = loginToken("paid-expire", "pw-123456");
		send("POST", "/api/me/plan", "{\"plan\":\"plus\"}", token);
		jdbcTemplate.update("UPDATE user SET credits = 400, plan_expires_at = ? WHERE id = ?",
				"2026-01-01T00:00:00.000Z", userId);

		JsonNode account = json(send("GET", "/api/me/account", null, token)).path("data");
		assertEquals("free", account.path("plan").asString());
		assertEquals(100, account.path("credits").asInt());
		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM credit_ledger WHERE user_id = ? AND type = 'downgrade' AND ref = 'plus'",
				Integer.class, userId));
	}
}
