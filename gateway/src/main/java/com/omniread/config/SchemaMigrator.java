package com.omniread.config;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** 启动迁移：user 表缺列才 ALTER，保留现有数据；幂等 seed 套餐与模型目录。 */
@Component
@Order(0)
public class SchemaMigrator implements ApplicationRunner {

	private static final Logger log = LoggerFactory.getLogger(SchemaMigrator.class);

	private final JdbcTemplate jdbcTemplate;

	public SchemaMigrator(JdbcTemplate jdbcTemplate) {
		this.jdbcTemplate = jdbcTemplate;
	}

	@Override
	public void run(ApplicationArguments args) {
		migrateUserColumns();
		seedPlanCatalog();
		seedModelCatalog();
	}

	private void migrateUserColumns() {
		List<String> columns = jdbcTemplate.query("PRAGMA table_info(user)",
				(rs, rowNum) -> rs.getString("name"));
		Map<String, String> additions = new LinkedHashMap<>();
		additions.put("role", "TEXT NOT NULL DEFAULT 'user'");
		additions.put("plan", "TEXT NOT NULL DEFAULT 'free'");
		additions.put("credits", "INTEGER NOT NULL DEFAULT 100");
		additions.put("plan_started_at", "TEXT");
		additions.put("plan_expires_at", "TEXT");
		additions.put("balance", "REAL NOT NULL DEFAULT 0");
		for (Map.Entry<String, String> entry : additions.entrySet()) {
			if (!columns.contains(entry.getKey())) {
				jdbcTemplate.execute("ALTER TABLE user ADD COLUMN " + entry.getKey() + " " + entry.getValue());
				log.info("user 表补列 {}", entry.getKey());
			}
		}
	}

	private void seedPlanCatalog() {
		jdbcTemplate.update("INSERT OR IGNORE INTO plan_catalog(code, price, credits, duration_days) VALUES('free', 0, 100, 30)");
		jdbcTemplate.update("INSERT OR IGNORE INTO plan_catalog(code, price, credits, duration_days) VALUES('plus', 20, 500, 30)");
		jdbcTemplate.update("INSERT OR IGNORE INTO plan_catalog(code, price, credits, duration_days) VALUES('pro', 60, 2000, 30)");
		jdbcTemplate.update("INSERT OR IGNORE INTO plan_catalog(code, price, credits, duration_days) VALUES('ultra', 100, 4000, 30)");
	}

	private void seedModelCatalog() {
		jdbcTemplate.update("INSERT OR IGNORE INTO model_catalog(provider, model, display_name, plans, byok_supported, status) "
				+ "VALUES('bailian', 'qwen3.7-plus', 'Qwen3.7 Plus', 'plus,pro,ultra', 1, 'active')");
		jdbcTemplate.update("INSERT OR IGNORE INTO model_catalog(provider, model, display_name, plans, byok_supported, status) "
				+ "VALUES('bailian', 'qwen3.8-max', 'Qwen3.8 Max', 'pro,ultra', 1, 'active')");
	}
}
