package com.omniread.backend.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.omniread.backend.gateway.RagGatewayClient;
import com.omniread.backend.orchestration.BookCatalog;
import com.omniread.backend.progress.FileProgressStore;
import com.omniread.backend.progress.ProgressProperties;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/**
 * 进度端点的对外行为：越界拒绝（上界要 chapter_count，只能由 Java 判）与字段名都是契约的一部分。
 * 不启 Spring 上下文：Controller 的依赖只有下游入口与一个文件存储，standalone 足够。
 */
class CatalogControllerTest {

    private static final int CHAPTER_COUNT = 193;

    @TempDir
    Path dir;

    private BookCatalog bookCatalog;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        RagGatewayClient gateway = mock(RagGatewayClient.class);
        bookCatalog = mock(BookCatalog.class);
        FileProgressStore store = new FileProgressStore(new ProgressProperties(dir.resolve("progress.json")));
        mvc = MockMvcBuilders.standaloneSetup(new CatalogController(gateway, bookCatalog, store))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    @DisplayName("进度超过 chapter_count 即 400，且不落盘")
    void rejectsOutOfBoundsProgress() throws Exception {
        when(bookCatalog.chapterCount(1)).thenReturn(CHAPTER_COUNT);

        mvc.perform(put("/api/v1/books/1/progress")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"max_seq\":194}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("RAG_INVALID_REALM"));

        assertThat(Files.exists(dir.resolve("progress.json"))).isFalse();
    }

    @Test
    @DisplayName("进度小于 1 同样 400")
    void rejectsZero() throws Exception {
        when(bookCatalog.chapterCount(1)).thenReturn(CHAPTER_COUNT);

        mvc.perform(put("/api/v1/books/1/progress")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"max_seq\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("RAG_INVALID_REALM"));
    }

    @Test
    @DisplayName("PUT 写进度、GET 读回，字段名与契约一致")
    void roundTripOverHttp() throws Exception {
        when(bookCatalog.chapterCount(1)).thenReturn(CHAPTER_COUNT);

        mvc.perform(put("/api/v1/books/1/progress")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"max_seq\":42}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.book_id").value(1))
                .andExpect(jsonPath("$.max_seq").value(42));

        mvc.perform(get("/api/v1/books/1/progress"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.book_id").value(1))
                .andExpect(jsonPath("$.max_seq").value(42));
    }

    @Test
    @DisplayName("没写过时 GET 返回第 1 章")
    void getBeforeAnyWrite() throws Exception {
        mvc.perform(get("/api/v1/books/1/progress"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.max_seq").value(1));
    }
}
