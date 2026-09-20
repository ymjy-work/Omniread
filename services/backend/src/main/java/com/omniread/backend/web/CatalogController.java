package com.omniread.backend.web;

import com.omniread.backend.contract.model.BookList;
import com.omniread.backend.contract.model.ChapterDetail;
import com.omniread.backend.contract.model.ChapterList;
import com.omniread.backend.gateway.RagGatewayClient;
import com.omniread.backend.gateway.RagStream;
import com.omniread.backend.orchestration.BookCatalog;
import com.omniread.backend.progress.FileProgressStore;
import com.omniread.backend.progress.Progress;
import com.omniread.backend.progress.ProgressWrite;
import com.omniread.backend.validation.RealmValidator;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.io.IOException;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 书目录来自 Python，阅读进度落在 Java 本地文件（M0-01 §1：Python 不保存用户进度）。
 *
 * 目录端点只做协议转发；进度端点是真正的读写，边界校验留在这一层。
 */
@RestController
@RequestMapping("/api/v1/books")
public class CatalogController {

    private final RagGatewayClient gateway;
    private final BookCatalog bookCatalog;
    private final FileProgressStore progressStore;

    public CatalogController(RagGatewayClient gateway, BookCatalog bookCatalog, FileProgressStore progressStore) {
        this.gateway = gateway;
        this.bookCatalog = bookCatalog;
        this.progressStore = progressStore;
    }

    @GetMapping
    public BookList listBooks() {
        return gateway.listBooks();
    }

    @GetMapping("/{bookId}/chapters")
    public ChapterList listChapters(@PathVariable int bookId) {
        return gateway.listChapters(bookId);
    }

    @GetMapping("/{bookId}/chapters/{chapterIndex}")
    public ChapterDetail getChapter(@PathVariable int bookId, @PathVariable int chapterIndex) {
        return gateway.getChapter(bookId, chapterIndex);
    }

    /**
     * 插图字节流，边读边写给客户端。
     *
     * 路径由客户端传来，目录穿越与扩展名白名单两道防护在 Python 侧（内部契约该端点的要求），
     * 网关只负责不落内存地转出去。这里同步写而不是走异步：流没结束就占住一个请求线程，
     * M0 单机阅读场景下这点代价换来的是「首字节立刻到、每片即刷」。
     */
    @GetMapping("/{bookId}/images/{*path}")
    public void getImage(@PathVariable int bookId, @PathVariable String path, HttpServletResponse response)
            throws IOException {
        RagStream stream = gateway.openImage(bookId, path.startsWith("/") ? path.substring(1) : path);
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType(stream.contentType() != null
                ? stream.contentType().toString()
                : MediaType.APPLICATION_OCTET_STREAM_VALUE);
        if (stream.contentLength() >= 0) {
            response.setContentLengthLong(stream.contentLength());
        }
        Streams.forward(stream, response.getOutputStream());
    }

    @GetMapping("/{bookId}/progress")
    public Progress getProgress(@PathVariable int bookId) {
        return progressStore.read(bookId);
    }

    @PutMapping("/{bookId}/progress")
    public Progress putProgress(@PathVariable int bookId, @RequestBody @Valid ProgressWrite body) {
        // 越界与否取决于该书的 chapter_count，只能由 Java 判（M0-01 §7）。
        RealmValidator.validateProgress(body.maxSeq(), bookCatalog.chapterCount(bookId));
        return progressStore.write(bookId, body.maxSeq());
    }
}
