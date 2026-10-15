package com.omniread.backend.user;

/**
 * 一条登录会话（不透明 token）。
 *
 * <p>**库里只有 `token_hash`，原文只存在 cookie 里**（`docs/方案.md（依赖与选型一节）` §十）。
 * 所以这张表即使被读走，也拿不到能登录的凭据。
 *
 * <p>主键是 token 哈希本身，没有自增列——但仍然手写可变类，与其它实体保持同一种形状，
 * 免得日后加列时再分心去想「这个能不能用 record」。
 */
public class AuthSession {

    private String tokenHash;
    private Long userId;
    private String createdAt;
    private String expiresAt;
    private String lastSeenAt;

    public String getTokenHash() {
        return tokenHash;
    }

    public void setTokenHash(String tokenHash) {
        this.tokenHash = tokenHash;
    }

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }

    public String getExpiresAt() {
        return expiresAt;
    }

    public void setExpiresAt(String expiresAt) {
        this.expiresAt = expiresAt;
    }

    public String getLastSeenAt() {
        return lastSeenAt;
    }

    public void setLastSeenAt(String lastSeenAt) {
        this.lastSeenAt = lastSeenAt;
    }

    /** 哈希不进日志——它是「等价于凭据」的东西。 */
    @Override
    public String toString() {
        return "AuthSession{userId=" + userId + ", expiresAt='" + expiresAt + "'}";
    }
}
