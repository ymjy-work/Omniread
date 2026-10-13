package com.omniread.backend.web;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.omniread.backend.config.ReadingProperties;
import com.omniread.backend.gateway.RagGatewayClient;
import com.omniread.backend.orchestration.BookCatalog;
import com.omniread.backend.progress.UserProgressStore;
import com.omniread.backend.reading.ReadingRange;
import com.omniread.backend.user.AuthenticatedUser;
import com.omniread.backend.user.UserProgress;
import com.omniread.backend.user.UserProgressMapper;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/**
 * 进度端点的对外行为：越界拒绝（上界要 chapter_count，只能由 Java 判）、字段名、
 * 以及**进度是按账户的**。
 *
 * <p>仍是 standalone：`bookCatalog.chapterCount` 必须打桩，否则这几条用例会变成
 * 「去问 Python 这本书有几章」。真实装配下的那一层（拦截器真的把账户放进了请求属性、
 * 真的落进了 SQLite）由 `ProgressPerAccountTest` 用全上下文验。
 */
class CatalogControllerTest {

    private static final int CHAPTER_COUNT = 193;

    private static final long ALICE = 1L;

    private static final long BOB = 2L;

    private BookCatalog bookCatalog;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        RagGatewayClient gateway = mock(RagGatewayClient.class);
        bookCatalog = mock(BookCatalog.class);
        UserProgressStore store = new UserProgressStore(new InMemoryProgressMapper());
        // 阅读范围在这个用例里全放开：它测的是进度与目录的边界校验，不是 E2 那条护栏
        ReadingRange readingRange = mock(ReadingRange.class);
        when(readingRange.rangeOf(1)).thenReturn(new ReadingRange.ChapterRange(1, 193));
        mvc = MockMvcBuilders.standaloneSetup(
                        new CatalogController(gateway, bookCatalog, store, readingRange, new ReadingProperties(1)))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    @DisplayName("进度超过 chapter_count 即 400，且不写库")
    void rejectsOutOfBoundsProgress() throws Exception {
        when(bookCatalog.chapterCount(1)).thenReturn(CHAPTER_COUNT);

        mvc.perform(progress(put("/api/v1/books/1/progress"), ALICE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"max_seq\":194}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("RAG_INVALID_REALM"));

        mvc.perform(progress(get("/api/v1/books/1/progress"), ALICE))
                .andExpect(jsonPath("$.max_seq").value(1));
    }

    @Test
    @DisplayName("进度小于 1 也是 400，但码与越上界不同：schema 约束归 REQUEST、语义归 REALM")
    void rejectsZero() throws Exception {
        when(bookCatalog.chapterCount(1)).thenReturn(CHAPTER_COUNT);

        // 下界 1 写在契约的 schema 里 → 请求本身不合法；上界要问书目录 → 语义检查。
        // 两者同为 400，前端按 code 分支，所以这条要钉住它们**不一样**。
        mvc.perform(progress(put("/api/v1/books/1/progress"), ALICE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"max_seq\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("RAG_INVALID_REQUEST"));
    }

    @Test
    @DisplayName("PUT 写进度、GET 读回，字段名与契约一致")
    void roundTripOverHttp() throws Exception {
        when(bookCatalog.chapterCount(1)).thenReturn(CHAPTER_COUNT);

        mvc.perform(progress(put("/api/v1/books/1/progress"), ALICE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"max_seq\":42}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.book_id").value(1))
                .andExpect(jsonPath("$.max_seq").value(42));

        mvc.perform(progress(get("/api/v1/books/1/progress"), ALICE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.book_id").value(1))
                .andExpect(jsonPath("$.max_seq").value(42));
    }

    @Test
    @DisplayName("没写过时 GET 返回第 1 章")
    void getBeforeAnyWrite() throws Exception {
        mvc.perform(progress(get("/api/v1/books/1/progress"), ALICE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.max_seq").value(1));
    }

    @Test
    @DisplayName("一个账户写进度，另一个账户读到的是初始值")
    void progressIsScopedToTheAccount() throws Exception {
        when(bookCatalog.chapterCount(1)).thenReturn(CHAPTER_COUNT);

        mvc.perform(progress(put("/api/v1/books/1/progress"), ALICE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"max_seq\":100}"))
                .andExpect(status().isOk());

        mvc.perform(progress(get("/api/v1/books/1/progress"), ALICE))
                .andExpect(jsonPath("$.max_seq").value(100));
        mvc.perform(progress(get("/api/v1/books/1/progress"), BOB))
                .andExpect(jsonPath("$.max_seq").value(1));
    }

    // ── 夹具 ──

    /** 进度端点要账户，而 standalone 不经过拦截器，所以属性由用例自己放。 */
    private static MockHttpServletRequestBuilder progress(MockHttpServletRequestBuilder builder, long userId) {
        return builder.requestAttr(
                AuthInterceptor.USER_ATTRIBUTE, new AuthenticatedUser(userId, "u" + userId, Instant.now()));
    }

    /**
     * 内存版 mapper。这几条用例要验的是「控制器怎么用它」，SQL 本身由 `SqliteStoreTest`
     * 对着真库验（含复合主键冲突与按用户隔离）。
     */
    private static final class InMemoryProgressMapper implements UserProgressMapper {

        private final Map<String, UserProgress> rows = new HashMap<>();

        @Override
        public int upsert(UserProgress progress) {
            rows.put(key(progress.getUserId(), progress.getBookId()), progress);
            return 1;
        }

        @Override
        public UserProgress find(long userId, int bookId) {
            return rows.get(key(userId, bookId));
        }

        @Override
        public List<UserProgress> findByUserId(long userId) {
            return rows.values().stream().filter(row -> row.getUserId() == userId).toList();
        }

        @Override
        public int deleteByUserId(long userId) {
            int before = rows.size();
            rows.entrySet().removeIf(entry -> entry.getValue().getUserId() == userId);
            return before - rows.size();
        }

        private static String key(long userId, int bookId) {
            return userId + "/" + bookId;
        }
    }
}
