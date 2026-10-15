package com.omniread.backend.user;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * 口令哈希。只借 `spring-security-crypto` 的 BCrypt 实现，不引 Spring Security 全家桶——
 * 这个项目要的只有「登录 / 退出 / 401」三件事，过滤器链与它的配置面比它解决的问题大
 * （`docs/方案.md（依赖与选型一节）` §三）。
 *
 * <p>BCrypt 自带盐，所以同一个口令两次哈希不相等，比对只能走 {@link #matches}——
 * 想用等号比较哈希的地方都是错的。
 *
 * <p>**明文不进日志、不进库、不进异常消息**：这个类不提供任何把原文带出来的方法。
 */
@Component
public class PasswordHasher {

    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();

    public String hash(String rawPassword) {
        return encoder.encode(rawPassword);
    }

    /** 口令不对与哈希格式坏掉都返回 false：调用方只需要知道「能不能进」。 */
    public boolean matches(String rawPassword, String passwordHash) {
        if (rawPassword == null || passwordHash == null) {
            return false;
        }
        try {
            return encoder.matches(rawPassword, passwordHash);
        } catch (IllegalArgumentException e) {
            return false;
        }
    }
}
