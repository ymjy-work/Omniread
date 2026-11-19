package com.omniread.byok;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import com.omniread.support.IntegrationTestBase;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ByokModelListTest extends IntegrationTestBase {

	private static final String GOOD_KEY = "sk-test-1234567890abcdef6789";
	private static final String BAD_KEY = "sk-upstream-bad-key-0001";

	private static final HttpServer MODELS_STUB;

	static {
		try {
			MODELS_STUB = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
		}
		catch (IOException e) {
			throw new ExceptionInInitializerError(e);
		}
		MODELS_STUB.createContext("/models", exchange -> {
			String authorization = exchange.getRequestHeaders().getFirst("Authorization");
			if (!("Bearer " + GOOD_KEY).equals(authorization)) {
				exchange.sendResponseHeaders(401, -1);
				exchange.close();
				return;
			}
			byte[] body = "{\"data\":[{\"id\":\"b-model\"},{\"id\":\"a-model\"},{\"id\":\"a-model\"}]}"
					.getBytes(StandardCharsets.UTF_8);
			exchange.getResponseHeaders().set("Content-Type", "application/json");
			exchange.sendResponseHeaders(200, body.length);
			try (OutputStream out = exchange.getResponseBody()) {
				out.write(body);
			}
		});
		MODELS_STUB.start();
		Runtime.getRuntime().addShutdownHook(new Thread(() -> MODELS_STUB.stop(0)));
	}

	@TestConfiguration
	static class StubModelsConfig {

		@Bean
		@Primary
		ByokModelsClient byokModelsClient() {
			return new ByokModelsClient(
					provider -> "http://127.0.0.1:" + MODELS_STUB.getAddress().getPort());
		}
	}

	private String userToken(String username) throws Exception {
		createUserViaAdmin(username, "user-pass-1");
		return loginToken(username, "user-pass-1");
	}

	@Test
	void modelsAreSortedAndDeduplicated() throws Exception {
		String token = userToken("models-user-1");
		assertEquals(200, send("POST", "/api/me/api-keys",
				"{\"provider\":\"openai\",\"key\":\"" + GOOD_KEY + "\"}", token).statusCode());

		HttpResponse<String> response = send("GET", "/api/me/api-keys/openai/models", null, token);
		assertEquals(200, response.statusCode());
		JsonNode data = json(response).path("data");
		assertEquals(2, data.size());
		assertEquals("a-model", data.get(0).asString());
		assertEquals("b-model", data.get(1).asString());
		assertFalse(response.body().contains(GOOD_KEY));
	}

	@Test
	void missingKeyReturns400() throws Exception {
		String token = userToken("models-user-2");
		HttpResponse<String> response = send("GET", "/api/me/api-keys/deepseek/models", null, token);
		assertEquals(400, response.statusCode());
		assertEquals("请先保存该提供商的 API Key", json(response).path("message").asString());
	}

	@Test
	void upstreamFailureReturns502WithoutKey() throws Exception {
		String token = userToken("models-user-3");
		send("POST", "/api/me/api-keys",
				"{\"provider\":\"openai\",\"key\":\"" + BAD_KEY + "\"}", token);

		HttpResponse<String> response = send("GET", "/api/me/api-keys/openai/models", null, token);
		assertEquals(502, response.statusCode());
		assertFalse(response.body().contains(BAD_KEY));
		assertFalse(response.body().contains("Bearer"));
	}

	@Test
	void invalidProviderReturns400() throws Exception {
		String token = userToken("models-user-4");
		HttpResponse<String> response = send("GET", "/api/me/api-keys/unknown/models", null, token);
		assertEquals(400, response.statusCode());
	}
}
