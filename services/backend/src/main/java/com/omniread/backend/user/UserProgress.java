package com.omniread.backend.user;

/**
 * 「某账户读到某本书第几章」。替换原来的单份 `var/progress.json`——那份是单机单份，
 * 多账户会共享（`docs/m1/deploy-plan.md` §三.5）。
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
