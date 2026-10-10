package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.omniread.backend.session.ChatMessageMapper;
import com.omniread.backend.user.AccountService;
import com.omniread.backend.user.AuthCookies;
import com.omniread.backend.user.User;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import jakarta.servlet.http.Cookie;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
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
 * 多轮问答：Java 把历史拼好发出去、把两边都落库、把 `message_id` 带回前端。
 *
 * <p>**下游是一个 JDK 自带的 {@code HttpServer} 桩**，不是打桩的 Java 对象：这一段的
 * 一半正确性在**发出去的请求体**上（历史有没有拼对、本轮问题有没有混进它自己的历史），
 * 而那只有把真的 HTTP 请求接下来才看得到。桩还把每次收到的请求体留下来供断言。
 */
@SpringBootTest
class QueryMultiTurnTest {

    private static final String PASSWORD = "correct-horse-battery-staple";

    private static final String CSRF = AuthInterceptor.CSRF_HEADER;

    private static final String ANSWER = "她后来回去了[C1]。";

    private static final List<String> RECEIVED = new CopyOnWriteArrayList<>();

    private static final HttpServer PYTHON = startStub();

    private static final Path DB_PATH = createDbPath();

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", QueryMultiTurnTest::handle);
            server.start();
            return server;
        } catch (IOException e) {
            throw new IllegalStateException("起不了桩服务", e);
        }
    }

    private static void handle(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        byte[] response;
        String contentType = "application/json";
        if (path.endsWith("/books")) {
            response = "{\"books\":[{\"book_id\":1,\"chapter_count\":193}]}"
                    .getBytes(StandardCharsets.UTF_8);
        } else if (path.endsWith("/query-stream")) {
            RECEIVED.add(body);
            contentType = "text/event-stream";
            response = sseFrames().getBytes(StandardCharsets.UTF_8);
        } else {
            RECEIVED.add(body);
            response = ("{\"request_id\":\"req_" + "0".repeat(32) + "\",\"status\":\"answered\","
                            + "\"answer\":\"" + ANSWER + "\","
                            + "\"context_chapters\":[{\"chapter_index\":1,\"chapter_title\":\"第一章\"}],"
                            + "\"usage\":{\"answer_provider\":\"stub\",\"answer_model\":\"stub-1\","
                            + "\"latency_ms\":7},\"rewritten_query\":null}")
                    .getBytes(StandardCharsets.UTF_8);
        }
        exchange.getResponseHeaders().add("Content-Type", contentType);
        exchange.sendResponseHeaders(200, response.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(response);
        }
    }

    private static String sseFrames() {
        return "event: answer_delta\ndata: {\"text\":\"她后来\"}\n\n"
                + "event: answer_delta\ndata: {\"text\":\"回去了[C1]。\"}\n\n"
                + "event: query_done\ndata: {\"status\":\"answered\","
                + "\"context_chapters\":[{\"chapter_index\":1,\"chapter_title\":\"第一章\"}],"
                + "\"usage\":{\"answer_provider\":\"stub\",\"answer_model\":\"stub-1\","
                + "\"latency_ms\":3}}\n\n"
                + "data: [DONE]\n\n";
    }

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-multiturn");
            dir.toFile().deleteOnExit();
            return dir.resolve("omniread.db");
        } catch (IOException e) {
            throw new IllegalStateException("无法建临时目录", e);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", DB_PATH::toString);
        registry.add("omniread.rag.base-url", () -> "http://127.0.0.1:" + PYTHON.getAddress().getPort());
    }

    @Autowired
    private WebApplicationContext context;
    @Autowired
    private AccountService accountService;
    @Autowired
    private ChatMessageMapper messageMapper;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        RECEIVED.clear();
        // **过滤器要显式挂上**：`webAppContextSetup` 不会自动把容器里的 Filter bean 装进来，
        // 而问答端点用 `@RequestAttribute(RequestIds.ATTRIBUTE)` 取 request_id——
        // 不挂的话每个请求都是 400「Missing request attribute」，看起来像参数校验失败。
        // 其它全上下文用例没暴露这一点，是因为它们的端点不读这个属性。
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(context.getBean(RequestIdFilter.class))
                .build();
    }

    @Test
    @DisplayName("连问两轮：第二轮发出去的历史里有第一轮的一问一答，且不含本轮")
    void secondTurnCarriesTheFirstTurn() throws Exception {
        Cookie cookie = login(newAccount("turn"));
        String sessionId = createSession(cookie);

        ask(cookie, sessionId, "她后来回去了吗？");
        ask(cookie, sessionId, "那她是什么时候回去的？");

        assertThat(RECEIVED).hasSize(2);
        String second = RECEIVED.get(1);
        assertThat(second)
                .as("第二轮要带上第一轮的一问一答")
                .contains("\"role\":\"user\",\"content\":\"她后来回去了吗？\"")
                .contains("\"role\":\"assistant\",\"content\":\"" + ANSWER + "\"");
        assertThat(countOccurrences(second, "那她是什么时候回去的？"))
                .as("**本轮的问题只该出现一次**（在 question 字段里）——写进 history 的话"
                        + "模型会看到同一个问题被问两遍，而两边都不报错")
                .isEqualTo(1);
    }

    @Test
    @DisplayName("两轮都落库：一问一答各一条，seq 不重不漏")
    void bothTurnsArePersisted() throws Exception {
        Cookie cookie = login(newAccount("persist"));
        String sessionId = createSession(cookie);

        ask(cookie, sessionId, "第一问");
        ask(cookie, sessionId, "第二问");

        var messages = messageMapper.findBySession(sessionId);
        assertThat(messages).extracting("seq").containsExactly(1, 2, 3, 4);
        assertThat(messages).extracting("role").containsExactly("user", "assistant", "user", "assistant");
        assertThat(messages.get(1).getContent()).isEqualTo(ANSWER);
        assertThat(messages.get(1).getMeta())
                .as("回答那一条的 meta 留着当时的引用范围与模型——多轮出问题时只有这里查得到")
                .contains("context_chapters").contains("stub-1");
    }

    @Test
    @DisplayName("流式：正文按 delta 攒起来落库，终止帧带上 session_id 与 message_id")
    void streamAccumulatesAndStampsTheIds() throws Exception {
        Cookie cookie = login(newAccount("stream"));
        String sessionId = createSession(cookie);

        String body = mvc.perform(post("/api/v1/query/stream").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(askBody(sessionId, "她后来回去了吗？")))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);

        assertThat(body).contains("event: answer_delta").contains("data: [DONE]");
        assertThat(body)
                .as("终止帧要带网关分配的两个 id——前端靠 message_id 定位「从哪一条重新生成」")
                .contains("\"session_id\":\"" + sessionId + "\"")
                .containsPattern("\"message_id\":[0-9]+");

        var messages = messageMapper.findBySession(sessionId);
        assertThat(messages).hasSize(2);
        assertThat(messages.get(1).getContent())
                .as("正文分散在若干 delta 里，不攒起来落库的就是一条空消息")
                .isEqualTo("她后来回去了[C1]。");
    }

    @Test
    @DisplayName("会话详情能看到落库的两条")
    void detailShowsBothTurns() throws Exception {
        Cookie cookie = login(newAccount("detail"));
        String sessionId = createSession(cookie);
        ask(cookie, sessionId, "她后来回去了吗？");

        mvc.perform(get("/api/v1/sessions/" + sessionId).cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.messages.length()").value(2))
                .andExpect(jsonPath("$.messages[0].content").value("她后来回去了吗？"))
                .andExpect(jsonPath("$.messages[1].content").value(ANSWER));
    }

    @Test
    @DisplayName("level 与会话不符即 409：切档位要走分叉，不在这儿悄悄换挡")
    void levelMismatchIsAConflict() throws Exception {
        Cookie cookie = login(newAccount("mismatch"));
        String sessionId = createSession(cookie);

        mvc.perform(post("/api/v1/query").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"session_id\":\"" + sessionId
                                + "\",\"book_id\":1,\"question\":\"问\",\"level\":\"past\",\"progress\":1}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("RAG_SESSION_MISMATCH"));
    }

    // ── 夹具 ──

    private User newAccount(String prefix) {
        return accountService.create(prefix + "-" + UUID.randomUUID(), PASSWORD);
    }

    private Cookie login(User user) throws Exception {
        MvcResult result = mvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"" + user.getUsername() + "\",\"password\":\"" + PASSWORD + "\"}"))
                .andExpect(status().isOk())
                .andReturn();
        return result.getResponse().getCookie(AuthCookies.NAME);
    }

    private String createSession(Cookie cookie) throws Exception {
        String body = mvc.perform(post("/api/v1/sessions").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"book_id\":1,\"level\":\"full\"}"))
                .andExpect(status().isCreated())
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
        return body.replaceAll(".*\"id\":\"([^\"]+)\".*", "$1");
    }

    private void ask(Cookie cookie, String sessionId, String question) throws Exception {
        MvcResult result = mvc.perform(post("/api/v1/query").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(askBody(sessionId, question)))
                .andReturn();
        String body = result.getResponse().getContentAsString(StandardCharsets.UTF_8)
                + " | resolved=" + result.getResolvedException();
        // 失败时把响应体带进断言消息：网关的错误体里就写着是哪个字段、哪条规则挂了。
        assertThat(result.getResponse().getStatus()).as("响应体：" + body).isEqualTo(200);
        assertThat(body).contains("\"session_id\":\"" + sessionId + "\"").contains("\"message_id\":");
        assertThat(body).contains(ANSWER);
    }

    private static String askBody(String sessionId, String question) {
        return "{\"session_id\":\"" + sessionId + "\",\"book_id\":1,\"question\":\"" + question
                + "\",\"level\":\"full\"}";
    }

    private static int countOccurrences(String haystack, String needle) {
        int count = 0;
        int at = haystack.indexOf(needle);
        while (at >= 0) {
            count++;
            at = haystack.indexOf(needle, at + needle.length());
        }
        return count;
    }
}
