package com.omniread.reading;

import java.net.http.HttpResponse;

import com.omniread.book.BookMapper;
import com.omniread.book.model.BookEntity;
import com.omniread.common.Timestamps;
import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProgressTest extends IntegrationTestBase {

	@Autowired
	private BookMapper bookMapper;

	@Test
	void defaultThenPutThenGet() throws Exception {
		BookEntity book = new BookEntity();
		book.setTitle("进度测试书");
		book.setCreatedAt(Timestamps.now());
		bookMapper.insert(book);
		String token = adminToken();
		String path = "/api/books/" + book.getId() + "/progress";

		JsonNode initial = json(send("GET", path, null, token));
		assertEquals(1, initial.path("data").path("chapterIndex").asInt());
		assertEquals(0.0, initial.path("data").path("scrollRatio").asDouble());

		HttpResponse<String> put = send("PUT", path,
				"{\"chapterIndex\":2,\"scrollRatio\":0.5}", token);
		assertEquals(200, put.statusCode());

		JsonNode after = json(send("GET", path, null, token));
		assertEquals(2, after.path("data").path("chapterIndex").asInt());
		assertEquals(0.5, after.path("data").path("scrollRatio").asDouble());
	}

	@Test
	void invalidScrollRatioReturns400() throws Exception {
		BookEntity book = new BookEntity();
		book.setTitle("进度校验测试书");
		book.setCreatedAt(Timestamps.now());
		bookMapper.insert(book);
		HttpResponse<String> response = send("PUT", "/api/books/" + book.getId() + "/progress",
				"{\"chapterIndex\":1,\"scrollRatio\":1.5}", adminToken());
		assertEquals(400, response.statusCode());
		assertEquals(40000, json(response).path("code").asInt());
	}
}
