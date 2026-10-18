package com.omniread.backend.store.smoke;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 三件新依赖能不能与 Spring Boot 4.1.1 一起工作——**实测，不是假设**。
 *
 * <p>最不确定的是 MyBatis 的 Boot 4 starter（4.1.0，很新、使用量少）。它不通就得换
 * MyBatis-Plus 的 boot4 starter，那是另一套自动配置与 SQL 映射写法，所以这一步必须先跑。
 *
 * <p>用**临时文件库**而不是 {@code :memory:}：内存库在连接池回收连接后就没了，
 * 而真实的 SQLite 使用场景（WAL、多连接）本来也基于文件。连接参数与生产一致
 * （{@code journal_mode=WAL} / {@code busy_timeout} / {@code foreign_keys}）。
 */
@SpringBootTest
class SqliteMyBatisSmokeTest {

    private static final Path DB_PATH = createDbPath();

    private static Path createDbPath() {
        try {
            Path dir = Files.createTempDirectory("omniread-sqlite-smoke");
            dir.toFile().deleteOnExit();
            return dir.resolve("smoke.db");
        } catch (IOException e) {
            throw new IllegalStateException("无法建临时目录", e);
        }
    }

    /**
     * 换库的唯一途径是 {@code omniread.store.file}——{@code spring.datasource.url} 不生效
     * （{@code StoreConfig} 自己定义了 DataSource，Boot 的自动配置退让，而且现在会显式报错）。
     *
     * <p>这条曾经写错过：配了 {@code spring.datasource.url} 的用例被静默忽略，
     * 落回默认的 {@code var/omniread.db}，而 Maven 的工作目录是 {@code services/backend}，
     * 于是它一直往那个共用的库里写，表现是断言的行数逐次上涨。
     */
    @DynamicPropertySource
    static void storeFile(DynamicPropertyRegistry registry) {
        registry.add("omniread.store.file", DB_PATH::toString);
    }

    @Autowired
    private SmokeNoteMapper mapper;

    @Test
    @DisplayName("MyBatis 4.1.0 的自动配置与 Boot 4.1.1 合得来：建表 → 插入 → 查回")
    void mybatisStarterWorksWithBoot() {
        mapper.createTable();
        // 临时库、刚建表，应当是空的。这条先断言，是为了让「表里有别人的数据」与
        // 「insert 多插了」在失败信息里分得开——它们看起来都是「行数不对」。
        assertThat(mapper.findAll()).as("刚建表的临时库应当是空的").isEmpty();

        SmokeNote first = new SmokeNote(null, "第一条", "2026-10-10T00:00:00Z");
        SmokeNote second = new SmokeNote(null, "第二条", "2026-10-10T00:00:01Z");
        assertThat(mapper.insert(first)).isEqualTo(1);
        assertThat(mapper.insert(second)).isEqualTo(1);

        // 自增主键必须被回填进入参对象——SQLite 驱动支持 useGeneratedKeys，但要实测。
        // 这条要求正是实体不能写成 record 的原因：回填靠 setter。
        assertThat(first.getId()).isNotNull();
        assertThat(second.getId()).isEqualTo(first.getId() + 1);

        SmokeNote loaded = mapper.findById(first.getId());
        assertThat(loaded).isNotNull();
        assertThat(loaded.getBody()).isEqualTo("第一条");
        // 时间统一走 ISO-8601 字符串，避开时区与 typeHandler 依赖。
        assertThat(loaded.getCreatedAt()).isEqualTo("2026-10-10T00:00:00Z");

        List<SmokeNote> all = mapper.findAll();
        assertThat(all).extracting(SmokeNote::getBody).containsExactly("第一条", "第二条");
    }

    @Test
    @DisplayName("BCrypt 可用的同时，哈希里读不出口令")
    void bcryptIsAvailableAndOneWay() {
        BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();
        String hash = encoder.encode("demo-password");

        assertThat(hash).startsWith("$2");
        assertThat(hash).doesNotContain("demo-password");
        assertThat(encoder.matches("demo-password", hash)).isTrue();
        assertThat(encoder.matches("wrong-password", hash)).isFalse();
        // 每次加盐不同：同一个口令两次哈希不相等，比对只能走 matches。
        assertThat(encoder.encode("demo-password")).isNotEqualTo(hash);
    }

    @Test
    @DisplayName("连接串的参数真的生效：外键约束打开")
    void foreignKeysAreEnforced() {
        // 连接串里带 foreign_keys=on，否则 SQLite 默认不校验外键（静默留下孤儿行）。
        assertThat(foreignKeysEnabled()).isTrue();
    }

    @Autowired
    private org.springframework.jdbc.core.JdbcTemplate jdbcTemplate;

    private boolean foreignKeysEnabled() {
        Integer on = jdbcTemplate.queryForObject("PRAGMA foreign_keys", Integer.class);
        return on != null && on == 1;
    }

    /** 冒烟结束后删掉临时目录；失败也不该留垃圾。 */
    static void cleanUp() {
        try (var paths = Files.walk(DB_PATH.getParent())) {
            paths.sorted(Comparator.reverseOrder()).forEach(p -> {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException ignored) {
                    // 清理失败不该让测试变红。
                }
            });
        } catch (IOException ignored) {
            // 同上。
        }
    }
}
