package com.omniread.chat;

import java.net.http.HttpResponse;

import com.omniread.book.BookMapper;
import com.omniread.book.model.BookEntity;
import com.omniread.common.Timestamps;
import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ChatAskBillingTest extends IntegrationTestBase {

	@Autowired
	private BookMapper bookMapper;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	private record Ctx(String token, long userId, long sessionId) {
	}

	private Ctx setup(String username) throws Exception {
		long userId = createUserViaAdmin(username, "user-pass-1");
		String token = loginToken(username, "user-pass-1");
		BookEntity book = new BookEntity();
		book.setTitle("计费测试书-" + username);
		book.setCreatedAt(Timestamps.now());
		bookMapper.insert(book);
		JsonNode session = json(send("POST", "/api/chat/sessions",
				"{\"bookId\":" + book.getId() + "}", token));
		return new Ctx(token, userId, session.path("data").path("id").asLong());
	}

	private HttpResponse<String> ask(Ctx ctx, String body) throws Exception {
		return send("POST", "/api/chat/sessions/" + ctx.sessionId() + "/ask", body, ctx.token());
	}

	private long credits(Ctx ctx) throws Exception {
		return json(send("GET", "/api/me/account", null, ctx.token())).path("data").path("credits").asLong();
	}

	@Test
	void autoDeductsOneCreditAndRecordsUsage() throws Exception {
		Ctx ctx = setup("ask-auto");
		HttpResponse<String> response = ask(ctx, "{\"question\":\"她是谁？\"}");
		assertEquals(200, response.statusCode());
		JsonNode data = json(response).path("data");
		assertEquals("auto", data.path("usage").path("mode").asString());
		assertEquals("free-channel", data.path("usage").path("provider").asString());
		assertEquals("auto-model", data.path("usage").path("model").asString());
		assertEquals(10, data.path("usage").path("promptTokens").asLong());
		assertEquals(20, data.path("usage").path("completionTokens").asLong());
		assertEquals(99, credits(ctx));
		// auto 的实际路由取自 rag 响应 usage 内的 provider/model，并落 usage_record
		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM usage_record WHERE user_id = ? AND provider = 'free-channel' "
						+ "AND model = 'auto-model'",
				Integer.class, ctx.userId()));

		JsonNode ragRequest = MAPPER.readTree(LAST_ASK_BODY.get());
		assertEquals("auto", ragRequest.path("mode").asString());
		assertFalse(ragRequest.has("api_key"));

		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM usage_record WHERE user_id = ? AND mode = 'auto' AND credits = 1",
				Integer.class, ctx.userId()));
		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM credit_ledger WHERE user_id = ? AND type = 'usage' AND amount = -1",
				Integer.class, ctx.userId()));
	}

	@Test
	void platformForbiddenForFreeAndValidatedForPlus() throws Exception {
		Ctx free = setup("ask-platform-free");
		assertEquals(403, ask(free,
				"{\"question\":\"x\",\"mode\":\"platform\",\"model\":\"qwen3.7-plus\"}").statusCode());

		Ctx plus = setup("ask-platform-plus");
		send("POST", "/api/me/plan", "{\"plan\":\"plus\"}", plus.token());
		HttpResponse<String> ok = ask(plus,
				"{\"question\":\"x\",\"mode\":\"platform\",\"model\":\"qwen3.7-plus\"}");
		assertEquals(200, ok.statusCode());
		assertEquals(499, credits(plus));
		// usage 缺 provider/model 时回退请求值
		assertEquals("bailian", json(ok).path("data").path("usage").path("provider").asString());
		assertEquals("qwen3.7-plus", json(ok).path("data").path("usage").path("model").asString());
		JsonNode ragRequest = MAPPER.readTree(LAST_ASK_BODY.get());
		assertEquals("platform", ragRequest.path("mode").asString());
		assertEquals("bailian", ragRequest.path("provider").asString());
		assertEquals("qwen3.7-plus", ragRequest.path("model").asString());
		assertFalse(ragRequest.has("api_key"));

		assertEquals(400, ask(plus,
				"{\"question\":\"x\",\"mode\":\"platform\",\"model\":\"qwen3.8-max\"}").statusCode());
		assertEquals(400, ask(plus, "{\"question\":\"x\",\"mode\":\"platform\"}").statusCode());
	}

	@Test
	void byokRequiresStoredKeyAndSkipsCredits() throws Exception {
		Ctx ctx = setup("ask-byok");
		assertEquals(400, ask(ctx,
				"{\"question\":\"x\",\"mode\":\"byok\",\"provider\":\"openai\",\"model\":\"my-model\"}")
				.statusCode());
		assertEquals(400, ask(ctx,
				"{\"question\":\"x\",\"mode\":\"byok\",\"provider\":\"openai\"}").statusCode());

		send("POST", "/api/me/api-keys",
				"{\"provider\":\"openai\",\"key\":\"sk-test-1234567890abcdef6789\"}", ctx.token());
		HttpResponse<String> ok = ask(ctx,
				"{\"question\":\"x\",\"mode\":\"byok\",\"provider\":\"openai\",\"model\":\"my-free-model\"}");
		assertEquals(200, ok.statusCode());
		assertEquals(100, credits(ctx));
		assertEquals("byok", json(ok).path("data").path("usage").path("mode").asString());
		assertEquals("openai", json(ok).path("data").path("usage").path("provider").asString());
		assertEquals("my-free-model", json(ok).path("data").path("usage").path("model").asString());

		JsonNode ragRequest = MAPPER.readTree(LAST_ASK_BODY.get());
		assertEquals("byok", ragRequest.path("mode").asString());
		assertEquals("openai", ragRequest.path("provider").asString());
		assertEquals("my-free-model", ragRequest.path("model").asString());
		assertEquals("sk-test-1234567890abcdef6789", ragRequest.path("api_key").asString());

		assertEquals(1, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM usage_record WHERE user_id = ? AND mode = 'byok' AND credits = 0",
				Integer.class, ctx.userId()));
	}

	@Test
	void ragFailureDoesNotCharge() throws Exception {
		Ctx ctx = setup("ask-failure");
		long before = credits(ctx);
		HttpResponse<String> response = ask(ctx, "{\"question\":\"FAIL 请失败\"}");
		assertEquals(502, response.statusCode());
		assertEquals(50200, json(response).path("code").asInt());
		assertEquals(before, credits(ctx));
		assertEquals(0, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM usage_record WHERE user_id = ?", Integer.class, ctx.userId()));
		assertEquals(0, jdbcTemplate.queryForObject(
				"SELECT COUNT(*) FROM credit_ledger WHERE user_id = ? AND type = 'usage'",
				Integer.class, ctx.userId()));
	}

	@Test
	void insufficientCreditsRejectedBeforeRag() throws Exception {
		Ctx ctx = setup("ask-no-credits");
		jdbcTemplate.update("UPDATE user SET credits = 0 WHERE id = ?", ctx.userId());
		HttpResponse<String> response = ask(ctx, "{\"question\":\"x\"}");
		assertEquals(400, response.statusCode());
		assertEquals(40201, json(response).path("code").asInt());
		assertTrue(json(send("GET", "/api/chat/sessions/" + ctx.sessionId() + "/messages",
				null, ctx.token())).path("data").size() == 0);
	}
}
