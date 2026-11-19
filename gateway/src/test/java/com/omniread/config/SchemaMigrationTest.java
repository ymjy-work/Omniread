package com.omniread.config;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ScriptUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SchemaMigrationTest {

	@Test
	void migrationPreservesExistingDataAndIsIdempotent() throws Exception {
		Path db = Files.createTempFile(Path.of("target"), "legacy-migration-", ".db");
		db.toFile().deleteOnExit();
		String url = "jdbc:sqlite:" + db.toAbsolutePath();
		DriverManagerDataSource dataSource = new DriverManagerDataSource(url);
		JdbcTemplate jdbc = new JdbcTemplate(dataSource);

		// 旧版 schema：user 无账户列
		try (Connection connection = DriverManager.getConnection(url)) {
			ScriptUtils.executeSqlScript(connection, new ClassPathResource("schema.sql"));
			try (Statement statement = connection.createStatement()) {
				statement.execute("INSERT INTO user(username, password_hash, display_name, created_at) "
						+ "VALUES('old-admin', 'hash', 'Old Admin', '2026-01-01T00:00:00.000Z')");
				statement.execute("INSERT INTO book(id, title, author, created_at) "
						+ "VALUES(1, '旧书', '作者', '2026-01-01T00:00:00.000Z')");
				statement.execute("INSERT INTO chapter(book_id, chapter_index, title, text, created_at) "
						+ "VALUES(1, 1, '旧章节', '旧正文', '2026-01-01T00:00:00.000Z')");
			}
		}

		new SchemaMigrator(jdbc).run(null);

		assertEquals("old-admin", jdbc.queryForObject(
				"SELECT username FROM user WHERE id = 1", String.class));
		assertEquals("user", jdbc.queryForObject("SELECT role FROM user WHERE id = 1", String.class));
		assertEquals("free", jdbc.queryForObject("SELECT plan FROM user WHERE id = 1", String.class));
		assertEquals(100, jdbc.queryForObject("SELECT credits FROM user WHERE id = 1", Integer.class));
		assertEquals(0.0, jdbc.queryForObject("SELECT balance FROM user WHERE id = 1", Double.class));
		assertEquals("旧正文", jdbc.queryForObject(
				"SELECT text FROM chapter WHERE book_id = 1 AND chapter_index = 1", String.class));
		assertEquals(4, jdbc.queryForObject("SELECT COUNT(*) FROM plan_catalog", Integer.class));
		assertEquals(2, jdbc.queryForObject("SELECT COUNT(*) FROM model_catalog", Integer.class));
		assertEquals(500, jdbc.queryForObject(
				"SELECT credits FROM plan_catalog WHERE code = 'plus'", Integer.class));

		// 二次迁移不重复补列、不重复 seed
		new SchemaMigrator(jdbc).run(null);
		assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM user", Integer.class));
		assertEquals(4, jdbc.queryForObject("SELECT COUNT(*) FROM plan_catalog", Integer.class));
		assertEquals(2, jdbc.queryForObject("SELECT COUNT(*) FROM model_catalog", Integer.class));
	}
}
