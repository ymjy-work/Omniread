package com.omniread.tools;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import com.omniread.book.BookIndexService;
import com.omniread.book.BookMapper;
import com.omniread.book.ChapterMapper;
import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SeedImporterTest extends IntegrationTestBase {

	@Autowired
	private BookMapper bookMapper;

	@Autowired
	private ChapterMapper chapterMapper;

	@Autowired
	private BookIndexService bookIndexService;

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Test
	void importsIdempotentlyWithLineNumbersAsChapterIndex() throws Exception {
		// 与其他测试共用库，先清掉 book 1 保证确定性
		jdbcTemplate.update("DELETE FROM chapter WHERE book_id = 1");
		jdbcTemplate.update("DELETE FROM book WHERE id = 1");

		Path jsonl = Files.createTempFile(Path.of("target"), "seed-test-", ".jsonl");
		jsonl.toFile().deleteOnExit();
		Files.write(jsonl, List.of(
				"{\"title\":\"序章\",\"text\":\"正文一\"}",
				"{\"title\":\"第一章\",\"text\":\"正文二\"}",
				"{\"title\":\"第二章\",\"text\":\"正文三\"}"), StandardCharsets.UTF_8);

		SeedImporter importer = new SeedImporter(bookMapper, chapterMapper, bookIndexService,
				jsonl.toString());
		importer.run(null);

		assertEquals("不时轻声地以俄语遮羞的邻座艾莉同学", bookMapper.findById(1).getTitle());
		assertEquals(3, chapterMapper.countByBook(1));
		assertEquals("第一章", chapterMapper.findByIndex(1, 2).getTitle());
		assertEquals("正文三", chapterMapper.findByIndex(1, 3).getText());

		importer.run(null);
		assertEquals(3, chapterMapper.countByBook(1));
	}
}
