package com.omniread.book;

import java.net.http.HttpResponse;

import com.omniread.book.model.BookEntity;
import com.omniread.book.model.ChapterEntity;
import com.omniread.common.Timestamps;
import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BookChapterTest extends IntegrationTestBase {

	@Autowired
	private BookMapper bookMapper;

	@Autowired
	private ChapterMapper chapterMapper;

	private long seedBook(String title) {
		BookEntity book = new BookEntity();
		book.setTitle(title);
		book.setAuthor("测试作者");
		book.setCreatedAt(Timestamps.now());
		bookMapper.insert(book);
		for (int i = 1; i <= 2; i++) {
			ChapterEntity chapter = new ChapterEntity();
			chapter.setBookId(book.getId());
			chapter.setChapterIndex(i);
			chapter.setTitle("第" + i + "章");
			chapter.setText("第" + i + "章完整正文。");
			chapter.setCreatedAt(Timestamps.now());
			chapterMapper.insert(chapter);
		}
		return book.getId();
	}

	@Test
	void listAndDetailAndChapters() throws Exception {
		long bookId = seedBook("章节查询测试书");
		String token = adminToken();

		JsonNode list = json(send("GET", "/api/books", null, token));
		boolean found = false;
		for (JsonNode node : list.path("data")) {
			found |= node.path("id").asLong() == bookId;
		}
		assertTrue(found);

		JsonNode detail = json(send("GET", "/api/books/" + bookId, null, token));
		assertEquals(2, detail.path("data").path("chapterCount").asInt());

		JsonNode chapters = json(send("GET", "/api/books/" + bookId + "/chapters", null, token));
		assertEquals(2, chapters.path("data").size());
		assertFalse(chapters.path("data").get(0).has("text"));

		JsonNode chapter = json(send("GET", "/api/books/" + bookId + "/chapters/1", null, token));
		assertEquals("第1章完整正文。", chapter.path("data").path("text").asString());
	}

	@Test
	void missingBookOrChapterReturns404() throws Exception {
		String token = adminToken();
		HttpResponse<String> missingBook = send("GET", "/api/books/999999", null, token);
		assertEquals(404, missingBook.statusCode());
		assertEquals(40400, json(missingBook).path("code").asInt());

		long bookId = seedBook("404测试书");
		HttpResponse<String> missingChapter =
				send("GET", "/api/books/" + bookId + "/chapters/99", null, token);
		assertEquals(404, missingChapter.statusCode());
	}

	@Test
	void createChapterThenRead() throws Exception {
		long bookId = seedBook("章节写入测试书");
		String token = adminToken();
		HttpResponse<String> created = send("POST", "/api/books/" + bookId + "/chapters",
				"{\"chapterIndex\":3,\"title\":\"第3章\",\"text\":\"新增正文。\"}", token);
		assertEquals(200, created.statusCode());
		assertEquals(0, json(created).path("code").asInt());

		JsonNode chapter = json(send("GET", "/api/books/" + bookId + "/chapters/3", null, token));
		assertEquals("新增正文。", chapter.path("data").path("text").asString());

		HttpResponse<String> duplicate = send("POST", "/api/books/" + bookId + "/chapters",
				"{\"chapterIndex\":3,\"title\":\"重复\",\"text\":\"x\"}", token);
		assertEquals(400, duplicate.statusCode());
	}
}
