package com.omniread.backend.store;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.sql.DataSource;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 本机 SQLite 的连接装配。
 *
 * <p>**自己定义 {@code DataSource} 而不是走 {@code spring.datasource.url}**，有两件事只有
 * 在这里做才做得成：
 *
 * <ol>
 *   <li>SQLite 不会替我们建目录。库文件放在 `var/` 下，而 `var/` 可能是空的或不存在——
 *       交给 Boot 的自动配置，第一次连接就会以「unable to open database file」失败，
 *       而那个报错完全看不出是缺目录。
 *   <li>三个连接参数必须跟着 URL 走：{@code journal_mode=WAL}（读写并发）、
 *       {@code busy_timeout}（写冲突时等而不是立刻失败）、{@code foreign_keys=on}
 *       （**不写这个，SQLite 默认不校验外键**，会静默留下孤儿行）。
 * </ol>
 */
@Configuration
@EnableConfigurationProperties(StoreProperties.class)
public class StoreConfig {

    /** SQLite 是单写者：WAL 之后读可以并发，写仍然只有一条路。池子开大只增加写冲突。 */
    private static final int MAX_POOL_SIZE = 5;

    @Bean
    public DataSource dataSource(StoreProperties properties) {
        Path file = Path.of(properties.file()).toAbsolutePath();
        Path parent = file.getParent();
        if (parent != null) {
            try {
                Files.createDirectories(parent);
            } catch (IOException e) {
                throw new UncheckedIOException("无法创建数据库目录：" + parent, e);
            }
        }

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(
                "jdbc:sqlite:" + file + "?journal_mode=WAL&busy_timeout=5000&foreign_keys=on");
        config.setDriverClassName("org.sqlite.JDBC");
        config.setMaximumPoolSize(MAX_POOL_SIZE);
        // 池名带文件名：多个测试上下文并存时，日志里能分清是哪一个库。
        config.setPoolName("omniread-sqlite");
        return new HikariDataSource(config);
    }
}
