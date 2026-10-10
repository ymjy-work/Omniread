package com.omniread.backend.web;

import com.omniread.backend.session.ChatSessionSummary;
import com.omniread.backend.session.SessionCreateRequest;
import com.omniread.backend.session.SessionDetail;
import com.omniread.backend.session.SessionList;
import com.omniread.backend.session.SessionService;
import com.omniread.backend.user.AuthenticatedUser;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 会话的列表 / 新建 / 详情 / 删除。
 *
 * <p>契约里**没有消息写端点**：消息只在会话详情里读、在 `/query` 那一轮里写
 * （那是 D 阶段的事）。所以这里的「会话 CRUD」实际是这四条。
 *
 * <p>账户一律从 {@link AuthInterceptor#USER_ATTRIBUTE} 取，不从请求体或查询参数取——
 * 后者等于让调用方声明自己是谁。
 */
@RestController
@RequestMapping("/api/v1/sessions")
public class SessionController {

    private final SessionService sessionService;

    public SessionController(SessionService sessionService) {
        this.sessionService = sessionService;
    }

    @GetMapping
    public SessionList list(@RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        return new SessionList(sessionService.list(user.id()));
    }

    @PostMapping
    public ResponseEntity<ChatSessionSummary> create(
            @RequestBody @Valid SessionCreateRequest body,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        ChatSessionSummary created = sessionService.create(user.id(), body.bookId(), body.level());
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @GetMapping("/{sessionId}")
    public SessionDetail detail(
            @PathVariable String sessionId,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        return sessionService.detail(user.id(), sessionId);
    }

    @DeleteMapping("/{sessionId}")
    public ResponseEntity<Void> delete(
            @PathVariable String sessionId,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        sessionService.delete(user.id(), sessionId);
        return ResponseEntity.noContent().build();
    }
}
