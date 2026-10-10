package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.omniread.backend.session.ChatMessageMapper;
import com.omniread.backend.session.ChatMessageStore;
import com.omniread.backend.session.ChatSessionMapper;
import com.omniread.backend.user.AccountService;
import com.omniread.backend.user.AuthCookies;
import com.omniread.backend.user.User;
import jakarta.servlet.http.Cookie;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
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
 * 切档位分叉：**复制**父会话截至 `at_seq` 的消息进新会话，父会话一律不动。
 *
 * <p>全上下文，因为要验的一半是「原会话真的没动」——那要真库真事务，
 * 而不是看返回值对不对。
 */
@SpringBootTest
class SessionForkTest {

    private static final String PASSWORD = "correct-horse-battery-staple";

    private static final String CSRF = AuthInterceptor.CSRF_HEADER;

    private static final Path DB_PATH = createDbPath();

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-session-fork");
            dir.toFile().deleteOnExit();
            return dir.resolve("omniread.db");
        } catch (IOException e) {
            throw new IllegalStateException("无法建临时目录", e);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", DB_PATH::toString);
        registry.add("omniread.rag.base-url", () -> "http://127.0.0.1:1");
    }

    @Autowired
    private WebApplicationContext context;
    @Autowired
    private AccountService accountService;
    @Autowired
    private ChatSessionMapper sessionMapper;
    @Autowired
    private ChatMessageMapper messageMapper;
    @Autowired
    private ChatMessageStore messageStore;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    @Test
    @DisplayName("分叉复制前 K 条、seq 从 1 重排、原会话一条不动")
    void forkCopiesUpToTheAlignedPoint() throws Exception {
        Cookie cookie = login(newAccount("fork"));
        String parent = createSession(cookie, "past");
        twoTurns(parent);

        // at_seq=2 落在第一轮的 assistant 上，复制的就是前两条。
        String forked = fork(cookie, parent, "full", "2");

        mvc.perform(get("/api/v1/sessions/" + forked).cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.level").value("full"))
                .andExpect(jsonPath("$.forked_from").value(parent))
                .andExpect(jsonPath("$.messages.length()").value(2))
                .andExpect(jsonPath("$.messages[0].seq").value(1))
                .andExpect(jsonPath("$.messages[0].content").value("问一"))
                .andExpect(jsonPath("$.messages[1].seq").value(2))
                .andExpect(jsonPath("$.messages[1].content").value("答一"));

        // 父会话：档位与四条消息都在，一条没少。
        mvc.perform(get("/api/v1/sessions/" + parent).cookie(cookie))
                .andExpect(jsonPath("$.level").value("past"))
                .andExpect(jsonPath("$.messages.length()").value(4));
        assertThat(messageMapper.countBySession(parent)).isEqualTo(4);
    }

    @Test
    @DisplayName("at_seq 落在 user 上：退到前一条 assistant，复制 2 条而不是 3 条")
    void forkAlignsDownToACompleteTurn() throws Exception {
        Cookie cookie = login(newAccount("align"));
        String parent = createSession(cookie, "past");
        twoTurns(parent);

        String forked = fork(cookie, parent, "full", "3");

        // forked_at_seq 记的是父会话那边对齐后的 seq，不是请求里传的那个。
        assertThat(sessionMapper.findById(forked).getForkedAtSeq()).isEqualTo(2);
        mvc.perform(get("/api/v1/sessions/" + forked).cookie(cookie))
                .andExpect(jsonPath("$.messages.length()").value(2));
    }

    @Test
    @DisplayName("不给 at_seq 就继承到当前点")
    void forkDefaultsToNow() throws Exception {
        Cookie cookie = login(newAccount("default"));
        String parent = createSession(cookie, "past");
        twoTurns(parent);

        String forked = fork(cookie, parent, "full", null);

        mvc.perform(get("/api/v1/sessions/" + forked).cookie(cookie))
                .andExpect(jsonPath("$.messages.length()").value(4));
    }

    @Test
    @DisplayName("档位与原会话相同即 400——不静默给一个副本")
    void forkRefusesTheSameLevel() throws Exception {
        Cookie cookie = login(newAccount("same"));
        String parent = createSession(cookie, "past");

        mvc.perform(post("/api/v1/sessions/" + parent + "/fork").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"level\":\"past\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("RAG_INVALID_REQUEST"));
    }

    @Test
    @DisplayName("别人的会话分不了叉（403），不存在的会话是 404")
    void forkRespectsOwnership() throws Exception {
        Cookie alice = login(newAccount("fork-owner"));
        Cookie bob = login(newAccount("fork-other"));
        String parent = createSession(alice, "past");

        mvc.perform(post("/api/v1/sessions/" + parent + "/fork").cookie(bob).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"level\":\"full\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("RAG_FORBIDDEN"));

        mvc.perform(post("/api/v1/sessions/" + UUID.randomUUID() + "/fork").cookie(alice).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"level\":\"full\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RAG_NOT_FOUND"));
    }

    @Test
    @DisplayName("at_seq 小于 1 是 400：越界是算出来的，传 0 是传错了")
    void forkRejectsZeroAtSeq() throws Exception {
        Cookie cookie = login(newAccount("zero"));
        String parent = createSession(cookie, "past");

        mvc.perform(post("/api/v1/sessions/" + parent + "/fork").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"level\":\"full\",\"at_seq\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("RAG_INVALID_REQUEST"));
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
        Cookie cookie = result.getResponse().getCookie(AuthCookies.NAME);
        assertThat(cookie).isNotNull();
        return cookie;
    }

    private String createSession(Cookie cookie, String level) throws Exception {
        return idOf(post("/api/v1/sessions").cookie(cookie).header(CSRF, "1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"book_id\":1,\"level\":\"" + level + "\"}"), 201);
    }

    private String fork(Cookie cookie, String parent, String level, String atSeq) throws Exception {
        String body = "{\"level\":\"" + level + "\"" + (atSeq == null ? "" : ",\"at_seq\":" + atSeq) + "}";
        return idOf(post("/api/v1/sessions/" + parent + "/fork").cookie(cookie).header(CSRF, "1")
                .contentType(MediaType.APPLICATION_JSON).content(body), 201);
    }

    private String idOf(org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request, int expected)
            throws Exception {
        String body = mvc.perform(request)
                .andExpect(status().is(expected))
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
        return body.replaceAll(".*\"id\":\"([^\"]+)\".*", "$1");
    }

    /** 一问一答两轮：seq 1..4。 */
    private void twoTurns(String sessionId) {
        messageStore.append(sessionId, "user", "问一", 1, null);
        messageStore.append(sessionId, "assistant", "答一", 1, null);
        messageStore.append(sessionId, "user", "问二", 1, null);
        messageStore.append(sessionId, "assistant", "答二", 1, null);
    }
}
