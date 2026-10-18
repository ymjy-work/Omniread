package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.omniread.backend.user.AccountService;
import com.omniread.backend.user.AuthCookies;
import com.omniread.backend.user.AuthSession;
import com.omniread.backend.user.AuthSessionMapper;
import com.omniread.backend.user.AuthTokens;
import com.omniread.backend.user.User;
import jakarta.servlet.http.Cookie;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

/**
 * 登录门在**真实注册路径**上的行为：未登录的 `/api/v1/*` 一律 401、健康检查与登录除外、
 * 写操作要求自定义头、退出后立刻失效。
 *
 * <p>为什么不用 {@code MockMvcBuilders.standaloneSetup}（{@code CatalogControllerTest} 那种）：
 * standalone 不经过拦截器与过滤器，**恰好把这套用例要验的东西全部跳过**——
 * 拦截器没挂上、路径模式写错、例外名单写反，standalone 一律通过。
 * 这里用 {@code webAppContextSetup} 起真实上下文：容器里注册的拦截器、过滤器、
 * 处理器映射都是生产那一套。（Boot 4.1 的 classpath 上没有 {@code @AutoConfigureMockMvc}，
 * 而 {@code webAppContextSetup} 本来就不需要它。）
 */
@SpringBootTest
class AuthGateTest {

    private static final String PASSWORD = "correct-horse-battery-staple";

    private static final String CSRF_HEADER = AuthInterceptor.CSRF_HEADER;

    /** 与拦截器里那份同义：安全方法不要求 CSRF 头。 */
    private static final Set<String> SAFE_METHODS = Set.of("GET", "HEAD", "OPTIONS");

    private static final Path DB_PATH = createDbPath();

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-auth-gate");
            dir.toFile().deleteOnExit();
            return dir.resolve("omniread.db");
        } catch (IOException e) {
            throw new IllegalStateException("无法建临时目录", e);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", DB_PATH::toString);
        // 下游 Python 指向一个必定连不上的端口。默认的 127.0.0.1:8000 在开发者本机
        // **可能真的有服务在跑**，那样「过了门禁之后会怎样」就会随本机状态而变。
        registry.add("omniread.rag.base-url", () -> "http://127.0.0.1:1");
    }

    @Autowired
    private WebApplicationContext context;
    @Autowired
    private AccountService accountService;
    @Autowired
    private AuthSessionMapper authSessionMapper;
    @Autowired
    private AuthTokens tokens;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    // ── 门禁 ──

    @Test
    @DisplayName("没带 cookie 时 /api/v1/* 一律 401，错误体形状与其它错误一致")
    void unauthenticatedIsRejected() throws Exception {
        for (String path : new String[] {"/api/v1/books", "/api/v1/auth/me", "/api/v1/sessions"}) {
            mvc.perform(get(path))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.code").value("RAG_UNAUTHENTICATED"))
                    .andExpect(jsonPath("$.request_id").isString())
                    .andExpect(jsonPath("$.message").isString());
        }
    }

    @Test
    @DisplayName("逐个验证：注册表里每个 /api/v1 的每条方法都真的在门内")
    void everyRegisteredRouteIsBehindTheGate() throws Exception {
        // 手写路径清单的用例只覆盖它列出来的那几条：新加一个控制器、或者把某个端点挪到
        // 另一个前缀下，被漏掉的那条不会红。这里改成从注册表枚举——**新端点自动进入覆盖**。
        RequestMappingHandlerMapping mapping = context.getBean(RequestMappingHandlerMapping.class);
        Set<String> exempt = Set.of("/api/v1/health", "/api/v1/auth/login");
        List<String> checked = new ArrayList<>();

        for (RequestMappingInfo info : mapping.getHandlerMethods().keySet()) {
            Set<RequestMethod> methods = info.getMethodsCondition().getMethods();
            if (methods.isEmpty()) {
                methods = Set.of(RequestMethod.GET);
            }
            for (String pattern : info.getPatternValues()) {
                if (!pattern.startsWith("/api/v1/") || exempt.contains(pattern)) {
                    continue;
                }
                for (RequestMethod method : methods) {
                    // 既不带 cookie 也不带 CSRF 头：拦下它的必须是登录门（401），
                    // 而不是 CSRF 判定（403）或参数校验（400）——顺序反了这里就红。
                    mvc.perform(request(HttpMethod.valueOf(method.name()), concretize(pattern)))
                            .andExpect(status().isUnauthorized());
                    checked.add(method + " " + pattern);
                }
            }
        }

        assertThat(checked)
                .as("一条 /api/v1 的路由都没枚举到，说明这条用例已经退化成了空跑")
                .hasSizeGreaterThanOrEqualTo(8)
                .doesNotContainAnyElementsOf(exempt);
    }

    /** 把 `/books/{bookId}/chapters/{chapterIndex}` 变成可以直接请求的路径。 */
    private static String concretize(String pattern) {
        return pattern.replaceAll("\\{[^}]*\\}", "1");
    }

    @Test
    @DisplayName("逐个验证：注册表里每条 /api/v1 的写操作都要求 CSRF 头（登录除外）")
    void everyRegisteredWriteRequiresTheCsrfHeader() throws Exception {
        // 上一条钉「进得来」，这条钉「写操作多一道」。两条合起来才说明契约里那 7 条
        // `$ref: CsrfHeader` 与实现里的路由**是同一批**——手写清单做不到这一点，
        // 而契约与实现各写一份清单、只改一处，正是这类漂移的典型来源。
        Cookie cookie = login(newAccount("csrf-sweep"));
        RequestMappingHandlerMapping mapping = context.getBean(RequestMappingHandlerMapping.class);
        Set<String> exempt = Set.of("/api/v1/health", "/api/v1/auth/login");
        List<String> checked = new ArrayList<>();

        for (RequestMappingInfo info : mapping.getHandlerMethods().keySet()) {
            Set<RequestMethod> methods = info.getMethodsCondition().getMethods();
            for (String pattern : info.getPatternValues()) {
                if (!pattern.startsWith("/api/v1/") || exempt.contains(pattern)) {
                    continue;
                }
                for (RequestMethod method : methods) {
                    if (SAFE_METHODS.contains(method.name())) {
                        continue;
                    }
                    // 带着 cookie、**不带** CSRF 头：拦下它的必须是 CSRF 判定（403）。
                    // 请求体是空的也无所谓——拦截器在参数解析之前就把它挡了，
                    // 所以这条不需要为每条路由编一份合法载荷。
                    mvc.perform(request(HttpMethod.valueOf(method.name()), concretize(pattern))
                                    .cookie(cookie))
                            .andExpect(status().isForbidden())
                            .andExpect(jsonPath("$.code").value("RAG_FORBIDDEN"));
                    checked.add(method + " " + pattern);
                }
            }
        }

        assertThat(checked)
                .as("一条写操作都没枚举到，说明这条用例已经退化成了空跑")
                .hasSizeGreaterThanOrEqualTo(5)
                .doesNotContainAnyElementsOf(exempt);
    }

    @Test
    @DisplayName("两个例外：健康检查与登录本身不需要登录")
    void healthAndLoginAreExempt() throws Exception {
        mvc.perform(get("/api/v1/health")).andExpect(status().isOk());

        String username = newAccount("exempt");
        mvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(username, PASSWORD)))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("未登录时的写操作也是 401 而不是 403：401 优先于 CSRF 判定")
    void unauthenticatedWriteIsStill401() throws Exception {
        // 这条钉的是**判定顺序**。反过来的话，部署验收里「未登录请求 /api/v1/* 均返回 401，
        // 逐个验证」就会出现一个「POST 且没带头时是 403」的例外。
        mvc.perform(put("/api/v1/books/1/progress")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"progress\":5}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("RAG_UNAUTHENTICATED"));
    }

    @Test
    @DisplayName("退出也在门内：没登录时调退出是 401，不是幂等的 204")
    void logoutRequiresBeingLoggedIn() throws Exception {
        mvc.perform(post("/api/v1/auth/logout").header(CSRF_HEADER, "1"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("RAG_UNAUTHENTICATED"));
    }

    @Test
    @DisplayName("写操作缺自定义头即 403；带上就放行到下游")
    void writeRequiresTheCsrfHeader() throws Exception {
        Cookie cookie = login(newAccount("csrf"));

        mvc.perform(put("/api/v1/books/1/progress")
                        .cookie(cookie)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"progress\":5}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("RAG_FORBIDDEN"));

        // 带上头之后就不再被 CSRF 拦下——它走到了下游，而下游在本用例里指向死端口。
        // 这条正向对照是必要的：没有它，一个「永远返回 403」的实现也能让上面那半条通过。
        mvc.perform(put("/api/v1/books/1/progress")
                        .cookie(cookie)
                        .header(CSRF_HEADER, "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"progress\":5}"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.code").value("RAG_UNAVAILABLE"));
    }

    // ── 登录 / 退出 / 当前账户 ──

    @Test
    @DisplayName("登录种下 cookie：HttpOnly + SameSite=Strict + Max-Age，响应体里没有 token")
    void loginSetsTheCookieAndNothingElse() throws Exception {
        String username = newAccount("cookie");

        MvcResult result = mvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(username, PASSWORD)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value(username))
                .andReturn();

        String setCookie = result.getResponse().getHeader("Set-Cookie");
        assertThat(setCookie)
                .as("cookie 的三个属性缺一不可：读不到、不跨站、会过期")
                .contains(AuthCookies.NAME + "=")
                .contains("HttpOnly")
                .contains("SameSite=Strict")
                .contains("Max-Age=");

        Cookie cookie = result.getResponse().getCookie(AuthCookies.NAME);
        assertThat(cookie).isNotNull();
        assertThat(result.getResponse().getContentAsString(StandardCharsets.UTF_8))
                .as("token 只该出现在 cookie 里，不该在响应体里再给一份")
                .doesNotContain(cookie.getValue());
    }

    @Test
    @DisplayName("登录后 /auth/me 返回账户名与 ISO-8601 的到期时刻")
    void meReturnsTheCurrentAccount() throws Exception {
        String username = newAccount("me");
        Cookie cookie = login(username);

        String body = mvc.perform(get("/api/v1/auth/me").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value(username))
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);

        // 到期时刻是可解析的 ISO-8601：前端拿它做本地登出，解析不了就等于没有这个字段。
        String expiresAt = body.replaceAll(".*\"expires_at\":\"([^\"]+)\".*", "$1");
        assertThat(Instant.parse(expiresAt)).isAfter(Instant.now());
    }

    @Test
    @DisplayName("账户不存在与口令错返回逐字相同的 401——否则就是枚举账户名的接口")
    void bothFailureKindsLookIdentical() throws Exception {
        String username = newAccount("enumeration");

        String wrongPassword = normalizedFailure(username, "not-the-password");
        String noSuchAccount = normalizedFailure("ghost-" + UUID.randomUUID(), PASSWORD);

        assertThat(wrongPassword)
                .as("两种失败在响应上必须不可区分")
                .isEqualTo(noSuchAccount);
    }

    @Test
    @DisplayName("退出后原 cookie 立刻失效，服务端那条登录会话行也没了")
    void logoutInvalidatesImmediately() throws Exception {
        Cookie cookie = login(newAccount("logout"));

        mvc.perform(post("/api/v1/auth/logout").cookie(cookie).header(CSRF_HEADER, "1"))
                .andExpect(status().isNoContent());

        mvc.perform(get("/api/v1/auth/me").cookie(cookie)).andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("过期的登录态一律 401，即使 cookie 还在")
    void expiredSessionIsRejected() throws Exception {
        User user = createAccount("expired");
        String token = tokens.newToken();
        AuthSession expired = new AuthSession();
        expired.setTokenHash(tokens.hash(token));
        expired.setUserId(user.getId());
        expired.setCreatedAt(Instant.now().minus(Duration.ofHours(9)).toString());
        expired.setExpiresAt(Instant.now().minus(Duration.ofHours(1)).toString());
        authSessionMapper.insert(expired);

        mvc.perform(get("/api/v1/auth/me").cookie(new Cookie(AuthCookies.NAME, token)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("RAG_UNAUTHENTICATED"));
    }

    @Test
    @DisplayName("停用账户后，手里的 cookie 立刻不认（D15 的登录态失效）")
    void disablingAnAccountKillsItsSessions() throws Exception {
        User user = createAccount("disabled");
        Cookie cookie = login(user.getUsername());

        accountService.disableAndPurge(user.getId());

        mvc.perform(get("/api/v1/auth/me").cookie(cookie)).andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("缺字段的登录体是 400 RAG_INVALID_REQUEST，不是 401")
    void malformedLoginBodyIsABadRequest() throws Exception {
        mvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"someone\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("RAG_INVALID_REQUEST"));
    }

    // ── 夹具 ──

    /** 唯一名：同一个测试上下文里多条用例共用一个库。 */
    private String newAccount(String prefix) {
        return createAccount(prefix).getUsername();
    }

    /** 需要账户 id 的用例用这个（停用、直接插登录会话行）。 */
    private User createAccount(String prefix) {
        return accountService.create(prefix + "-" + UUID.randomUUID(), PASSWORD);
    }

    private Cookie login(String username) throws Exception {
        MvcResult result = mvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(username, PASSWORD)))
                .andExpect(status().isOk())
                .andReturn();
        Cookie cookie = result.getResponse().getCookie(AuthCookies.NAME);
        assertThat(cookie).as("登录成功必须带回 cookie").isNotNull();
        return cookie;
    }

    private String normalizedFailure(String username, String password) throws Exception {
        String body = mvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(username, password)))
                .andExpect(status().isUnauthorized())
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
        // request_id 每次不同，抹掉它再比——要比的是「除它之外还有没有差别」。
        return body.replaceAll(Pattern.quote("\"request_id\":\"") + "[^\"]*", "\"request_id\":\"...");
    }

    private static String loginBody(String username, String password) {
        return "{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}";
    }
}
