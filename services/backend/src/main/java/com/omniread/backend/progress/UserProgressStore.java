package com.omniread.backend.progress;

import com.omniread.backend.user.UserProgress;
import com.omniread.backend.user.UserProgressMapper;
import org.springframework.stereotype.Component;

/**
 * 按账户的阅读进度（表 `user_progress`），一个账户一本书一行。
 *
 * <p>**进度必须带账户**：不带的话所有人共享一份「读到哪」，一个人翻到第 100 章、
 * 另一个人刷新就跟着变，而两边都不会报错。
 *
 * <p>`var/progress.json` 已经没有任何代码读它，可以删。**它不迁移**：那份文件没有
 * `user_id`，归属不到任何账户——迁移的前提是先有一个「这份进度是谁的」的答案，
 * 而那个答案不存在。
 *
 * <p>这里不判 `max_seq` 的边界：上界要 `chapter_count`，只有 Controller 拿得到。
 */
@Component
public class UserProgressStore {

    /** 没写过进度时读到第 1 章：契约 `max_seq` 下界是 1，0 不在合法范围。 */
    static final int FIRST_CHAPTER = 1;

    private final UserProgressMapper mapper;

    public UserProgressStore(UserProgressMapper mapper) {
        this.mapper = mapper;
    }

    /** 没写过的账户读到的是一份**初始值**，不是别人的值，也不落库。 */
    public Progress read(long userId, int bookId) {
        UserProgress stored = mapper.find(userId, bookId);
        return stored == null ? initial(bookId) : new Progress(bookId, stored.getProgress());
    }

    /** 有则更新、无则插入：`(user_id, book_id)` 是主键，也是冲突目标。 */
    public Progress write(long userId, int bookId, int maxSeq) {
        UserProgress row = new UserProgress();
        row.setUserId(userId);
        row.setBookId(bookId);
        row.setProgress(maxSeq);
        mapper.upsert(row);
        return new Progress(bookId, maxSeq);
    }

    private static Progress initial(int bookId) {
        return new Progress(bookId, FIRST_CHAPTER);
    }
}
