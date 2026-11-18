package com.omniread.support;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicReference;

import com.sun.net.httpserver.HttpServer;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/** 集成测试基座：临时 SQLite + 随机端口 + 进程内 rag stub，全部子类共享同一上下文。 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
public abstract class IntegrationTestBase {

	protected static final ObjectMapper MAPPER = JsonMapper.builder().build();
	protected static final AtomicReference<String> LAST_ASK_BODY = new AtomicReference<>();
	protected static final String STUB_ANSWER = "这是 stub 回答。";

	private static final Path DB_FILE;
	private static final HttpServer RAG_STUB;
	private static final HttpClient HTTP = HttpClient.newHttpClient();
	private static String cachedToken;

	static {
		try {
			Files.createDirectories(Path.of("target"));
			DB_FILE = Files.createTempFile(Path.of("target"), "gateway-test-", ".db");
			DB_FILE.toFile().deleteOnExit();
			RAG_STUB = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
		}
		catch (IOException e) {
			throw new ExceptionInInitializerError(e);
		}
		RAG_STUB.createContext("/v1/index", exchange -> {
			exchange.getRequestBody().readAllBytes();
			respond(exchange, "{\"indexed_chunks\":3}");
		});
		RAG_STUB.createContext("/v1/ask", exchange -> {
			LAST_ASK_BODY.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
			respond(exchange, MAPPER.writeValueAsString(java.util.Map.of(
					"answer", STUB_ANSWER,
					"citations", java.util.List.of(java.util.Map.of(
							"chapter_id", "book:1:chapter:1",
							"chapter_index", 1,
							"title", "序章",
							"quote", "私立征岭学园。")))));
		});
		RAG_STUB.start();
		Runtime.getRuntime().addShutdownHook(new Thread(() -> RAG_STUB.stop(0)));
	}

	private static void respond(com.sun.net.httpserver.HttpExchange exchange, String body) throws IOException {
		byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
		exchange.getResponseHeaders().set("Content-Type", "application/json");
		exchange.sendResponseHeaders(200, bytes.length);
		try (OutputStream out = exchange.getResponseBody()) {
			out.write(bytes);
		}
	}

	@DynamicPropertySource
	static void properties(DynamicPropertyRegistry registry) {
		registry.add("spring.datasource.url", () -> "jdbc:sqlite:" + DB_FILE.toAbsolutePath());
		registry.add("omniread.jwt.secret", () -> "test-secret-0123456789abcdef0123456789abcdef");
		registry.add("omniread.admin.username", () -> "admin");
		registry.add("omniread.admin.password", () -> "admin-pass-123");
		registry.add("omniread.rag.base-url",
				() -> "http://127.0.0.1:" + RAG_STUB.getAddress().getPort());
	}

	@Autowired
	private Environment environment;

	protected HttpResponse<String> send(String method, String path, String body, String token)
			throws IOException, InterruptedException {
		HttpRequest.Builder builder = HttpRequest.newBuilder(
				URI.create("http://127.0.0.1:" + environment.getProperty("local.server.port") + path))
				.header("Content-Type", "application/json");
		if (token != null) {
			builder.header("Authorization", "Bearer " + token);
		}
		builder.method(method, body == null
				? HttpRequest.BodyPublishers.noBody()
				: HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));
		return HTTP.send(builder.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
	}

	protected JsonNode json(HttpResponse<String> response) {
		return MAPPER.readTree(response.body());
	}

	protected String adminToken() throws IOException, InterruptedException {
		if (cachedToken == null) {
			HttpResponse<String> response = send("POST", "/api/auth/login",
					"{\"username\":\"admin\",\"password\":\"admin-pass-123\"}", null);
			cachedToken = json(response).path("data").path("token").asString();
		}
		return cachedToken;
	}
}
