package com.omniread.backend.orchestration;

import com.omniread.backend.contract.model.BookList;
import com.omniread.backend.contract.model.BookListBooksInner;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import com.omniread.backend.gateway.RagGatewayClient;
import org.springframework.stereotype.Component;

/**
 * 书目录的唯一查询入口：progress 上界校验需要的 chapter_count 只从这里取。
 *
 * 不缓存：M0 只有一本书、导入期外 chapter_count 恒定，而缓存要自己处理失效，
 * 为一个随时可查的字段付这份复杂度不划算。
 */
@Component
public class BookCatalog {

    private final RagGatewayClient gateway;

    public BookCatalog(RagGatewayClient gateway) {
        this.gateway = gateway;
    }

    public int chapterCount(int bookId) {
        BookList books = gateway.listBooks();
        BookListBooksInner book = books.getBooks().stream()
                .filter(candidate -> Integer.valueOf(bookId).equals(candidate.getBookId()))
                .findFirst()
                .orElseThrow(() -> new RagException(ErrorCode.RAG_INVALID_REALM, "book_id " + bookId + " 不存在"));
        Integer chapterCount = book.getChapterCount();
        if (chapterCount == null) {
            throw new RagException(ErrorCode.RAG_UNAVAILABLE, "RAG 服务未返回 book_id " + bookId + " 的 chapter_count");
        }
        return chapterCount;
    }
}
