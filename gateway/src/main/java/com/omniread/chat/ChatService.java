package com.omniread.chat;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import com.omniread.auth.AuthMapper;
import com.omniread.auth.model.UserEntity;
import com.omniread.billing.AccountService;
import com.omniread.billing.LedgerMapper;
import com.omniread.book.BookMapper;
import com.omniread.byok.ApiKeyService;
import com.omniread.byok.model.UserApiKeyEntity;
import com.omniread.catalog.ModelCatalogMapper;
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
	private final AuthMapper authMapper;
	private final AccountService accountService;
	private final ApiKeyService apiKeyService;
	private final ModelCatalogMapper modelCatalogMapper;
	private final LedgerMapper ledgerMapper;
	private final UsageRecordMapper usageRecordMapper;
	private final ObjectMapper mapper = JsonMapper.builder().build();

	public ChatService(ChatMapper chatMapper, BookMapper bookMapper, ProgressMapper progressMapper,
			RagClient ragClient, AuthMapper authMapper, AccountService accountService,
			ApiKeyService apiKeyService, ModelCatalogMapper modelCatalogMapper,
			LedgerMapper ledgerMapper, UsageRecordMapper usageRecordMapper) {
		this.chatMapper = chatMapper;
		this.bookMapper = bookMapper;
		this.progressMapper = progressMapper;
		this.ragClient = ragClient;
		this.authMapper = authMapper;
		this.accountService = accountService;
		this.apiKeyService = apiKeyService;
		this.modelCatalogMapper = modelCatalogMapper;
		this.ledgerMapper = ledgerMapper;
		this.usageRecordMapper = usageRecordMapper;
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

	/** 校验模式与计费资格 → rag → 成功后条件扣积分并写 usage/credit 流水；失败不扣。 */
	public AskResponseVO ask(long userId, long sessionId, AskRequestDTO request) {
		ChatSessionEntity session = requireOwnedSession(userId, sessionId);
		UserEntity user = authMapper.findUserById(userId);
		if (user == null) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "用户不存在");
		}
		accountService.ensureCurrent(user);

		String level = request.level() == null || request.level().isBlank() ? "past" : request.level();
		String mode = request.mode() == null || request.mode().isBlank() ? "auto" : request.mode();
		String provider = null;
		String model = null;
		String apiKey = null;
		boolean chargeCredits = true;
		switch (mode) {
			case "auto" -> {
				// 所有档位可用，provider/model 忽略，由 rag 路由
			}
			case "platform" -> {
				if ("free".equals(user.getPlan())) {
					throw new BusinessException(ErrorCode.FORBIDDEN, "free 档仅支持 auto 模式");
				}
				if (request.model() == null || request.model().isBlank()) {
					throw new BusinessException(ErrorCode.BAD_REQUEST, "platform 模式必须指定 model");
				}
				if (modelCatalogMapper.findForPlan("bailian", request.model(), user.getPlan()) == null) {
					throw new BusinessException(ErrorCode.BAD_REQUEST, "模型不在当前套餐可用范围");
				}
				provider = "bailian";
				model = request.model();
			}
			case "byok" -> {
				if (request.model() == null || request.model().isBlank()) {
					throw new BusinessException(ErrorCode.BAD_REQUEST, "byok 模式必须填写 model");
				}
				UserApiKeyEntity stored = apiKeyService.requireStoredKey(userId, request.provider());
				provider = request.provider();
				model = request.model();
				apiKey = apiKeyService.decryptKey(stored);
				chargeCredits = false;
			}
			default -> throw new BusinessException(ErrorCode.BAD_REQUEST, "mode 只能是 auto、platform 或 byok");
		}
		if (chargeCredits && user.getCredits() < 1) {
			throw new BusinessException(ErrorCode.INSUFFICIENT_CREDITS);
		}

		Integer progress = null;
		if ("past".equals(level)) {
			ReadingProgressEntity current = progressMapper.findByUserAndBook(userId, session.getBookId());
			progress = current == null ? 1 : current.getChapterIndex();
		}
		List<ChatMessageEntity> history = new ArrayList<>(chatMapper.listRecentMessages(sessionId, HISTORY_LIMIT));
		Collections.reverse(history);

		insertMessage(sessionId, "user", request.question(), null);
		AskResponseVO response = ragClient.ask(new RagClient.AskCommand(session.getBookId(),
				request.question(), level, progress, history, TOP_K, mode, provider, model, apiKey));

		int creditsUsed = 0;
		if (chargeCredits) {
			if (authMapper.deductCredit(userId) == 0) {
				throw new BusinessException(ErrorCode.INSUFFICIENT_CREDITS);
			}
			creditsUsed = 1;
			ledgerMapper.insertCredit(userId, "usage", -1, user.getCredits() - 1,
					"session:" + sessionId, Timestamps.now());
		}
		usageRecordMapper.insert(userId, sessionId, mode, response.usage().provider(),
				response.usage().model(), response.usage().promptTokens(),
				response.usage().completionTokens(), creditsUsed, Timestamps.now());
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
