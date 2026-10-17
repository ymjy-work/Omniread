package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.omniread.backend.session.ChatMessageMapper;
import com.omniread.backend.session.ChatMessageStore;
import com.omniread.backend.session.ChatSessionMapper;
import com.omniread.backend.session.SessionService;
import com.omniread.backend.user.AccountService;
import com.omniread.backend.user.AuthCookies;
import com.omniread.backend.user.User;
import jakarta.servlet.http.Cookie;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
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
 * 会话的列表 / 新建 / 详情 / 删除，走真实上下文（拦截器 + SQLite + 外键级联）。
 *
 * <p>用全上下文而不是 standalone：这一段的正确性有一半在**归属**上
 * （谁的会话、跨用户 403），而归属是靠拦截器放进请求属性的那个账户决定的——
 * standalone 得自己放，于是恰好把要验的那一步替换成了测试自己写的一行。
 *
 * <p>删会话要过级联，那依赖连接串里的 `foreign_keys=on`，也只有在真库上才验得到。
 */
@SpringBootTest
class SessionCrudTest {

    private static final String PASSWORD = "correct-horse-battery-staple";

    private static final String CSRF = AuthInterceptor.CSRF_HEADER;

    private static final Path DB_PATH = createDbPath();

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-session-crud");
            dir.toFile().deleteOnExit();
            return dir.resolve("omniread.db");
        } catch (IOException e) {
            throw new IllegalStateException("无法建临时目录", e);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", DB_PATH::toString);
        // 会话 CRUD 是纯本地动作，不该因为开发者本机开着 Python 而变绿或变红。
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

    // ── 新建与列表 ──

    @Test
    @DisplayName("新建返回 201 与契约字段；还没问过时是占位标题，forked_from 为空")
    void createReturnsTheContractShape() throws Exception {
        Cookie cookie = login(newAccount("create"));

        mvc.perform(post("/api/v1/sessions").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"book_id\":1,\"level\":\"past\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isString())
                .andExpect(jsonPath("$.book_id").value(1))
                .andExpect(jsonPath("$.title").value(SessionService.PLACEHOLDER_TITLE))
                .andExpect(jsonPath("$.level").value("past"))
                .andExpect(jsonPath("$.forked_from").doesNotExist())
                .andExpect(jsonPath("$.created_at").isString())
                .andExpect(jsonPath("$.last_active_at").isString());
    }

    @Test
    @DisplayName("新建的会话出现在自己的列表里，不在别人的列表里")
    void listShowsOnlyYourOwnSessions() throws Exception {
        Cookie alice = login(newAccount("list-alice"));
        Cookie bob = login(newAccount("list-bob"));
        String sessionId = createSession(alice, "full");

        mvc.perform(get("/api/v1/sessions").cookie(alice))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sessions.length()").value(1))
                .andExpect(jsonPath("$.sessions[0].id").value(sessionId))
                .andExpect(jsonPath("$.sessions[0].level").value("full"));

        mvc.perform(get("/api/v1/sessions").cookie(bob))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sessions.length()").value(0));
    }

    @Test
    @DisplayName("列表按最近活跃倒序——前端靠它决定「继续上次」是哪一条")
    void listIsOrderedByRecentActivity() throws Exception {
        Cookie cookie = login(newAccount("order"));
        String first = createSession(cookie, "past");
        String second = createSession(cookie, "past");
        // 两条的 last_active_at 在创建时几乎相同，把先建的那条拨到更晚：
        // 验的是 SQL 的 ORDER BY，而不是「创建得晚就排前面」这次巧合。
        sessionMapper.touch(first, Instant.now().plusSeconds(60).toString());

        mvc.perform(get("/api/v1/sessions").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sessions[0].id").value(first))
                .andExpect(jsonPath("$.sessions[1].id").value(second));
    }

    // ── 详情 ──

    @Test
    @DisplayName("详情含消息，按 seq 升序，且不带 meta")
    void detailCarriesMessagesWithoutMeta() throws Exception {
        Cookie cookie = login(newAccount("detail"));
        String sessionId = createSession(cookie, "past");
        messageStore.append(sessionId, "user", "第一问", 3, null);
        messageStore.append(sessionId, "assistant", "第一答", 5, "{\"citations\":[1]}");

        String body = mvc.perform(get("/api/v1/sessions/" + sessionId).cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(sessionId))
                .andExpect(jsonPath("$.messages.length()").value(2))
                .andExpect(jsonPath("$.messages[0].seq").value(1))
                .andExpect(jsonPath("$.messages[0].role").value("user"))
                .andExpect(jsonPath("$.messages[0].content").value("第一问"))
                .andExpect(jsonPath("$.messages[1].seq").value(2))
                .andExpect(jsonPath("$.messages[1].role").value("assistant"))
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);

        // meta 是内部诊断列（引用编号 / 改写前后 / 模型与 prompt 版本），下发出去
        // 就会变成前端依赖的事实契约，而那几样随时可能变。
        assertThat(body).doesNotContain("meta").doesNotContain("citations");
    }

    // ── 归属：403 与 404 是两件事 ──

    @Test
    @DisplayName("别人的会话：详情与删除都是 403，不是 404")
    void otherPeoplesSessionsAreForbidden() throws Exception {
        Cookie alice = login(newAccount("owner-alice"));
        Cookie bob = login(newAccount("owner-bob"));
        String sessionId = createSession(alice, "past");

        mvc.perform(get("/api/v1/sessions/" + sessionId).cookie(bob))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("RAG_FORBIDDEN"));

        mvc.perform(delete("/api/v1/sessions/" + sessionId).cookie(bob).header(CSRF, "1"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("RAG_FORBIDDEN"));

        // 删不掉就是真没删掉：原会话还在。
        assertThat(sessionMapper.findById(sessionId)).isNotNull();
    }

    @Test
    @DisplayName("不存在的会话：404，与「不是你的」分开")
    void unknownSessionsAreNotFound() throws Exception {
        Cookie cookie = login(newAccount("missing"));

        mvc.perform(get("/api/v1/sessions/" + UUID.randomUUID()).cookie(cookie))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RAG_NOT_FOUND"));

        mvc.perform(delete("/api/v1/sessions/" + UUID.randomUUID()).cookie(cookie).header(CSRF, "1"))
                .andExpect(status().isNotFound());
    }

    // ── 删除 ──

    @Test
    @DisplayName("删除会话连同它的消息一起删（外键级联）")
    void deleteCascadesMessages() throws Exception {
        Cookie cookie = login(newAccount("cascade"));
        String sessionId = createSession(cookie, "past");
        messageStore.append(sessionId, "user", "问", 1, null);
        messageStore.append(sessionId, "assistant", "答", 1, null);
        assertThat(messageMapper.countBySession(sessionId)).isEqualTo(2);

        mvc.perform(delete("/api/v1/sessions/" + sessionId).cookie(cookie).header(CSRF, "1"))
                .andExpect(status().isNoContent());

        mvc.perform(get("/api/v1/sessions/" + sessionId).cookie(cookie))
                .andExpect(status().isNotFound());
        assertThat(messageMapper.countBySession(sessionId)).isZero();
        assertThat(messageMapper.findBySession(sessionId)).isEmpty();
    }

    // ── 入参 ──

    @Test
    @DisplayName("level 不是 past/full 即 400，缺 book_id 也一样")
    void rejectsMalformedCreateBodies() throws Exception {
        Cookie cookie = login(newAccount("malformed"));

        mvc.perform(post("/api/v1/sessions").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"book_id\":1,\"level\":\"whatever\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("RAG_INVALID_REQUEST"));

        mvc.perform(post("/api/v1/sessions").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"level\":\"past\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("RAG_INVALID_REQUEST"));
    }

    // ── 改名 ──

    @Test
    @DisplayName("改名返回更新后的摘要，列表里读到的也是新名字")
    void renameUpdatesTheTitle() throws Exception {
        Cookie cookie = login(newAccount("rename"));
        String sessionId = createSession(cookie, "past");

        mvc.perform(put("/api/v1/sessions/" + sessionId + "/title").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"第三章伏笔整理\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(sessionId))
                .andExpect(jsonPath("$.title").value("第三章伏笔整理"));

        mvc.perform(get("/api/v1/sessions").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sessions[0].title").value("第三章伏笔整理"));
    }

    @Test
    @DisplayName("标题的空白压成单个空格：带换行的标题会把列表那一行撑成两行")
    void renameFlattensWhitespace() throws Exception {
        Cookie cookie = login(newAccount("rename-space"));
        String sessionId = createSession(cookie, "past");

        mvc.perform(put("/api/v1/sessions/" + sessionId + "/title").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"  前后  空白\\n换行  \"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("前后 空白 换行"));
    }

    @Test
    @DisplayName("空标题与超长都是 400；上限按**码点**算，20 个 emoji（40 个 char）是合法的")
    void renameRejectsBadTitles() throws Exception {
        Cookie cookie = login(newAccount("rename-bad"));
        String sessionId = createSession(cookie, "past");

        for (String bad : new String[] {"{\"title\":\"   \"}", "{\"title\":\"\"}", "{\"title\":\"" + "字".repeat(21) + "\"}"}) {
            mvc.perform(put("/api/v1/sessions/" + sessionId + "/title").cookie(cookie).header(CSRF, "1")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(bad))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code").value("RAG_INVALID_REQUEST"));
        }

        // 20 个 emoji 是 20 个码点、40 个 char：按 char 判会误拒，所以这条必须过
        String emoji = "😀".repeat(20);
        assertThat(emoji.length()).isEqualTo(40);
        mvc.perform(put("/api/v1/sessions/" + sessionId + "/title").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"" + emoji + "\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value(emoji));
    }

    @Test
    @DisplayName("改名也分 403 与 404：别人的会话改不了，不存在的返回没找到")
    void renameSplitsForbiddenFromNotFound() throws Exception {
        Cookie alice = login(newAccount("rename-alice"));
        Cookie bob = login(newAccount("rename-bob"));
        String sessionId = createSession(alice, "past");

        mvc.perform(put("/api/v1/sessions/" + sessionId + "/title").cookie(bob).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"偷改\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("RAG_FORBIDDEN"));
        assertThat(sessionMapper.findById(sessionId).getTitle())
                .isEqualTo(SessionService.PLACEHOLDER_TITLE);

        mvc.perform(put("/api/v1/sessions/" + UUID.randomUUID() + "/title").cookie(alice).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"随便\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RAG_NOT_FOUND"));
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
        assertThat(cookie).as("登录成功必须带回 cookie").isNotNull();
        return cookie;
    }

    /** 建一个会话并返回它的 id。 */
    private String createSession(Cookie cookie, String level) throws Exception {
        String body = mvc.perform(post("/api/v1/sessions").cookie(cookie).header(CSRF, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"book_id\":1,\"level\":\"" + level + "\"}"))
                .andExpect(status().isCreated())
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
        return body.replaceAll(".*\"id\":\"([^\"]+)\".*", "$1");
    }
}
