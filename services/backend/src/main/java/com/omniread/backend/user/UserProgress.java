package com.omniread.backend.user;

/**
 * 「某账户读到某本书第几章」。
 *
 * <p>**必须带 `user_id`**：不带的话所有人共享一份「读到哪」，一个人翻到第 100 章、
 * 另一个人刷新就跟着变，而两边都不会报错。
 *
 * <p>复合主键 `(user_id, book_id)`，没有自增列。
 */
public class UserProgress {

    private Long userId;
    private Integer bookId;
    private Integer progress;

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public Integer getBookId() {
        return bookId;
    }

    public void setBookId(Integer bookId) {
        this.bookId = bookId;
    }

    public Integer getProgress() {
        return progress;
    }

    public void setProgress(Integer progress) {
        this.progress = progress;
    }
}
