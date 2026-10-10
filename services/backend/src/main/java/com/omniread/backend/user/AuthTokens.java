package com.omniread.backend.user;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import org.springframework.stereotype.Component;

/**
 * 不透明登录 token 的生成与哈希（`docs/m1/java-依赖与选型.md` §十）。
 *
 * <p>**原文只出现在 cookie 里，库里存的是 SHA-256 哈希**：这张表即使被读走，
 * 也拿不到能登录的凭据。
 *
 * <p>哈希用 SHA-256 而不是 BCrypt——与口令的区别在**输入有多少不确定性**：
 * 口令是人选的、熵低，必须用慢哈希拖住离线爆破；这里的 token 是 256 位均匀随机，
 * 猜中的概率与暴力枚举密钥空间等价，慢哈希除了让每个受保护请求都多花几十毫秒以外
 * 什么也没买到。口令那一侧仍然是 BCrypt（{@link PasswordHasher}）。
 */
@Component
public class AuthTokens {

    /** 256 位。低于 128 位就该重新评估，而不是把这里的数字调小。 */
    private static final int TOKEN_BYTES = 32;

    private final SecureRandom random = new SecureRandom();

    /** URL 安全且无填充：它会进 cookie 值，也可能出现在日志或 curl 命令里。 */
    public String newToken() {
        byte[] bytes = new byte[TOKEN_BYTES];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    /** 十六进制而不是 Base64：哈希要当主键查，十六进制在 SQL 里不必转义、肉眼比对也方便。 */
    public String hash(String token) {
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            // SHA-256 是 JDK 必须实现的算法，走到这里说明运行环境已经不完整。
            throw new IllegalStateException("运行环境缺少 SHA-256", e);
        }
        return HexFormat.of().formatHex(digest.digest(token.getBytes(StandardCharsets.UTF_8)));
    }
}
