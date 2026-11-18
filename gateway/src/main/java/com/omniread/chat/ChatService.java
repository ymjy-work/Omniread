package com.omniread.chat;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import com.omniread.book.BookMapper;
import com.omniread.chat.model.AskRequestDTO;
import com.omniread.chat.model.AskResponseVO;
import com.omniread.chat.model.ChatMessageEntity;
import com.omniread.chat.model.ChatSessionEntity;
import com.omniread.chat.model.MessageVO;
import com.omniread.chat.model.SessionCreateDTO;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Timestamps;
import com.omniread.reading.ProgressMapper;
import com.omniread.reading.model.ReadingProgressEntity;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

@Service
public class ChatService {

	private static final int HISTORY_LIMIT = 6;
	private static final int TOP_K = 8;

	private final ChatMapper chatMapper;
	private final BookMapper bookMapper;
	private final ProgressMapper progressMapper;
	private final RagClient ragClient;
	private final ObjectMapper mapper = JsonMapper.builder().build();

	public ChatService(ChatMapper chatMapper, BookMapper bookMapper, ProgressMapper progressMapper,
			RagClient ragClient) {
		this.chatMapper = chatMapper;
		this.bookMapper = bookMapper;
		this.progressMapper = progressMapper;
		this.ragClient = ragClient;
	}

	@Transactional
	public ChatSessionEntity createSession(long userId, SessionCreateDTO request) {
		if (bookMapper.findById(request.bookId()) == null) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "书籍不存在");
		}
		ChatSessionEntity session = new ChatSessionEntity();
		session.setUserId(userId);
		session.setBookId(request.bookId());
		session.setTitle(request.title() == null || request.title().isBlank() ? "新会话" : request.title());
		session.setCreatedAt(Timestamps.now());
		session.setUpdatedAt(session.getCreatedAt());
		chatMapper.insertSession(session);
		return session;
	}

	public List<ChatSessionEntity> listSessions(long userId, Long bookId) {
		return chatMapper.listSessions(userId, bookId);
	}

	public List<MessageVO> listMessages(long userId, long sessionId) {
		requireOwnedSession(userId, sessionId);
		List<MessageVO> messages = new ArrayList<>();
		for (ChatMessageEntity message : chatMapper.listMessages(sessionId)) {
			messages.add(new MessageVO(message.getId(), message.getRole(), message.getContent(),
					parseCitations(message.getCitationsJson()), message.getCreatedAt()));
		}
		return messages;
	}

	/** 取 progress 与最近 6 条历史 → rag → 落 user/assistant 消息。rag 调用不包在事务里。 */
	public AskResponseVO ask(long userId, long sessionId, AskRequestDTO request) {
		ChatSessionEntity session = requireOwnedSession(userId, sessionId);
		String level = request.level() == null || request.level().isBlank() ? "past" : request.level();
		Integer progress = null;
		if ("past".equals(level)) {
			ReadingProgressEntity current = progressMapper.findByUserAndBook(userId, session.getBookId());
			progress = current == null ? 1 : current.getChapterIndex();
		}
		List<ChatMessageEntity> history = new ArrayList<>(chatMapper.listRecentMessages(sessionId, HISTORY_LIMIT));
		Collections.reverse(history);

		insertMessage(sessionId, "user", request.question(), null);
		AskResponseVO response = ragClient.ask(session.getBookId(), request.question(), level,
				progress, history, TOP_K);
		insertMessage(sessionId, "assistant", response.answer(),
				mapper.writeValueAsString(response.citations()));
		chatMapper.touchSession(sessionId, Timestamps.now());
		return response;
	}

	private void insertMessage(long sessionId, String role, String content, String citationsJson) {
		ChatMessageEntity message = new ChatMessageEntity();
		message.setSessionId(sessionId);
		message.setRole(role);
		message.setContent(content);
		message.setCitationsJson(citationsJson);
		message.setCreatedAt(Timestamps.now());
		chatMapper.insertMessage(message);
	}

	private ChatSessionEntity requireOwnedSession(long userId, long sessionId) {
		ChatSessionEntity session = chatMapper.findSessionById(sessionId);
		if (session == null) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "会话不存在");
		}
		if (session.getUserId() != userId) {
			throw new BusinessException(ErrorCode.FORBIDDEN);
		}
		return session;
	}

	private List<AskResponseVO.CitationVO> parseCitations(String citationsJson) {
		if (citationsJson == null || citationsJson.isBlank()) {
			return null;
		}
		return mapper.readValue(citationsJson, new TypeReference<List<AskResponseVO.CitationVO>>() {
		});
	}
}
