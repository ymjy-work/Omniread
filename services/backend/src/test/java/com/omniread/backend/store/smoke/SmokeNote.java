package com.omniread.backend.store.smoke;

/**
 * 冒烟用的最小实体。
 *
 * <p>存在的意义只有一个：验证 MyBatis 的 Boot 4 starter 与 Boot 4.1.1 合得来。
 * 这个 starter 很新、使用量还很少，「兼容」是实测项而不是假设项——不通过就换
 * MyBatis-Plus 的 boot4 starter（见 {@code docs/方案.md（依赖与选型一节）} §七）。
 *
 * <p><b>刻意手写成可变类，不用 {@code record}。</b>MyBatis 的 {@code useGeneratedKeys}
 * 靠反射调 setter 把自增主键写回入参，而 record 只有构造器、没有 setter，实测会报
 * {@code No setter found for the keyProperty 'id'}。
 * 这不是「record 不好」——契约 DTO 与只读视图仍然用 record；只有**需要接收自增主键的
 * 那一小撮实体**必须可变。本项目每一张表都有自增或需回填的主键，所以这条约束会反复遇到。
 */
public class SmokeNote {

    private Long id;
    private String body;
    private String createdAt;

    public SmokeNote() {
    }

    public SmokeNote(Long id, String body, String createdAt) {
        this.id = id;
        this.body = body;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getBody() {
        return body;
    }

    public void setBody(String body) {
        this.body = body;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
}
