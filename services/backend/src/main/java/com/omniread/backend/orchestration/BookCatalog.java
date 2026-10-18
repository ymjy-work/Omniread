package com.omniread.backend.orchestration;

import com.omniread.backend.contract.model.BookList;
import com.omniread.backend.contract.model.BookListBooksInner;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import com.omniread.backend.gateway.RagGatewayClient;
import org.springframework.stereotype.Component;

/**
 * 书目录的唯一查询入口：progress 上界校验需要的 chapter_count、以及「这本书在不在」
 * 都只从这里取。
 *
 * 不缓存：当前只有一本书、导入期外 chapter_count 恒定，而缓存要自己处理失效，
 * 为一个随时可查的字段付这份复杂度不划算。
 */
@Component
public class BookCatalog {

    private final RagGatewayClient gateway;

    public BookCatalog(RagGatewayClient gateway) {
        this.gateway = gateway;
    }

    public int chapterCount(int bookId) {
        Integer chapterCount = book(bookId).getChapterCount();
        if (chapterCount == null) {
            throw new RagException(ErrorCode.RAG_UNAVAILABLE, "RAG 服务未返回 book_id " + bookId + " 的 chapter_count");
        }
        return chapterCount;
    }

    /**
     * 目录里没有这本书即 400 —— 归 `RAG_INVALID_REQUEST` 而不是 `RAG_INVALID_REALM`：
     * 契约把「`book_id` 不存在」明确列为「请求本身不合法」那一类（前端该修自己），
     * 而 `RAG_INVALID_REALM` 的处置是提示用户改档位或改进度。两者同为 400，
     * 前端按 code 分支，混在一起就分不出该提示谁。
     */
    private BookListBooksInner book(int bookId) {
        BookList books = gateway.listBooks();
        return books.getBooks().stream()
                .filter(candidate -> Integer.valueOf(bookId).equals(candidate.getBookId()))
                .findFirst()
                .orElseThrow(() -> new RagException(ErrorCode.RAG_INVALID_REQUEST, "book_id " + bookId + " 不存在"));
    }
}
