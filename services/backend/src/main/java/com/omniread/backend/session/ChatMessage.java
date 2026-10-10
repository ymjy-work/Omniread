package com.omniread.backend.session;

/**
 * 一条会话消息（user 或 assistant）。
 *
 * <p>`id` 是自增主键、要靠 setter 回填，所以手写可变类而不是 {@code record}
 * （理由同 {@code user.User}）。`seq` 是**会话内消息序号**，由 {@link ChatMessageStore}
 * 做乐观锁赋值：先取 `MAX(seq)` 再写，唯一约束撞车就重取重试。
 *
 * <p>`meta` 是 JSON 字符串：引用编号、`context_chapters`、改写前后的问题、模型与 prompt 版本。
 * 存字符串而不是结构化列，是因为它的形状跟着回答链走，用列固定下来会让每次协议微调都要改表。
 */
public class ChatMessage {

    /** 消息的两个角色，与契约的 `role` 枚举逐字一致（库里存的就是这两个字符串）。 */
    public static final String ROLE_USER = "user";

    public static final String ROLE_ASSISTANT = "assistant";

    private Long id;
    private String sessionId;
    private Integer seq;
    private String role;
    private String content;
    /** Java 侧字符估算（汉字 × 0.81 + 其他 × 0.3），**不是权威值**；真实用量由 Python 回报。 */
    private Integer tokenCount;
    private String createdAt;
    private String meta;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public Integer getSeq() {
        return seq;
    }

    public void setSeq(Integer seq) {
        this.seq = seq;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public Integer getTokenCount() {
        return tokenCount;
    }

    public void setTokenCount(Integer tokenCount) {
        this.tokenCount = tokenCount;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }

    public String getMeta() {
        return meta;
    }

    public void setMeta(String meta) {
        this.meta = meta;
    }
}
