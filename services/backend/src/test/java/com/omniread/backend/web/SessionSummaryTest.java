package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.omniread.backend.orchestration.SummaryExecutor;
import com.omniread.backend.session.ChatMessage;
import com.omniread.backend.session.ChatMessageMapper;
import com.omniread.backend.session.ChatSession;
import com.omniread.backend.session.ChatSessionMapper;
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
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

/**
 * 摘要的**触发与推进**：一轮回答落库之后判定、后台压、成功后一次性写 `summary` + `summary_upto`。
 *
 * <p>下游是 JDK 自带的 {@code HttpServer} 桩（同 {@code QueryMultiTurnTest}）：这一段的正确性
 * 一半在**发出去的请求体**上——压的是哪一段、旧摘要有没有带上——那只有把真的 HTTP 请求接下来
 * 才看得到。
 *
 * <p>线程池在这里换成「调用线程上直接跑」的执行器：异步的断言只能靠 sleep 或轮询，
 * 两者都会变成偶发红的用例；而线程池本身不是被测对象（会话级锁由 {@code SummaryExecutorTest}
 * 单独钉）。换成直跑之后，每个请求返回时摘要已经落库，断言就是确定性的。
 *
 * <p>预算调得很小（近轮窗口 20、保留最近 1 轮），因为这里要验的是**边界**不是量。夹具下每轮
 * 8 个 token（问题 2 + 回答 6），于是「第几轮会触发」是一次减法，不必靠数数。
 */
@SpringBootTest
class SessionSummaryTest {

    private static final String PASSWORD = "correct-horse-battery-staple";

    private static final String CSRF = AuthInterceptor.CSRF_HEADER;

    private static final String ANSWER = "她后来回去了[C1]。";

    /** 桩收到的问答请求体（`/rag/query`），按到达顺序。 */
    private static final List<String> QUERY_CALLS = new CopyOnWriteArrayList<>();

    /** 桩收到的摘要请求体（`/summarize`），按到达顺序。 */
    private static final List<String> SUMMARIZE_CALLS = new CopyOnWriteArrayList<>();

    private static final AtomicBoolean SUMMARIZE_FAILS = new AtomicBoolean();

    private static final AtomicInteger SUMMARY_SEQ = new AtomicInteger();

    /** 桩这一轮吐什么回答。空串用来造「模型一个 token 都没吐」那一轮。 */
    private static final AtomicReference<String> ANSWER_TEXT = new AtomicReference<>(ANSWER);

    private static final HttpServer PYTHON = startStub();

    private static final Path DB_PATH = createDbPath();

    @TestConfiguration
    static class InlineSummaryExecutor {

        /** 换个 bean 名，免得与生产那个 `@Component` 撞名（撞名是 BeanDefinitionOverrideException）。 */
        @Bean
        @Primary
        SummaryExecutor inlineSummaryExecutor() {
            return new SummaryExecutor(Runnable::run);
        }
    }

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", SessionSummaryTest::handle);
            server.start();
            return server;
        } catch (IOException e) {
            throw new IllegalStateException("起不了桩服务", e);
        }
    }

    private static void handle(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        if (path.endsWith("/books")) {
            respond(exchange, 200, "{\"books\":[{\"book_id\":1,\"chapter_count\":193}]}");
            return;
        }
        if (path.endsWith("/summarize")) {
            SUMMARIZE_CALLS.add(body);
            if (SUMMARIZE_FAILS.get()) {
                respond(exchange, 502, "{\"request_id\":\"req_" + "0".repeat(32)
                        + "\",\"code\":\"RAG_PROVIDER_ERROR\",\"message\":\"桩：摘要失败\"}");
                return;
            }
            respond(exchange, 200, "{\"summary\":\"摘要" + SUMMARY_SEQ.incrementAndGet()
                    + "\",\"prompt_version\":\"sum-v1\"}");
            return;
        }
        QUERY_CALLS.add(body);
        respond(exchange, 200, "{\"request_id\":\"req_" + "0".repeat(32) + "\",\"status\":\"answered\","
                + "\"answer\":\"" + ANSWER_TEXT.get() + "\","
                + "\"context_chapters\":[{\"chapter_index\":1,\"chapter_title\":\"第一章\"}],"
                + "\"usage\":{\"answer_provider\":\"stub\",\"answer_model\":\"stub-1\","
                + "\"latency_ms\":7},\"rewritten_query\":null}");
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-summary");
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
        // 近轮原文的预算 = 摘要的触发线，压到 20：夹具下每轮 8 个 token，于是第三轮
        // （24 > 20）触发、第四轮（压在 8 + 8 = 16）不触发、第五轮（24）又触发。
        registry.add("omniread.context.history-budget-tokens", () -> "20");
        registry.add("omniread.context.keep-recent-on-summarize", () -> "1");
    }

    @Autowired
    private WebApplicationContext context;
    @Autowired
    private AccountService accountService;
    @Autowired
    private ChatMessageMapper messageMapper;
    @Autowired
    private ChatSessionMapper sessionMapper;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        QUERY_CALLS.clear();
        SUMMARIZE_CALLS.clear();
        SUMMARIZE_FAILS.set(false);
        SUMMARY_SEQ.set(0);
        ANSWER_TEXT.set(ANSWER);
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(context.getBean(RequestIdFilter.class))
                .build();
    }

    @Test
    @DisplayName("首轮之后没有可压的内容：一次摘要调用都不发")
    void nothingToSummarizeOnTheFirstTurn() throws Exception {
        Cookie cookie = login(newAccount("summary-first"));
        String sessionId = createSession(cookie);

        ask(cookie, sessionId, "第一问");

        assertThat(SUMMARIZE_CALLS)
                .as("只有一轮，最近一轮之外没有任何内容——发出去就是一个空段（契约 minItems: 1）")
                .isEmpty();
        assertThat(sessionMapper.findById(sessionId).getSummaryUpto()).isNull();
    }

    @Test
    @DisplayName("回答落库之后触发：压最近几轮之外的那一段，summary 与 summary_upto 同一条写下去")
    void summaryFiresAfterTheAnswerLands() throws Exception {
        Cookie cookie = login(newAccount("summary-fire"));
        String sessionId = createSession(cookie);

        ask(cookie, sessionId, "第一问");
        ask(cookie, sessionId, "第二问");
        assertThat(SUMMARIZE_CALLS).as("攒下 16 ≤ 20，还都在窗口里，没有看不见的内容").isEmpty();

        ask(cookie, sessionId, "第三问");

        assertThat(SUMMARIZE_CALLS).hasSize(1);
        assertThat(SUMMARIZE_CALLS.get(0))
                .as("压的是前两轮，不含刚结束的第三轮（keep-recent 保留最近 1 轮）")
                .contains("\"content\":\"第一问\"")
                .contains("\"content\":\"第二问\"")
                .contains(ANSWER)
                .doesNotContain("第三问");

        ChatSession session = sessionMapper.findById(sessionId);
        assertThat(session.getSummary()).isEqualTo("摘要1");
        assertThat(session.getSummaryUpto())
                .as("覆盖到第二轮的答复那一条为止（记的是消息 id）")
                .isEqualTo(messageId(sessionId, 4));
        assertThat(session.getSummaryPromptVersion())
                .as("哪一版模板产的，与 summary 同一条 UPDATE 写下去")
                .isEqualTo("sum-v1");
    }

    @Test
    @DisplayName("下一轮把摘要带上：发给 Python 的 summary 就是刚存下的那份")
    void nextTurnCarriesTheSummary() throws Exception {
        Cookie cookie = login(newAccount("summary-carry"));
        String sessionId = createSession(cookie);

        ask(cookie, sessionId, "第一问");
        ask(cookie, sessionId, "第二问");
        ask(cookie, sessionId, "第三问");
        ask(cookie, sessionId, "第四问");

        assertThat(QUERY_CALLS.get(3))
                .as("整条链合上的地方：这一轮带的是上一轮压出来的摘要")
                .contains("\"summary\":\"摘要1\"");
    }

    @Test
    @DisplayName("压过的不再压：第二次只带新积累的那段，并把旧摘要一起交上去")
    void secondSummaryOnlyCarriesTheNewTurns() throws Exception {
        Cookie cookie = login(newAccount("summary-second"));
        String sessionId = createSession(cookie);

        ask(cookie, sessionId, "第一问");
        ask(cookie, sessionId, "第二问");
        ask(cookie, sessionId, "第三问");
        ask(cookie, sessionId, "第四问");
        assertThat(SUMMARIZE_CALLS)
                .as("第三轮压完只剩一轮没进摘要（keep-recent 之外为空），不发；"
                        + "第四轮攒出的那轮（8 + 8）还在窗口里，还是不触发")
                .hasSize(1);

        ask(cookie, sessionId, "第五问");

        assertThat(SUMMARIZE_CALLS).hasSize(2);
        assertThat(SUMMARIZE_CALLS.get(1))
                .as("第二次压的是第三、四轮，不是从头再来一遍")
                .contains("\"previous_summary\":\"摘要1\"")
                .contains("\"content\":\"第三问\"")
                .contains("\"content\":\"第四问\"")
                .doesNotContain("第一问")
                .doesNotContain("第二问");
        assertThat(sessionMapper.findById(sessionId).getSummaryUpto())
                .as("覆盖点往前推，不是从头再覆盖一遍")
                .isEqualTo(messageId(sessionId, 8));
    }

    @Test
    @DisplayName("摘要失败什么都不动：summary_upto 不推进，下一轮重试时把漏掉的那段一起压上")
    void failureDoesNotAdvanceTheCoverage() throws Exception {
        Cookie cookie = login(newAccount("summary-fail"));
        String sessionId = createSession(cookie);

        SUMMARIZE_FAILS.set(true);
        ask(cookie, sessionId, "第一问");
        ask(cookie, sessionId, "第二问");
        ask(cookie, sessionId, "第三问");
        assertThat(SUMMARIZE_CALLS).as("该触发是触发了，只是失败").hasSize(1);

        ChatSession failed = sessionMapper.findById(sessionId);
        assertThat(failed.getSummary()).isNull();
        assertThat(failed.getSummaryUpto())
                .as("失败不推进覆盖点——推进了就永远压不上这一段了")
                .isNull();

        SUMMARIZE_FAILS.set(false);
        ask(cookie, sessionId, "第四问");

        assertThat(SUMMARIZE_CALLS).hasSize(2);
        assertThat(SUMMARIZE_CALLS.get(1))
                .as("重试把漏掉的三轮一起压上，没有丢内容")
                .contains("\"content\":\"第一问\"")
                .contains("\"content\":\"第二问\"")
                .contains("\"content\":\"第三问\"")
                .contains("\"previous_summary\":null");
        assertThat(sessionMapper.findById(sessionId).getSummaryUpto()).isEqualTo(messageId(sessionId, 6));
    }

    @Test
    @DisplayName("空回答不留死结：它既不进历史也不进摘要，覆盖点照样往前走")
    void emptyAnswerDoesNotBrickTheSession() throws Exception {
        Cookie cookie = login(newAccount("summary-empty"));
        String sessionId = createSession(cookie);

        ask(cookie, sessionId, "第一问");
        // 模型一个 token 都没吐的那一轮：落库的是一条空正文的 assistant 消息。
        ANSWER_TEXT.set("");
        ask(cookie, sessionId, "第二问");
        ANSWER_TEXT.set(ANSWER);
        ask(cookie, sessionId, "第三问");
        ask(cookie, sessionId, "第四问");

        assertThat(SUMMARIZE_CALLS).as("摘要该触发还是要触发").isNotEmpty();
        assertThat(SUMMARIZE_CALLS).allSatisfy(body -> assertThat(body)
                .as("空正文带出去，整条摘要请求会被判 400——而它每次都带着同一条，"
                        + "summary_upto 就再也推不动了")
                .doesNotContain("\"content\":\"\""));
        assertThat(sessionMapper.findById(sessionId).getSummaryUpto())
                .as("覆盖点要跨过那条空消息往前走")
                .isEqualTo(messageId(sessionId, 6));
    }

    // ── 夹具 ──

    private long messageId(String sessionId, int seq) {
        return messageMapper.findBySession(sessionId).stream()
                .filter(message -> message.getSeq() == seq)
                .map(ChatMessage::getId)
                .findFirst()
                .orElseThrow(() -> new AssertionError("会话里没有 seq=" + seq + " 的消息"));
    }

    private User newAccount(String prefix) {
        return accountService.create(prefix + "-" + UUID.randomUUID(), PASSWORD);
    }

    private Cookie login(User user) throws Exception {
        MvcResult result = mvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"" + user.getUsername() + "\",\"password\":\"" + PASSWORD + "\"}"))
                .andReturn();
        return result.getResponse().getCookie(AuthCookies.NAME);
    }

    private String createSession(Cookie cookie) throws Exception {
        String body = mvc.perform(post("/api/v1/sessions").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"book_id\":1,\"level\":\"full\"}"))
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
        return body.replaceAll(".*\"id\":\"([^\"]+)\".*", "$1");
    }

    private void ask(Cookie cookie, String sessionId, String question) throws Exception {
        MvcResult result = mvc.perform(post("/api/v1/query").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"session_id\":\"" + sessionId + "\",\"book_id\":1,\"question\":\""
                                + question + "\",\"level\":\"full\"}"))
                .andReturn();
        assertThat(result.getResponse().getStatus())
                .as("响应体：" + result.getResponse().getContentAsString(StandardCharsets.UTF_8))
                .isEqualTo(200);
    }
}
