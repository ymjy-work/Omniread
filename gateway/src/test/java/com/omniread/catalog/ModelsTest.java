package com.omniread.catalog;

import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ModelsTest extends IntegrationTestBase {

	@Autowired
	private JdbcTemplate jdbcTemplate;

	private boolean containsModel(JsonNode data, String model) {
		for (JsonNode node : data) {
			if (model.equals(node.path("model").asString())) {
				return true;
			}
		}
		return false;
	}

	@Test
	void platformModelsFollowPlan() throws Exception {
		createUserViaAdmin("models-free", "pw-123456");
		String freeToken = loginToken("models-free", "pw-123456");
		assertEquals(0, json(send("GET", "/api/models?mode=platform", null, freeToken))
				.path("data").size());

		createUserViaAdmin("models-plus", "pw-123456");
		String plusToken = loginToken("models-plus", "pw-123456");
		send("POST", "/api/me/plan", "{\"plan\":\"plus\"}", plusToken);
		JsonNode plusModels = json(send("GET", "/api/models?mode=platform", null, plusToken))
				.path("data");
		assertTrue(containsModel(plusModels, "qwen3.7-plus"));
		assertFalse(containsModel(plusModels, "qwen3.8-max"));

		createUserViaAdmin("models-pro", "pw-123456");
		String proToken = loginToken("models-pro", "pw-123456");
		send("POST", "/api/admin/users/" + userId("models-pro") + "/balance",
				"{\"amount\":60}", adminToken());
		send("POST", "/api/me/plan", "{\"plan\":\"pro\"}", proToken);
		JsonNode proModels = json(send("GET", "/api/models?mode=platform", null, proToken))
				.path("data");
		assertTrue(containsModel(proModels, "qwen3.7-plus"));
		assertTrue(containsModel(proModels, "qwen3.8-max"));
	}

	@Test
	void byokListsFixedProviders() throws Exception {
		String token = adminToken();
		JsonNode data = json(send("GET", "/api/models?mode=byok", null, token)).path("data");
		assertEquals(4, data.size());
		boolean bailianHasSuggestions = false;
		for (JsonNode node : data) {
			if ("bailian".equals(node.path("provider").asString())) {
				bailianHasSuggestions = node.path("models").size() > 0;
			}
		}
		assertTrue(bailianHasSuggestions);

		JsonNode filtered = json(send("GET", "/api/models?mode=byok&provider=deepseek", null, token))
				.path("data");
		assertEquals(1, filtered.size());
		assertEquals("deepseek", filtered.get(0).path("provider").asString());

		assertEquals(400, send("GET", "/api/models?mode=unknown", null, token).statusCode());
	}

	private long userId(String username) {
		return jdbcTemplate.queryForObject("SELECT id FROM user WHERE username = ?",
				Long.class, username);
	}
}
