package com.omniread.backend.web;

import com.omniread.backend.session.ChatSessionSummary;
import com.omniread.backend.session.ForkRequest;
import com.omniread.backend.session.SessionCreateRequest;
import com.omniread.backend.session.SessionDetail;
import com.omniread.backend.session.SessionList;
import com.omniread.backend.session.SessionRenameRequest;
import com.omniread.backend.session.SessionService;
import com.omniread.backend.user.AuthenticatedUser;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
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
        return new SessionList(sessionService.list(user.userId()));
    }

    @PostMapping
    public ResponseEntity<ChatSessionSummary> create(
            @RequestBody @Valid SessionCreateRequest body,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        ChatSessionSummary created = sessionService.create(user.userId(), body.bookId(), body.level());
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @GetMapping("/{session_id}")
    public SessionDetail detail(
            @PathVariable("session_id") String sessionId,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        return sessionService.detail(user.userId(), sessionId);
    }

    @DeleteMapping("/{session_id}")
    public ResponseEntity<Void> delete(
            @PathVariable("session_id") String sessionId,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        sessionService.delete(user.userId(), sessionId);
        return ResponseEntity.noContent().build();
    }

    /**
     * 改会话标题。挂在子资源上而不是 PATCH 整个会话：标题是唯一可改的字段，
     * 写口越窄，将来「反正能 PATCH」长出别的可改字段的机会越小。
     */
    @PutMapping("/{session_id}/title")
    public ChatSessionSummary rename(
            @PathVariable("session_id") String sessionId,
            @RequestBody @Valid SessionRenameRequest body,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        return sessionService.rename(user.userId(), sessionId, body.title());
    }

    /**
     * 切档位分叉。前端在用户切档位时**必须先弹确认**（既然叫分叉，就得让人知道旧会话还在），
     * 确认后才调这里——把这一步藏起来会让用户以为档位是就地切的，而旧会话其实还在。
     */
    @PostMapping("/{session_id}/fork")
    public ResponseEntity<ChatSessionSummary> fork(
            @PathVariable("session_id") String sessionId,
            @RequestBody @Valid ForkRequest body,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        ChatSessionSummary forked = sessionService.fork(user.userId(), sessionId, body.level(), body.atSeq());
        return ResponseEntity.status(HttpStatus.CREATED).body(forked);
    }
}
