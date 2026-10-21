package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.omniread.backend.user.AccountService;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import jakarta.servlet.http.Cookie;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

/**
 * 三条护栏在**真实注册路径**上（拦截器 + 控制器都在链上）的验收：
 * 阅读范围 403 与导航夹住、卷外插图 403、配额 429（带 `Retry-After`）与 provider 5xx 退还、
 * 一键下线 503（健康检查除外）。
 *
 * <p>阈值压到 **1 轮/日**：一天一次就够验「用完挡、退还得回来」两件事。
 * 每个用例发**自己的账户**——日额度按账户计，共用账户就会互相看见对方那几轮。
 *
 * <p>下游是 JDK 自带的 {@code HttpServer} 桩（同 {@code QueryMultiTurnTest} 的理由：
 * 这一半正确性在真的 HTTP 往返上，打桩成 Java 对象就绕过去了）。
 */
@SpringBootTest(properties = {
        "omniread.quota.turns-per-day=1",
        "omniread.quota.turns-per-minute=10",
        "omniread.quota.concurrent=1",
        "omniread.reading.volume-index=1"
})
class GuardrailTest {

    private static final String PASSWORD = "guardrail-test-password";

    private static final String CSRF = AuthInterceptor.CSRF_HEADER;

    private static final String ANSWER_JSON = "{\"request_id\":\"req_" + "0".repeat(32)
            + "\",\"status\":\"answered\",\"answer\":\"好[C1]。\","
            + "\"context_chapters\":[{\"chapter_index\":1,\"chapter_title\":\"序章\"}],"
            + "\"usage\":{\"answer_provider\":\"stub\",\"answer_model\":\"stub-1\",\"latency_ms\":3},"
            + "\"rewritten_query\":null}";

    /** 桩的下一次 `/query` 是否以 502 收场（模拟 provider 故障）。 */
    private static final AtomicBoolean QUERY_FAILS = new AtomicBoolean(false);

    private static final HttpServer PYTHON = startStub();

    private static final Path DB_PATH = tempDir().resolve("omniread.db");

    private static final Path MARKER = tempDir().resolve("OFFLINE");

    private static Path tempDir() {
        try {
            return Files.createTempDirectory("omniread-guardrail");
        } catch (IOException e) {
            throw new IllegalStateException("建不了临时目录", e);
        }
    }

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", GuardrailTest::handle);
            server.start();
            return server;
        } catch (IOException e) {
            throw new IllegalStateException("起不了桩服务", e);
        }
    }

    private static void handle(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        int status = 200;
        String contentType = "application/json";
        byte[] response;
        if (path.endsWith("/books")) {
            response = "{\"books\":[{\"book_id\":1,\"chapter_count\":20}]}".getBytes(StandardCharsets.UTF_8);
        } else if (path.endsWith("/chapters")) {
            StringBuilder chapters = new StringBuilder();
            for (int index = 1; index <= 20; index++) {
                int volume = index <= 11 ? 1 : 2;
                chapters.append(chapters.isEmpty() ? "" : ",")
                        .append("{\"chapter_index\":").append(index)
                        .append(",\"chapter_title\":\"第").append(index).append("章\"")
                        .append(",\"volume_index\":").append(volume)
                        .append(",\"volume_title\":\"第").append(volume).append("卷\"}");
            }
            response = ("{\"book_id\":1,\"chapters\":[" + chapters + "]}").getBytes(StandardCharsets.UTF_8);
        } else if (path.contains("/chapters/")) {
            int index = Integer.parseInt(path.substring(path.lastIndexOf('/') + 1));
            int volume = index <= 11 ? 1 : 2;
            response = ("{\"chapter_index\":" + index + ",\"chapter_title\":\"第" + index + "章\","
                    + "\"volume_index\":" + volume + ",\"volume_title\":\"第" + volume + "卷\","
                    + "\"text\":\"正文\",\"images\":[{\"marker\":\"001\",\"url\":\"/api/v1/books/1/images/0"
                    + volume + "_第" + volume + "卷/00" + index + ".jpg\"}],"
                    + "\"prev_chapter_index\":" + (index - 1) + ",\"next_chapter_index\":" + (index + 1) + "}")
                    .getBytes(StandardCharsets.UTF_8);
        } else if (path.contains("/images/")) {
            contentType = "image/jpeg";
            response = "JPEG-BYTES".getBytes(StandardCharsets.UTF_8);
        } else if (path.endsWith("/query")) {
            if (QUERY_FAILS.get()) {
                status = 502;
                response = "{}".getBytes(StandardCharsets.UTF_8);
            } else {
                response = ANSWER_JSON.getBytes(StandardCharsets.UTF_8);
            }
        } else {
            status = 404;
            response = "{}".getBytes(StandardCharsets.UTF_8);
        }
        exchange.getResponseHeaders().add("Content-Type", contentType);
        exchange.sendResponseHeaders(status, response.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(response);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", DB_PATH::toString);
        registry.add("omniread.rag.base-url", () -> "http://127.0.0.1:" + PYTHON.getAddress().getPort());
        registry.add("omniread.offline.marker-file", MARKER::toString);
    }

    @Autowired
    private WebApplicationContext context;

    @Autowired
    private AccountService accounts;

    private MockMvc mvc;

    @BeforeEach
    void setUp() throws Exception {
        QUERY_FAILS.set(false);
        Files.deleteIfExists(MARKER);
        // 过滤器显式挂上：webAppContextSetup 不装容器里的 Filter bean，而问答端点要读
        // request_id 那个请求属性（不挂的话每个请求都是 400，看起来像参数校验失败）
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(context.getBean(RequestIdFilter.class))
                .build();
    }

    private Cookie login(String name) throws Exception {
        accounts.create(name, PASSWORD);
        MvcResult result = mvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"" + name + "\",\"password\":\"" + PASSWORD + "\"}"))
                .andExpect(status().isOk())
                .andReturn();
        Cookie cookie = result.getResponse().getCookie("omniread_session");
        assertThat(cookie).as("登录要种下会话 cookie").isNotNull();
        return cookie;
    }

    private String createSession(Cookie cookie) throws Exception {
        MvcResult result = mvc.perform(post("/api/v1/sessions")
                        .cookie(cookie)
                        .header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"book_id\":1,\"level\":\"past\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        return com.jayway.jsonpath.JsonPath.read(result.getResponse().getContentAsString(), "$.id");
    }

    private org.springframework.test.web.servlet.ResultActions ask(Cookie cookie, String sessionId) throws Exception {
        return mvc.perform(post("/api/v1/query")
                .cookie(cookie)
                .header(CSRF, "1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"session_id\":\"" + sessionId + "\",\"book_id\":1,\"question\":\"她回去了吗？\","
                        + "\"level\":\"past\",\"progress\":1}"));
    }

    @Test
    @DisplayName("阅读范围：卷外 403，卷内可读，且前后导航不跨卷")
    void chapterOutsideVolumeIsForbidden() throws Exception {
        Cookie cookie = login("guard-chapter");

        mvc.perform(get("/api/v1/books/1/chapters/12").cookie(cookie))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("RAG_FORBIDDEN"));

        // 第 11 章是第 1 卷最后一章：可读，但「下一章」（12）要收掉
        mvc.perform(get("/api/v1/books/1/chapters/11").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.chapter_index").value(11))
                .andExpect(jsonPath("$.next_chapter_index").doesNotExist());

        mvc.perform(get("/api/v1/books/1/chapters/5").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.next_chapter_index").value(6));
    }

    @Test
    @DisplayName("插图：只放行可读章节引用到的那些，其余 403")
    void imageOutsideReadableChaptersIsForbidden() throws Exception {
        Cookie cookie = login("guard-image");
        String volumeTwo = URLEncoder.encode("02_第2卷", StandardCharsets.UTF_8);
        String volumeOne = URLEncoder.encode("01_第1卷", StandardCharsets.UTF_8);

        mvc.perform(get("/api/v1/books/1/images/" + volumeTwo + "/005.jpg").cookie(cookie))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("RAG_FORBIDDEN"));

        mvc.perform(get("/api/v1/books/1/images/" + volumeOne + "/005.jpg").cookie(cookie))
                .andExpect(status().isOk())
                // 插图 URL 带扩展名，Cloudflare 默认按扩展名缓存而不看路径：少了这个头，
                // 未登录也能从边缘缓存取到图，且一键下线后边缘仍有副本
                .andExpect(header().string("Cache-Control", "private, no-store"))
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.content()
                        .string("JPEG-BYTES"));
    }

    @Test
    @DisplayName("日额度：用满即 429 + Retry-After，响应码是额度那一个")
    void dailyQuotaBlocksWithRetryAfter() throws Exception {
        Cookie cookie = login("guard-daily");
        String sessionId = createSession(cookie);

        ask(cookie, sessionId).andExpect(status().isOk());
        ask(cookie, sessionId)
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.code").value("RAG_DAILY_QUOTA_EXCEEDED"))
                .andExpect(header().exists("Retry-After"));
    }

    @Test
    @DisplayName("provider 5xx 退还那一轮：额度只有 1，第二次还能问就是退回来了")
    void providerFailureRefundsTheTurn() throws Exception {
        Cookie cookie = login("guard-refund");
        String sessionId = createSession(cookie);

        QUERY_FAILS.set(true);
        ask(cookie, sessionId).andExpect(status().isBadGateway());
        QUERY_FAILS.set(false);
        ask(cookie, sessionId).andExpect(status().isOk());
    }

    @Test
    @DisplayName("一键下线：标记文件一出现，除健康检查外一律 503；删掉即恢复")
    void offlineSwitchBlocksEverythingButHealth() throws Exception {
        Cookie cookie = login("guard-offline");

        Files.createFile(MARKER);
        try {
            mvc.perform(get("/api/v1/books").cookie(cookie))
                    .andExpect(status().isServiceUnavailable())
                    .andExpect(jsonPath("$.code").value("RAG_UNAVAILABLE"));
            mvc.perform(get("/api/v1/health")).andExpect(status().isOk());
        } finally {
            Files.deleteIfExists(MARKER);
        }

        mvc.perform(get("/api/v1/books").cookie(cookie)).andExpect(status().isOk());
    }
}
