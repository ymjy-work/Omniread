package com.omniread.chat;

import java.util.List;

import com.omniread.auth.AuthInterceptor;
import com.omniread.chat.model.AskRequestDTO;
import com.omniread.chat.model.AskResponseVO;
import com.omniread.chat.model.ChatSessionEntity;
import com.omniread.chat.model.MessageVO;
import com.omniread.chat.model.SessionCreateDTO;
import com.omniread.common.Result;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/chat/sessions")
public class ChatController {

	private final ChatService chatService;

	public ChatController(ChatService chatService) {
		this.chatService = chatService;
	}

	@PostMapping
	public Result<ChatSessionEntity> createSession(
			@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId,
			@Valid @RequestBody SessionCreateDTO request) {
		return Result.ok(chatService.createSession(userId, request));
	}

	@GetMapping
	public Result<List<ChatSessionEntity>> listSessions(
			@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId,
			@RequestParam(required = false) Long bookId) {
		return Result.ok(chatService.listSessions(userId, bookId));
	}

	@GetMapping("/{id}/messages")
	public Result<List<MessageVO>> listMessages(
			@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId, @PathVariable long id) {
		return Result.ok(chatService.listMessages(userId, id));
	}

	@PostMapping("/{id}/ask")
	public Result<AskResponseVO> ask(@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId,
			@PathVariable long id, @Valid @RequestBody AskRequestDTO request) {
		return Result.ok(chatService.ask(userId, id, request));
	}
}
