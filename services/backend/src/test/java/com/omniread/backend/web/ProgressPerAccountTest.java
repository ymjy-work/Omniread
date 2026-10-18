package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.omniread.backend.user.AccountService;
import com.omniread.backend.user.AuthCookies;
import com.omniread.backend.user.User;
import com.omniread.backend.user.UserProgress;
import com.omniread.backend.user.UserProgressMapper;
import jakarta.servlet.http.Cookie;
import java.io.IOException;
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
 * 进度**真的按账户**：走完 真实上下文 → 拦截器 → 控制器 → SQLite 这一整条。
 *
 * <p>`CatalogControllerTest` 是 standalone，它自己把账户放进请求属性——那证明不了
 * 「拦截器放的那个键就是控制器读的那个键」。两个字符串写岔了，两边都不会报错，
 * 只会在真实请求上 500。这个类专门补这一层。
 *
 * <p>只做 GET：PUT 要 `chapter_count`，而那要问 Python（本机测试不接线），
 * 所以 PUT 的写入路径由 `CatalogControllerTest`（控制器层）与 `SqliteStoreTest`
 * （真库 + 真 mapper）两头覆盖，这里不重复。
 */
@SpringBootTest
class ProgressPerAccountTest {

    private static final String PASSWORD = "correct-horse-battery-staple";

    private static final Path DB_PATH = createDbPath();

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-progress-account");
            dir.toFile().deleteOnExit();
            return dir.resolve("omniread.db");
        } catch (IOException e) {
            throw new IllegalStateException("无法建临时目录", e);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", DB_PATH::toString);
        // 下游指向死端口：这些用例不该因为开发者本机开着 Python 而变绿或变红。
        registry.add("omniread.rag.base-url", () -> "http://127.0.0.1:1");
    }

    @Autowired
    private WebApplicationContext context;
    @Autowired
    private AccountService accountService;
    @Autowired
    private UserProgressMapper userProgressMapper;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    @Test
    @DisplayName("两个账户各读各的进度，互不可见")
    void eachAccountSeesItsOwnProgress() throws Exception {
        User alice = newAccount("progress-alice");
        User bob = newAccount("progress-bob");
        seed(alice.getId(), 100);
        seed(bob.getId(), 200);

        expectProgress(login(alice), 100);
        expectProgress(login(bob), 200);
    }

    @Test
    @DisplayName("没写过进度的账户读到第 1 章，而不是别人的值")
    void accountWithoutARowGetsTheInitialValue() throws Exception {
        User alice = newAccount("blank-alice");
        User bob = newAccount("blank-bob");
        seed(alice.getId(), 100);

        expectProgress(login(bob), 1);
    }

    // ── 夹具 ──

    private User newAccount(String prefix) {
        return accountService.create(prefix + "-" + UUID.randomUUID(), PASSWORD);
    }

    /** 直接落库：读路径才是这个类要验的，写路径两头都有覆盖。 */
    private void seed(long userId, int progress) {
        UserProgress row = new UserProgress();
        row.setUserId(userId);
        row.setBookId(1);
        row.setProgress(progress);
        userProgressMapper.upsert(row);
    }

    private void expectProgress(Cookie cookie, int progress) throws Exception {
        mvc.perform(get("/api/v1/books/1/progress").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.book_id").value(1))
                .andExpect(jsonPath("$.progress").value(progress));
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
}
