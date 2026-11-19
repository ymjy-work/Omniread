package com.omniread.chat;

import java.net.http.HttpResponse;

import com.omniread.auth.AuthMapper;
import com.omniread.auth.model.UserEntity;
import com.omniread.book.BookMapper;
import com.omniread.book.model.BookEntity;
import com.omniread.common.Timestamps;
import com.omniread.support.IntegrationTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import tools.jackson.databind.JsonNode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ChatAskTest extends IntegrationTestBase {

	@Autowired
	private BookMapper bookMapper;

	@Autowired
	private AuthMapper authMapper;

	private long seedBook() {
		BookEntity book = new BookEntity();
		book.setTitle("会话测试书");
		book.setCreatedAt(Timestamps.now());
		bookMapper.insert(book);
		return book.getId();
	}

	@Test
	void askPersistsMessagesAndSendsProgressAndHistory() throws Exception {
		long bookId = seedBook();
		String token = adminToken();

		JsonNode session = json(send("POST", "/api/chat/sessions",
				"{\"bookId\":" + bookId + ",\"title\":\"测试会话\"}", token));
		long sessionId = session.path("data").path("id").asLong();
		assertTrue(sessionId > 0);

		send("PUT", "/api/books/" + bookId + "/progress",
				"{\"chapterIndex\":2,\"scrollRatio\":0.3}", token);

		HttpResponse<String> first = send("POST", "/api/chat/sessions/" + sessionId + "/ask",
				"{\"question\":\"她是谁？\",\"level\":\"past\"}", token);
		assertEquals(200, first.statusCode());
		JsonNode firstBody = json(first);
		assertEquals(STUB_ANSWER, firstBody.path("data").path("answer").asString());
		assertEquals(1, firstBody.path("data").path("citations").size());
		assertEquals("book:1:chapter:1",
				firstBody.path("data").path("citations").get(0).path("chapterId").asString());

		JsonNode ragRequest = MAPPER.readTree(LAST_ASK_BODY.get());
		assertEquals(bookId, ragRequest.path("book_id").asLong());
		assertEquals(2, ragRequest.path("progress").asInt());
		assertEquals("past", ragRequest.path("level").asString());
		assertEquals(8, ragRequest.path("top_k").asInt());
		assertEquals(0, ragRequest.path("history").size());

		JsonNode messages = json(send("GET", "/api/chat/sessions/" + sessionId + "/messages", null, token));
		assertEquals(2, messages.path("data").size());
		assertEquals("user", messages.path("data").get(0).path("role").asString());
		assertEquals("assistant", messages.path("data").get(1).path("role").asString());
		assertEquals(1, messages.path("data").get(1).path("citations").size());

		send("POST", "/api/chat/sessions/" + sessionId + "/ask",
				"{\"question\":\"再问一句\",\"level\":\"full\"}", token);
		JsonNode secondRequest = MAPPER.readTree(LAST_ASK_BODY.get());
		assertEquals(2, secondRequest.path("history").size());
		assertTrue(secondRequest.path("progress").isNull());

		JsonNode sessions = json(send("GET", "/api/chat/sessions?bookId=" + bookId, null, token));
		boolean found = false;
		for (JsonNode node : sessions.path("data")) {
			found |= node.path("id").asLong() == sessionId;
		}
		assertTrue(found);
	}

	@Test
	void invalidLevelReturns400() throws Exception {
		long bookId = seedBook();
		String token = adminToken();
		JsonNode session = json(send("POST", "/api/chat/sessions",
				"{\"bookId\":" + bookId + "}", token));
		long sessionId = session.path("data").path("id").asLong();
		HttpResponse<String> response = send("POST", "/api/chat/sessions/" + sessionId + "/ask",
				"{\"question\":\"x\",\"level\":\"future\"}", token);
		assertEquals(400, response.statusCode());
	}

	@Test
	void otherUsersSessionReturns403() throws Exception {
		long bookId = seedBook();
		String token = adminToken();
		JsonNode session = json(send("POST", "/api/chat/sessions",
				"{\"bookId\":" + bookId + "}", token));
		long sessionId = session.path("data").path("id").asLong();

		UserEntity other = new UserEntity();
		other.setUsername("other-user");
		other.setPasswordHash(new BCryptPasswordEncoder().encode("other-pass-1"));
		String now = Timestamps.now();
		other.setCreatedAt(now);
		other.setRole("user");
		other.setPlan("free");
		other.setCredits(100L);
		other.setPlanStartedAt(now);
		other.setPlanExpiresAt(Timestamps.plusDays(now, 30));
		other.setBalance(0.0);
		authMapper.insertUser(other);
		JsonNode login = json(send("POST", "/api/auth/login",
				"{\"username\":\"other-user\",\"password\":\"other-pass-1\"}", null));
		String otherToken = login.path("data").path("token").asString();

		HttpResponse<String> response = send("GET",
				"/api/chat/sessions/" + sessionId + "/messages", null, otherToken);
		assertEquals(403, response.statusCode());
		assertEquals(40300, json(response).path("code").asInt());
	}
}
