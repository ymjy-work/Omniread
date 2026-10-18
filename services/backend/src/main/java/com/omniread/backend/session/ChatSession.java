package com.omniread.backend.session;

/**
 * 一个对话会话（表 `chat_sessions`）。
 *
 * <p>`level`（档位）**在会话内固定**：切档位不就地改，而是新建一个分叉会话。
 * 这样做的理由是防剧透约束靠「会话档位固定 + 进度只增不减」
 * 保证——就地改档位会让同一段对话里的前半截来自 `past`、后半截来自 `full`，
 * 而 `past` 的检索结果可能已经带着更早的上下文进了摘要。
 *
 * <p>`id` 是 uuid 字符串、由调用方生成，没有自增列。
 */
public class ChatSession {

    /** 档位的两个取值，与契约的 `level` 枚举逐字一致（库里存的就是这两个字符串）。 */
    public static final String LEVEL_PAST = "past";

    public static final String LEVEL_FULL = "full";

    private String id;
    private Long userId;
    private Integer bookId;
    private String title;
    private String level;
    private String forkedFrom;
    /** 从父会话的哪条消息分叉；与消息的 `seq` 同口径。 */
    private Integer forkedAtSeq;
    private String summary;
    /**
     * 摘要覆盖到哪条 `chat_messages.id`；**必须与 `summary` 同一次更新**，否则下次摘要会重复或漏段。
     *
     * <p>类型必须与 {@code ChatMessage.id} 一致（都是 {@code Long}）：它存的就是消息主键，
     * 一边 Integer 一边 Long 会在消息量大时静默截断，而截断后的 id 仍然是个合法值，
     * 查出来的「待摘要区间」看着正常却少了内容。
     */
    private Long summaryUpto;
    /** 这份摘要出自哪一版摘要模板；与 summary / summary_upto 同一次更新。 */
    private String summaryPromptVersion;
    private String createdAt;
    private String lastActiveAt;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

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

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getLevel() {
        return level;
    }

    public void setLevel(String level) {
        this.level = level;
    }

    public String getForkedFrom() {
        return forkedFrom;
    }

    public void setForkedFrom(String forkedFrom) {
        this.forkedFrom = forkedFrom;
    }

    public Integer getForkedAtSeq() {
        return forkedAtSeq;
    }

    public void setForkedAtSeq(Integer forkedAtSeq) {
        this.forkedAtSeq = forkedAtSeq;
    }

    public String getSummary() {
        return summary;
    }

    public void setSummary(String summary) {
        this.summary = summary;
    }

    public Long getSummaryUpto() {
        return summaryUpto;
    }

    public void setSummaryUpto(Long summaryUpto) {
        this.summaryUpto = summaryUpto;
    }

    public String getSummaryPromptVersion() {
        return summaryPromptVersion;
    }

    public void setSummaryPromptVersion(String summaryPromptVersion) {
        this.summaryPromptVersion = summaryPromptVersion;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }

    public String getLastActiveAt() {
        return lastActiveAt;
    }

    public void setLastActiveAt(String lastActiveAt) {
        this.lastActiveAt = lastActiveAt;
    }
}
