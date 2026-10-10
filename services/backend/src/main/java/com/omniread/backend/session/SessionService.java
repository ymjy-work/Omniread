package com.omniread.backend.session;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;

/**
 * 对话会话的增删查。**每个入口都带 `userId`**，没有「不带账户」的重载——
 * 会话是用户数据，「忘了带上账户」在这里不该是一个能写出来的调用。
 *
 * <p>跨用户一律 403、不存在一律 404（`外部契约` 的 `{session_id}` 段写明了这个分工）。
 * 403 会让人知道「这个 id 存在」——但 id 是 uuid、猜不出来，而契约选的是把
 * 「不是你的」和「没有这个」分开，好让前端能分别处置。这条取舍记在契约里，不在这里重开。
 */
@Service
public class SessionService {

    /**
     * 还没问过时的标题；首轮之后由那一轮生成（D 阶段）。列是 NOT NULL，所以必须给一个。
     *
     * <p>public 是因为它是**用户能看见的一句话**，测试要按它断言——把断言写成
     * 「标题非空」就挡不住「占位符被改成空串以外的另一种空」这类改动。
     */
    public static final String PLACEHOLDER_TITLE = "新会话";

    private final ChatSessionMapper sessionMapper;
    private final ChatMessageMapper messageMapper;

    public SessionService(ChatSessionMapper sessionMapper, ChatMessageMapper messageMapper) {
        this.sessionMapper = sessionMapper;
        this.messageMapper = messageMapper;
    }

    /** 只返回调用者自己的会话，按最近活跃倒序（排序在 SQL 里，见 mapper）。 */
    public List<ChatSessionSummary> list(long userId) {
        return sessionMapper.findByUserId(userId).stream().map(ChatSessionSummary::of).toList();
    }

    /**
     * 新建一个空会话。档位在创建时定下并**在会话内固定**——切档位不就地改，走分叉。
     *
     * <p>**这里不校验 `book_id` 存不存在**：那条校验要问 Python 要目录，而会话创建是纯本地动作
     * （D 阶段落会话表那一步也是本地的）。把两者绑在一起的代价是「目录取不到就建不了会话」，
     * 而收益只是把一次 400 从「第一次提问」提前到「点新建」——第一次提问本来就要问目录要
     * `chapter_count`，那边判得更准。取舍记在这里，因为它看起来像漏了一条校验。
     */
    public ChatSessionSummary create(long userId, int bookId, String level) {
        Instant now = Instant.now();
        ChatSession session = new ChatSession();
        session.setId(UUID.randomUUID().toString());
        session.setUserId(userId);
        session.setBookId(bookId);
        session.setTitle(PLACEHOLDER_TITLE);
        session.setLevel(level);
        session.setCreatedAt(now.toString());
        session.setLastActiveAt(now.toString());
        sessionMapper.insert(session);

        return ChatSessionSummary.of(session);
    }

    /**
     * 详情，含全部消息（按 `seq` 升序）。
     *
     * <p>`messages` 里**不含 `meta`**：那是内部诊断用的，下发出去就会变成前端依赖的契约。
     */
    public SessionDetail detail(long userId, String sessionId) {
        ChatSession session = requireOwned(userId, sessionId);
        List<ChatMessageView> messages =
                messageMapper.findBySession(sessionId).stream().map(ChatMessageView::of).toList();
        return SessionDetail.of(session, messages);
    }

    /**
     * 删除会话，连同它的消息一起（外键 `ON DELETE CASCADE`，见 `schema.sql`）。
     *
     * <p>先 `requireOwned` 再删，而不是只靠 `deleteForUser` 的返回值：那样「不是你的」
     * 与「没有这个」会都变成 0 行，而契约要求它们分别给 403 与 404。
     */
    public void delete(long userId, String sessionId) {
        requireOwned(userId, sessionId);
        sessionMapper.deleteForUser(sessionId, userId);
    }

    /**
     * 取出属于该账户的会话，否则抛。
     *
     * <p>先按 id 取、再比 `user_id`，而不是直接 `findByIdForUser` 了事：后者分不出
     * 「没有这个会话」与「是别人的会话」，而这两种要分别给 404 与 403。
     */
    private ChatSession requireOwned(long userId, String sessionId) {
        ChatSession session = sessionMapper.findById(sessionId);
        if (session == null) {
            throw new RagException(ErrorCode.RAG_NOT_FOUND, "会话不存在");
        }
        if (!Objects.equals(session.getUserId(), userId)) {
            throw new RagException(ErrorCode.RAG_FORBIDDEN, "这不是你的会话");
        }
        return session;
    }
}
