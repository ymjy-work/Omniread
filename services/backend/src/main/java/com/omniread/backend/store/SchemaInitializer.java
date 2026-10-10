package com.omniread.backend.store;

import java.time.Instant;
import javax.sql.DataSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.DatabasePopulatorUtils;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.stereotype.Component;

/**
 * 启动时建表（幂等）并把版本记进 {@code schema_version}。
 *
 * <p>没有用迁移框架（`docs/m1/java-依赖与选型.md` §三）：五张表、单实例，启动时
 * {@code CREATE TABLE IF NOT EXISTS} 够用。代价是**表结构的变更要靠人记住改 {@code schema.sql}**，
 * 所以这里加一道反向闸门：**库里的版本比代码新就拒绝启动**——那是「代码比库旧」，
 * 继续跑只会以难以定位的方式写坏数据，不如当场停下。
 */
@Component
public class SchemaInitializer implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(SchemaInitializer.class);

    /** 代码认识的表结构版本。改了 {@code schema.sql} 就把它加一。 */
    static final int SCHEMA_VERSION = 1;

    private static final String SCHEMA_RESOURCE = "db/schema.sql";

    private final DataSource dataSource;
    private final JdbcTemplate jdbcTemplate;

    public SchemaInitializer(DataSource dataSource) {
        this.dataSource = dataSource;
        this.jdbcTemplate = new JdbcTemplate(dataSource);
    }

    @Override
    public void run(ApplicationArguments args) {
        // 必须用脚本执行器而不是 `JdbcTemplate.execute(sql)`：后者把整段文本当**一条**语句，
        // 多条 DDL 只会跑掉第一条，后面的表静默不建（现象是「启动成功、用的时候说没有表」）。
        ResourceDatabasePopulator populator =
                new ResourceDatabasePopulator(new ClassPathResource(SCHEMA_RESOURCE));
        populator.setContinueOnError(false);
        DatabasePopulatorUtils.execute(populator, dataSource);

        Integer newest = jdbcTemplate.queryForObject(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version", Integer.class);
        int current = newest == null ? 0 : newest;

        if (current > SCHEMA_VERSION) {
            throw new IllegalStateException(
                    "库的表结构版本（" + current + "）比代码认识的（" + SCHEMA_VERSION + "）新："
                            + "这份代码配不上这个库，换回新版本再启动");
        }
        if (current < SCHEMA_VERSION) {
            jdbcTemplate.update(
                    "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
                    SCHEMA_VERSION,
                    Instant.now().toString());
            log.info("表结构已就绪：版本 {} -> {}", current, SCHEMA_VERSION);
        }
    }
}
