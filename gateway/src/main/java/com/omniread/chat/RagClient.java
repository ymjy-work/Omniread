package com.omniread.chat;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.omniread.book.model.ChapterEntity;
import com.omniread.chat.model.AskResponseVO;
import com.omniread.chat.model.ChatMessageEntity;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.config.AiProperties;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/** gateway 调用 rag 的唯一出站口，契约见 /v1/index 与 /v1/ask。 */
@Component
public class RagClient {

	private final AiProperties properties;
	private final HttpClient httpClient;
	private final ObjectMapper mapper = JsonMapper.builder().build();

	public RagClient(AiProperties properties) {
		this.properties = properties;
		this.httpClient = HttpClient.newBuilder()
				.connectTimeout(properties.getConnectTimeout())
				.build();
	}

	/** chapters 为整本书内容，rag 整体替换该书 chunk。 */
	public int index(long bookId, List<ChapterEntity> chapters) {
		List<Map<String, Object>> items = chapters.stream().map(chapter -> Map.<String, Object>of(
				"chapter_id", "book:" + bookId + ":chapter:" + chapter.getChapterIndex(),
				"chapter_index", chapter.getChapterIndex(),
				"title", chapter.getTitle(),
				"text", chapter.getText())).toList();
		JsonNode response = post("/v1/index",
				Map.of("book_id", bookId, "chapters", items), properties.getIndexTimeout());
		return response.path("indexed_chunks").asInt();
	}

	/** progress 为当前章节号；level=full 时传 null。history 为最近 6 条 user/assistant 消息。 */
	public AskResponseVO ask(long bookId, String question, String level, Integer progress,
			List<ChatMessageEntity> history, int topK) {
		Map<String, Object> body = new LinkedHashMap<>();
		body.put("book_id", bookId);
		body.put("question", question);
		body.put("level", level);
		body.put("progress", progress);
		body.put("history", history.stream()
				.map(message -> Map.of("role", message.getRole(), "content", message.getContent()))
				.toList());
		body.put("top_k", topK);
		JsonNode response = post("/v1/ask", body, properties.getAskTimeout());
		List<AskResponseVO.CitationVO> citations = new ArrayList<>();
		for (JsonNode node : response.path("citations")) {
			citations.add(new AskResponseVO.CitationVO(
					node.path("chapter_id").asString(),
					node.path("chapter_index").asInt(),
					node.path("title").asString(),
					node.path("quote").asString()));
		}
		return new AskResponseVO(response.path("answer").asString(), citations);
	}

	private JsonNode post(String path, Object body, Duration timeout) {
		try {
			HttpRequest request = HttpRequest.newBuilder(URI.create(properties.getBaseUrl() + path))
					.timeout(timeout)
					.header("Content-Type", "application/json")
					.POST(HttpRequest.BodyPublishers.ofString(
							mapper.writeValueAsString(body), StandardCharsets.UTF_8))
					.build();
			HttpResponse<String> response = httpClient.send(request,
					HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
			if (response.statusCode() / 100 != 2) {
				throw new BusinessException(ErrorCode.RAG_ERROR,
						"rag " + path + " 返回 HTTP " + response.statusCode());
			}
			return mapper.readTree(response.body());
		}
		catch (IOException e) {
			throw new BusinessException(ErrorCode.RAG_ERROR, "无法连接 rag 服务: " + e.getMessage());
		}
		catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new BusinessException(ErrorCode.RAG_ERROR, "rag 调用被中断");
		}
		catch (JacksonException e) {
			throw new BusinessException(ErrorCode.RAG_ERROR, "rag 响应解析失败");
		}
	}
}
