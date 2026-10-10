package com.omniread.backend.user;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.omniread.backend.session.ChatMessageStore;
import com.omniread.backend.session.ChatSession;
import com.omniread.backend.session.ChatSessionMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataAccessException;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 账户的发放、认证与停用清理（`docs/m1/用户管理需求.md`）。
 *
 * <p>重点不在「能登录」，而在三条容易被做漏的：**明文不落库**、**停用即清空内容数据**、
 * **停用后登录态立即失效**。
 */
@SpringBootTest
class AccountServiceTest {

    private static final Path DB_PATH = createDbPath();

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-account-test");
            dir.toFile().deleteOnExit();
            return dir.resolve("omniread.db");
        } catch (IOException e) {
            throw new IllegalStateException("无法建临时目录", e);
        }
    }

    @DynamicPropertySource
    static void storeFile(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", DB_PATH::toString);
    }

    @Autowired
    private AccountService accountService;
    @Autowired
    private UserMapper userMapper;
    @Autowired
    private AuthSessionMapper authSessionMapper;
    @Autowired
    private ChatSessionMapper chatSessionMapper;
    @Autowired
    private ChatMessageStore chatMessageStore;
    @Autowired
    private org.springframework.jdbc.core.JdbcTemplate jdbcTemplate;

    private static String unique(String prefix) {
        return prefix + "-" + UUID.randomUUID();
    }

    @Test
    @DisplayName("发放的账户能登录；口令只以哈希落库")
    void createsAccountAndStoresOnlyHash() {
        String username = unique("alice");
        accountService.create(username, "correct-horse-battery");

        User stored = userMapper.findByUsername(username);
        assertThat(stored.getPasswordHash())
                .as("库里必须是哈希，不是明文")
                .startsWith("$2")
                .doesNotContain("correct-horse-battery");
        assertThat(stored.getStatus()).isEqualTo(User.STATUS_ACTIVE);

        // 连整行 dump 出来也不该含明文——比只查一列更严。
        String row = jdbcTemplate.queryForObject(
                "SELECT username || password_hash FROM users WHERE id = ?",
                String.class, stored.getId());
        assertThat(row).doesNotContain("correct-horse-battery");

        assertThat(accountService.authenticate(username, "correct-horse-battery")).isPresent();
        assertThat(accountService.authenticate(username, "wrong-password")).isEmpty();
    }

    @Test
    @DisplayName("不存在的账户与口令错误返回同一种结果——不给枚举账户名的接口")
    void unknownUserAndBadPasswordLookTheSame() {
        String username = unique("bob");
        accountService.create(username, "pw-123456");

        Optional<User> wrongPassword = accountService.authenticate(username, "nope");
        Optional<User> noSuchUser = accountService.authenticate(unique("ghost") + "-missing", "pw-123456");

        assertThat(wrongPassword).isEmpty();
        assertThat(noSuchUser).isEmpty();
    }

    @Test
    @DisplayName("账户名重复由唯一约束拦下")
    void duplicateUsernameIsRejected() {
        String username = unique("dup");
        accountService.create(username, "pw-123456");

        assertThatThrownBy(() -> accountService.create(username, "another-pw"))
                .isInstanceOf(DataAccessException.class);
    }

    @Test
    @DisplayName("停用后登不进来，且登录态立即失效")
    void disabledAccountCannotLogInAndSessionsAreRevoked() {
        String username = unique("carol");
        User user = accountService.create(username, "pw-123456");

        AuthSession session = new AuthSession();
        session.setTokenHash("hash-" + UUID.randomUUID());
        session.setUserId(user.getId());
        session.setCreatedAt(Instant.now().toString());
        session.setExpiresAt(Instant.now().plusSeconds(3600).toString());
        authSessionMapper.insert(session);
        assertThat(authSessionMapper.findByTokenHash(session.getTokenHash())).isNotNull();

        accountService.disableAndPurge(user.getId());

        // 登录态已吊销：这正是选「自建会话表」而不是 JWT 的理由。
        assertThat(authSessionMapper.findByTokenHash(session.getTokenHash())).isNull();
        assertThat(accountService.authenticate(username, "pw-123456")).isEmpty();
        assertThat(userMapper.findById(user.getId()).getStatus())
                .as("账户行保留为 disabled，用于审计与复用")
                .isEqualTo(User.STATUS_DISABLED);
    }

    @Test
    @DisplayName("停用会清空该账户的会话与消息，不留原文片段")
    void disablingPurgesChatContent() {
        User user = accountService.create(unique("dave"), "pw-123456");
        String sessionId = UUID.randomUUID().toString();
        ChatSession chat = new ChatSession();
        chat.setId(sessionId);
        chat.setUserId(user.getId());
        chat.setBookId(1);
        chat.setTitle("会话");
        chat.setLevel("past");
        chat.setCreatedAt(Instant.now().toString());
        chat.setLastActiveAt(chat.getCreatedAt());
        chatSessionMapper.insert(chat);
        chatMessageStore.append(sessionId, "user", "用户问的原文", 5, null);
        chatMessageStore.append(sessionId, "assistant", "模型答的原文", 5, null);

        accountService.disableAndPurge(user.getId());

        assertThat(chatSessionMapper.findById(sessionId)).isNull();
        Integer remaining = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", Integer.class, sessionId);
        assertThat(remaining).as("消息由外键 ON DELETE CASCADE 带走").isZero();
    }
}
