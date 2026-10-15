package com.omniread.backend.store;

import java.time.Instant;
import javax.sql.DataSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.DatabasePopulatorUtils;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.stereotype.Component;

/**
 * 启动时建表（幂等）并把版本记进 {@code schema_version}。
 *
 * <p>没有用迁移框架（`docs/方案.md（依赖与选型一节）` §三）：五张表、单实例，启动时
 * {@code CREATE TABLE IF NOT EXISTS} 够用。代价是**表结构的变更要靠人记住改 {@code schema.sql}**，
 * 所以这里加一道反向闸门：**库里的版本比代码新就拒绝启动**——那是「代码比库旧」，
 * 继续跑只会以难以定位的方式写坏数据，不如当场停下。
 *
 * <p>**建表必须是第一个 {@code ApplicationRunner}**：后面任何一个在启动阶段查库的组件
 * 都排在它之后才行。平级的 runner 之间没有顺序保证，实测踩过一次——清理登录会话的组件
 * 先跑，报的是 `no such table: auth_sessions`，看起来像 mapper 的 namespace 写错了。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class SchemaInitializer implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(SchemaInitializer.class);

    /** 代码认识的表结构版本。改了 {@code schema.sql} 就把它加一。 */
    static final int SCHEMA_VERSION = 3;

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
        if (current > 0 && current < SCHEMA_VERSION) {
            // 本项目没有迁移框架（选型见 java-依赖与选型.md §三：五张表、单实例，
            // 引 Flyway 要多一个依赖与一套配置）。代价就落在这里：**加了列不会自己生效**，
            // 因为 DDL 全是 CREATE TABLE IF NOT EXISTS——表已存在就整条跳过，
            // 于是新列静默不存在，直到某次查询才报「no such column」。
            //
            // 所以旧版本的库直接拒绝，并把要做的事写清楚。预部署期删库重建没有代价；
            // 等真上线了，这里就该换成真正的迁移。
            throw new IllegalStateException(
                    "库的表结构版本是 " + current + "，代码是 " + SCHEMA_VERSION
                            + "：本项目没有迁移框架，改了 schema.sql 不会自动应用到旧库。"
                            + "删掉库文件重建即可（预部署期没有需要保留的数据）："
                            + "本机默认在 services/backend/var/omniread.db（相对进程工作目录）");
        }
        if (current == 0) {
            jdbcTemplate.update(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    SCHEMA_VERSION,
                    Instant.now().toString());
            log.info("表结构已就绪：版本 0 -> {}", SCHEMA_VERSION);
        }
    }
}
