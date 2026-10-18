package com.omniread.backend.user;

/**
 * 一个演示账户。
 *
 * <p>**手写可变类而不是 {@code record}**：`id` 是自增主键，要靠 MyBatis 的
 * {@code useGeneratedKeys} 回填，而回填走的是 setter——record 只有构造器，实测会报
 * {@code No setter found for the keyProperty 'id'}。本项目每张表都有自增或需回填的主键，
 * 所以「需要接收主键的实体手写」是一条会反复遇到的约束。
 *
 * <p>`status` 用字符串常量而不是枚举：SQLite 里存的是 TEXT，用枚举要引 typeHandler，
 * 而只有两个取值（见 {@link #STATUS_ACTIVE} / {@link #STATUS_DISABLED}）。
 */
public class User {

    public static final String STATUS_ACTIVE = "active";
    public static final String STATUS_DISABLED = "disabled";

    private Long id;
    private String username;
    /** BCrypt 哈希；明文永不落库、不入日志。 */
    private String passwordHash;
    private String status;
    private String createdAt;
    private String lastLoginAt;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public void setPasswordHash(String passwordHash) {
        this.passwordHash = passwordHash;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }

    public String getLastLoginAt() {
        return lastLoginAt;
    }

    public void setLastLoginAt(String lastLoginAt) {
        this.lastLoginAt = lastLoginAt;
    }

    public boolean isActive() {
        return STATUS_ACTIVE.equals(status);
    }

    /** 日志与报错里只出现账户名，不出现哈希。 */
    @Override
    public String toString() {
        return "User{id=" + id + ", username='" + username + "', status='" + status + "'}";
    }
}
