package com.omniread.backend.web;

import com.omniread.backend.config.ReadingProperties;
import com.omniread.backend.contract.model.BookList;
import com.omniread.backend.contract.model.ChapterDetail;
import com.omniread.backend.contract.model.ChapterList;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import com.omniread.backend.gateway.RagGatewayClient;
import com.omniread.backend.gateway.RagStream;
import com.omniread.backend.orchestration.BookCatalog;
import com.omniread.backend.progress.Progress;
import com.omniread.backend.progress.ProgressWrite;
import com.omniread.backend.progress.UserProgressStore;
import com.omniread.backend.reading.ReadingRange;
import com.omniread.backend.user.AuthenticatedUser;
import com.omniread.backend.validation.RealmValidator;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.io.IOException;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 书目录来自 Python；阅读进度按账户落在 Java 的 SQLite 里（Python 不保存用户进度）。
 *
 * 目录端点只做协议转发；进度端点是真正的读写，边界校验留在这一层。
 * 进度**必须带账户**：它是「读到哪」这件事的一部分，缺了 user_id 就退化成所有人共享一份。
 */
@RestController
@RequestMapping("/api/v1/books")
public class CatalogController {

    private final RagGatewayClient gateway;
    private final BookCatalog bookCatalog;
    private final UserProgressStore progressStore;
    private final ReadingRange readingRange;
    private final ReadingProperties readingProperties;

    public CatalogController(RagGatewayClient gateway, BookCatalog bookCatalog, UserProgressStore progressStore,
            ReadingRange readingRange, ReadingProperties readingProperties) {
        this.gateway = gateway;
        this.bookCatalog = bookCatalog;
        this.progressStore = progressStore;
        this.readingRange = readingRange;
        this.readingProperties = readingProperties;
    }

    @GetMapping
    public BookList listBooks() {
        return gateway.listBooks();
    }

    @GetMapping("/{book_id}/chapters")
    public ChapterList listChapters(@PathVariable("book_id") int bookId) {
        // 列表**不筛**：全部章节的序号与标题照发（列表项不含正文），前端不做锁定标记
        // （2026-10-13 用户定：不做标记，只留 403）。挡内容的是下面两个端点。
        return gateway.listChapters(bookId);
    }

    /**
     * 章节正文：**卷外一律 403**（产品上的刻意取舍）。
     *
     * <p>先判范围再取正文：越界时不必向上游要一次全文，也就没有「取回来了再丢掉」那一步。
     * 前后导航同理往回收——不然读到第 1 卷末尾，界面上的「下一章」会指向卷外那一章，
     * 点下去才 403。
     */
    @GetMapping("/{book_id}/chapters/{chapter_index}")
    public ChapterDetail getChapter(@PathVariable("book_id") int bookId, @PathVariable("chapter_index") int chapterIndex) {
        ReadingRange.ChapterRange range = readingRange.rangeOf(bookId);
        if (!range.contains(chapterIndex)) {
            throw new RagException(
                    ErrorCode.RAG_FORBIDDEN,
                    "第 " + chapterIndex + " 章不在可读范围内：阅读页只开放第 "
                            + readingProperties.volumeIndex() + " 卷（全书第 " + range.lo() + "–" + range.hi() + " 章）");
        }
        ChapterDetail detail = gateway.getChapter(bookId, chapterIndex);
        if (detail.getPrevChapterIndex() != null && !range.contains(detail.getPrevChapterIndex())) {
            detail.setPrevChapterIndex(null);
        }
        if (detail.getNextChapterIndex() != null && !range.contains(detail.getNextChapterIndex())) {
            detail.setNextChapterIndex(null);
        }
        return detail;
    }

    /**
     * 插图字节流，边读边写给客户端。
     *
     * 路径由客户端传来，目录穿越与扩展名白名单两道防护在 Python 侧（内部契约该端点的要求），
     * 网关只负责不落内存地转出去。这里同步写而不是走异步：流没结束就占住一个请求线程，
     * 单机阅读场景下这点代价换来的是「首字节立刻到、每片即刷」。
     */
    @GetMapping("/{book_id}/images/{*path}")
    public void getImage(@PathVariable("book_id") int bookId, @PathVariable("path") String path, HttpServletResponse response)
            throws IOException {
        // 插图按「可读章节引用了它」判，不按目录名猜：口径只有一个来源（章节详情里的 images）
        if (!readingRange.imageReadable(bookId, path)) {
            throw new RagException(ErrorCode.RAG_FORBIDDEN, "这张插图不在可读范围内");
        }
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

    @GetMapping("/{book_id}/progress")
    public Progress getProgress(
            @PathVariable("book_id") int bookId, @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        return progressStore.read(user.userId(), bookId);
    }

    @PutMapping("/{book_id}/progress")
    public Progress putProgress(
            @PathVariable("book_id") int bookId,
            @RequestBody @Valid ProgressWrite body,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        // 越界与否取决于该书的 chapter_count，只能由 Java 判。
        RealmValidator.validateProgress(body.progress(), bookCatalog.chapterCount(bookId));
        return progressStore.write(user.userId(), bookId, body.progress());
    }
}
