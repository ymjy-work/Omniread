package com.omniread.backend.store;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.omniread.backend.session.ChatMessage;
import com.omniread.backend.session.ChatMessageMapper;
import com.omniread.backend.session.ChatMessageStore;
import com.omniread.backend.session.ChatSession;
import com.omniread.backend.session.ChatSessionMapper;
import com.omniread.backend.user.User;
import com.omniread.backend.user.UserMapper;
import com.omniread.backend.user.UserProgress;
import com.omniread.backend.user.UserProgressMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 五张表与它们的 mapper：建表幂等、进程内 <b>seq</b> 不串序、级联删除、跨用户隔离。
 *
 * <p>用临时文件库而不是内存库：内存库在连接池回收连接后整库消失，而这里要验的
 * 并发写与 WAL 行为本来也基于文件。连接参数与生产一致。
 */
@SpringBootTest
class SqliteStoreTest {

    private static final Path DB_PATH = createDbPath();

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-store-test");
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
    private JdbcTemplate jdbcTemplate;
    @Autowired
    private UserMapper userMapper;
    @Autowired
    private UserProgressMapper userProgressMapper;
    @Autowired
    private ChatSessionMapper chatSessionMapper;
    @Autowired
    private ChatMessageMapper chatMessageMapper;
    @Autowired
    private ChatMessageStore chatMessageStore;
    @Autowired
    private SchemaInitializer schemaInitializer;

    // ── 建表 ──

    @Test
    @DisplayName("五张表都建起来了，且建表可重复执行")
    void schemaIsCreatedAndIdempotent() {
        for (String table :
                List.of("users", "auth_sessions", "user_progress", "chat_sessions",
                        "chat_messages", "schema_version")) {
            Integer count = jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                    Integer.class, table);
            assertThat(count).as("表 %s 应存在", table).isEqualTo(1);
        }

        // 再跑一遍：CREATE ... IF NOT EXISTS 必须无声通过，不能报「表已存在」。
        schemaInitializer.run(null);
        Integer version = jdbcTemplate.queryForObject(
                "SELECT MAX(version) FROM schema_version", Integer.class);
        assertThat(version).isEqualTo(SchemaInitializer.SCHEMA_VERSION);
    }

    @Test
    @DisplayName("库的表结构比代码旧时也拒绝——没有迁移框架，加列不会自己生效")
    void refusesWhenDatabaseIsOlderThanCode() {
        Integer original = jdbcTemplate.queryForObject(
                "SELECT MAX(version) FROM schema_version", Integer.class);
        try {
            // 模拟一个旧库：版本记成 1，而代码认识 2。
            jdbcTemplate.update("DELETE FROM schema_version");
            jdbcTemplate.update(
                    "INSERT INTO schema_version (version, applied_at) VALUES (1, ?)",
                    Instant.now().toString());

            assertThatThrownBy(() -> schemaInitializer.run(null))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("没有迁移框架")
                    .hasMessageContaining("删掉库文件重建");
        } finally {
            jdbcTemplate.update("DELETE FROM schema_version");
            jdbcTemplate.update(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    original, Instant.now().toString());
        }
    }

    @Test
    @DisplayName("库的表结构比代码新时拒绝继续，而不是硬跑")
    void refusesWhenDatabaseIsNewerThanCode() {
        Integer original = jdbcTemplate.queryForObject(
                "SELECT MAX(version) FROM schema_version", Integer.class);
        try {
            jdbcTemplate.update(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    SchemaInitializer.SCHEMA_VERSION + 1, Instant.now().toString());

            assertThatThrownBy(() -> schemaInitializer.run(null))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("比代码认识的");
        } finally {
            // 恢复，免得这条用例污染同一个上下文里的其它用例。
            jdbcTemplate.update("DELETE FROM schema_version WHERE version > ?", original);
        }
    }

    // ── 账户与隔离 ──

    @Test
    @DisplayName("账户自增主键回填；进度按账户隔离")
    void usersGetGeneratedIdsAndProgressIsPerUser() {
        User alice = newUser("alice");
        User bob = newUser("bob");
        assertThat(alice.getId()).isNotNull();
        assertThat(bob.getId()).isNotEqualTo(alice.getId());

        userProgressMapper.upsert(progress(alice.getId(), 1, 10));
        userProgressMapper.upsert(progress(bob.getId(), 1, 200));

        assertThat(userProgressMapper.find(alice.getId(), 1).getProgress()).isEqualTo(10);
        assertThat(userProgressMapper.find(bob.getId(), 1).getProgress()).isEqualTo(200);

        // 同一账户同一本书再写一次是更新而不是插新行——复合主键就是冲突目标。
        userProgressMapper.upsert(progress(alice.getId(), 1, 11));
        assertThat(userProgressMapper.findByUserId(alice.getId())).hasSize(1);
        assertThat(userProgressMapper.find(alice.getId(), 1).getProgress()).isEqualTo(11);
    }

    // ── 会话与消息 ──

    @Test
    @DisplayName("seq 从 1 起逐条递增，且 id 被回填")
    void seqStartsAtOneAndIncrements() {
        User user = newUser("seq-user");
        ChatSession session = newSession(user.getId(), "past");

        ChatMessage first = chatMessageStore.append(session.getId(), "user", "第一问", 5, null);
        ChatMessage second =
                chatMessageStore.append(session.getId(), "assistant", "第一答", 7, "{\"c\":1}");

        assertThat(first.getSeq()).isEqualTo(1);
        assertThat(second.getSeq()).isEqualTo(2);
        assertThat(first.getId()).isNotNull();
        assertThat(second.getId()).isGreaterThan(first.getId());

        List<ChatMessage> all = chatMessageMapper.findBySession(session.getId());
        assertThat(all).extracting(ChatMessage::getSeq).containsExactly(1, 2);
        assertThat(all.get(1).getMeta()).isEqualTo("{\"c\":1}");
    }

    @Test
    @DisplayName("并发往同一会话写：seq 不重不漏")
    void concurrentAppendsNeverCollide() throws Exception {
        User user = newUser("concurrent-user");
        ChatSession session = newSession(user.getId(), "past");

        int writers = 6;
        int perWriter = 8;
        Set<Integer> observedSeqs = ConcurrentHashMap.newKeySet();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(writers);
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (int w = 0; w < writers; w++) {
                // **必须留下 Future 并 get()**：`submit` 把任务抛的异常吞进 Future，
                // 不取就永远看不到——某个写者中途抛异常会表现为「少写了几条」，
                // 而真正的原因（碰撞没被识别？写锁超时？）一个字都不会出现在失败信息里。
                futures.add(pool.submit(() -> {
                    start.await();
                    for (int i = 0; i < perWriter; i++) {
                        ChatMessage m = chatMessageStore.append(
                                session.getId(), "user", "并发写", 1, null);
                        observedSeqs.add(m.getSeq());
                    }
                    return null;
                }));
            }
            start.countDown();
            pool.shutdown();
            assertThat(pool.awaitTermination(30, TimeUnit.SECONDS)).isTrue();
            for (Future<?> future : futures) {
                future.get();
            }
        } catch (ExecutionException e) {
            throw new AssertionError("并发写者抛了异常：" + e.getCause(), e.getCause());
        } finally {
            pool.shutdownNow();
        }

        int total = writers * perWriter;
        List<Integer> inDb = chatMessageMapper.findBySession(session.getId()).stream()
                .map(ChatMessage::getSeq)
                .toList();

        // 一条断言给出全部现场：库里几条、内存里观察到几个不同 seq、库里的 seq 序列。
        // 分开断言只会告诉我「哪一条不符」，而这里要区分的是「丢了行」与「取重了号」。
        assertThat(inDb)
                .as("库里 %d 条（期望 %d），内存观察到 %d 个不同 seq",
                        inDb.size(), total, observedSeqs.size())
                .containsExactlyElementsOf(IntStream.rangeClosed(1, total).boxed().toList());
    }

    @Test
    @DisplayName("seq 撞车抛出来的异常能被识别成「可重试」")
    void duplicateSeqRaisesSomethingTheStoreRecognises() {
        User user = newUser("collision-user");
        ChatSession session = newSession(user.getId(), "past");
        chatMessageStore.append(session.getId(), "user", "第一条", 1, null);

        ChatMessage duplicate = new ChatMessage();
        duplicate.setSessionId(session.getId());
        duplicate.setSeq(1); // 已被占用
        duplicate.setRole("user");
        duplicate.setContent("撞号");
        duplicate.setCreatedAt(Instant.now().toString());

        // 这条断言的作用不是「它会抛」，而是**把异常形状钉住**：ChatMessageStore 判
        // 「可重试」要靠它。Spring 对 SQLite 的约束错误翻译未必到位，
        // 所以这里同时记录 Spring 的异常类型与底层的 SQLite 错误码——
        // 换驱动、换 Spring 版本时，这条会先红，而不是让并发路径在别处以「少写几条」的形式失败。
        assertThatThrownBy(() -> chatMessageMapper.insert(duplicate))
                .isInstanceOf(DataAccessException.class)
                .hasMessageContaining("UNIQUE");
    }

    @Test
    @DisplayName("跨用户取不到别人的会话；删别人的会话删不掉")
    void sessionsAreScopedToTheirOwner() {
        User alice = newUser("owner-alice");
        User bob = newUser("owner-bob");
        ChatSession session = newSession(alice.getId(), "past");

        // 按 id 取是**不带用户过滤**的（生产刻意如此：要能区分「不是你的」与「不存在」），
        // 所以越权判定得自己比 userId——这正是 SessionService 鉴权路径的形状。
        assertThat(chatSessionMapper.findById(session.getId()).getUserId()).isEqualTo(alice.getId());
        assertThat(chatSessionMapper.findById(session.getId()).getUserId()).isNotEqualTo(bob.getId());
        // 批量与删除按用户过滤是对的：删不掉就是没删掉，不需要区分原因。
        assertThat(chatSessionMapper.deleteForUser(session.getId(), bob.getId())).isZero();
        assertThat(chatSessionMapper.findById(session.getId())).isNotNull();
    }

    @Test
    @DisplayName("删会话级联删消息——依赖连接串里的 foreign_keys=on")
    void deletingSessionCascadesMessages() {
        User user = newUser("cascade-user");
        ChatSession session = newSession(user.getId(), "full");
        chatMessageStore.append(session.getId(), "user", "问", 1, null);
        chatMessageStore.append(session.getId(), "assistant", "答", 1, null);
        assertThat(chatMessageMapper.countBySession(session.getId())).isEqualTo(2);

        chatSessionMapper.deleteForUser(session.getId(), user.getId());

        assertThat(chatMessageMapper.countBySession(session.getId())).isZero();
    }

    @Test
    @DisplayName("外键真的在拦：挂到不存在的会话上会被拒")
    void foreignKeysAreEnforced() {
        ChatMessage orphan = new ChatMessage();
        orphan.setSessionId("不存在的会话");
        orphan.setSeq(1);
        orphan.setRole("user");
        orphan.setContent("孤儿");
        orphan.setCreatedAt(Instant.now().toString());

        assertThatThrownBy(() -> chatMessageMapper.insert(orphan))
                .isInstanceOf(org.springframework.dao.DataAccessException.class);
    }

    @Test
    @DisplayName("摘要与 summary_upto 同一次更新")
    void summaryAndUptoAdvanceTogether() {
        User user = newUser("summary-user");
        ChatSession session = newSession(user.getId(), "past");
        ChatMessage first = chatMessageStore.append(session.getId(), "user", "问", 1, null);

        chatSessionMapper.updateSummary(
                session.getId(), "这段对话在问一件事", first.getId(), "summarize-deadbeef");

        ChatSession reloaded = chatSessionMapper.findById(session.getId());
        assertThat(reloaded.getSummary()).isEqualTo("这段对话在问一件事");
        assertThat(reloaded.getSummaryUpto()).isEqualTo(first.getId());
        // 三样一次更新：摘要在库里长期存着，模板改过后要能分辨它出自哪一版。
        assertThat(reloaded.getSummaryPromptVersion()).isEqualTo("summarize-deadbeef");
    }

    // ── 夹具 ──

    private User newUser(String prefix) {
        User user = new User();
        // 唯一名：同一个测试上下文里多条用例共用一个库。
        user.setUsername(prefix + "-" + UUID.randomUUID());
        user.setPasswordHash("$2a$10$not-a-real-hash");
        user.setStatus(User.STATUS_ACTIVE);
        user.setCreatedAt(Instant.now().toString());
        userMapper.insert(user);
        return user;
    }

    private ChatSession newSession(long userId, String level) {
        ChatSession session = new ChatSession();
        session.setId(UUID.randomUUID().toString());
        session.setUserId(userId);
        session.setBookId(1);
        session.setTitle("新会话");
        session.setLevel(level);
        session.setCreatedAt(Instant.now().toString());
        session.setLastActiveAt(session.getCreatedAt());
        chatSessionMapper.insert(session);
        return session;
    }

    private static UserProgress progress(long userId, int bookId, int value) {
        UserProgress p = new UserProgress();
        p.setUserId(userId);
        p.setBookId(bookId);
        p.setProgress(value);
        return p;
    }
}
