package com.omniread.backend.session;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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
     * 改标题。**只改标题这一个字段**——档位固定在建立时（切档位要分叉），`book_id` 同理，
     * 所以这里不接受别的。
     *
     * <p>空白压成单个空格：标题是列表里的一行，带换行的标题会把那一行撑成两行。
     * 去完空白为空、或超过上限（按**码点**算，与首轮自动命名同一个数）都是
     * `RAG_INVALID_REQUEST`——这里**截断而不是拒绝**的话，用户输入的东西会被悄悄改掉。
     */
    public ChatSessionSummary rename(long userId, String sessionId, String rawTitle) {
        ChatSession session = requireOwned(userId, sessionId);
        String title = rawTitle.strip().replaceAll("\\s+", " ");
        if (title.isEmpty()) {
            throw new RagException(ErrorCode.RAG_INVALID_REQUEST, "标题不能为空");
        }
        if (title.codePointCount(0, title.length()) > SessionTitle.MAX_LENGTH) {
            throw new RagException(
                    ErrorCode.RAG_INVALID_REQUEST, "标题最多 " + SessionTitle.MAX_LENGTH + " 个字");
        }
        sessionMapper.updateTitle(session.getId(), title);
        session.setTitle(title);
        return ChatSessionSummary.of(session);
    }

    /**
     * 切档位分叉：新建一个会话，**复制**父会话截至 `atSeq` 的消息进去。
     *
     * <p>复制式而不是引用式：实现最简单，且删除时父子互不影响（引用式要么级联删掉父，
     * 要么留下悬空引用）。
     *
     * <p>父会话的档位与消息**一律不动**——用户看到的是「新开了一条」，原会话还在列表里。
     * 档位必须与原会话不同：相同即 400，不静默返回一个副本。后端悄悄接受的话，前端会以为
     * 切档位成功了，而用户看到的「新会话」其实还在旧档位上，症状是下一轮回答照旧带着旧边界。
     */
    @Transactional
    public ChatSessionSummary fork(long userId, String parentId, String newLevel, Integer atSeq) {
        ChatSession parent = requireOwned(userId, parentId);
        if (parent.getLevel().equals(newLevel)) {
            throw new RagException(
                    ErrorCode.RAG_INVALID_REQUEST,
                    "分叉后的档位必须与原会话不同（原会话已是 " + newLevel + "）");
        }

        List<ChatMessage> history = messageMapper.findBySession(parentId);
        int forkAtSeq = alignToCompleteTurn(history, atSeq);

        Instant now = Instant.now();
        ChatSession fork = new ChatSession();
        fork.setId(UUID.randomUUID().toString());
        fork.setUserId(userId);
        fork.setBookId(parent.getBookId());
        // 标题跟着父会话走：它是由首轮生成的那句话概括的，而首轮一定被复制进来了。
        fork.setTitle(parent.getTitle());
        fork.setLevel(newLevel);
        fork.setForkedFrom(parentId);
        fork.setForkedAtSeq(forkAtSeq);
        fork.setCreatedAt(now.toString());
        fork.setLastActiveAt(now.toString());
        sessionMapper.insert(fork);

        copyMessagesUpTo(history, fork.getId(), forkAtSeq);
        return ChatSessionSummary.of(fork);
    }

    /**
     * 把 `atSeq` 规整成一个**合法的分叉点**（含），规整而不是报错。
     *
     * <p>- 缺省（null）取最后一条；- 比最后一条还大就夹到最大值；- 落在 `user` 消息上
     * 就退到它前一条 `assistant`（半轮会让新会话以一条没有回答的 user 结尾，
     * 而下一轮再追加一条 user 时 prompt 里就出现连续两条 user，模型容易被带偏）；
     * - 前面没有 `assistant` 就退到 0（复制 0 条，得到一个空会话）。
     *
     * <p>纯函数，输入按 `seq` 升序（`findBySession` 就是这么返回的），所以它能单测。
     */
    static int alignToCompleteTurn(List<ChatMessage> history, Integer atSeq) {
        if (history.isEmpty()) {
            return 0;
        }
        int lastSeq = history.get(history.size() - 1).getSeq();
        int candidate = atSeq == null ? lastSeq : Math.min(atSeq, lastSeq);
        // 从后往前：跨过比 candidate 靠后的，停在第一条 `assistant` 上。
        // 若 candidate 正好是 user，这一步自然退到它的前一条 assistant。
        for (int i = history.size() - 1; i >= 0; i--) {
            ChatMessage message = history.get(i);
            if (message.getSeq() <= candidate && ChatMessage.ROLE_ASSISTANT.equals(message.getRole())) {
                return message.getSeq();
            }
        }
        return 0;
    }

    /** 复制前 `upToSeq` 条进新会话。入参是已经取好的列表，不再查一次库（同一事务里读两遍没必要）。 */
    private void copyMessagesUpTo(List<ChatMessage> history, String forkId, int upToSeq) {
        if (upToSeq <= 0) {
            return;
        }
        int seq = 0;
        for (ChatMessage message : history) {
            if (message.getSeq() > upToSeq) {
                break;
            }
            ChatMessage copy = new ChatMessage();
            copy.setSessionId(forkId);
            // 在新会话里从 1 重新编号：新会话自己的消息必须自成一个 1..n 的序列，
            // 否则下一轮的取号（MAX(seq)+1）会从一个空档开始。
            copy.setSeq(++seq);
            copy.setRole(message.getRole());
            copy.setContent(message.getContent());
            copy.setTokenCount(message.getTokenCount());
            // 时间戳沿用原来那条：这两条消息是那时候说的，不是分叉的时候说的。
            copy.setCreatedAt(message.getCreatedAt());
            copy.setMeta(message.getMeta());
            messageMapper.insert(copy);
        }
    }

    /**
     * 首轮那句问话顺手给会话起个名，返回改没改。
     *
     * <p>**只在还是占位标题时改**：分叉会把父会话的标题一并复制过来，而那是父会话首轮那句话
     * 截出来的——不判一下的话，标题会变成「这个会话里最后问的那句」，每问一句在列表里跳一次。
     *
     * <p>起名挂在**用户消息**落库这一侧，而不是回答那一侧：答案是模型给的，问话是用户给的；
     * 而且回答失败时（provider 挂了）会话也该有个名字。
     */
    public boolean renameFromFirstQuestion(ChatSession session, String question) {
        if (!PLACEHOLDER_TITLE.equals(session.getTitle())) {
            return false;
        }
        String title = SessionTitle.of(question);
        if (title == null) {
            return false;
        }
        sessionMapper.updateTitle(session.getId(), title);
        // 同一个对象这一轮还会被读（记录回答时顺手 touch），先在内存里对齐，
        // 免得同一轮里出现两个标题。
        session.setTitle(title);
        return true;
    }

    /**
     * 刷新会话的最近活跃时间。列表按它倒序，所以「继续上次」靠的就是这一下——
     * 不刷的话，用户接着聊的那个会话会一直沉在列表底部，而列表本身看不出任何异常。
     */
    public void touch(String sessionId) {
        sessionMapper.touch(sessionId, Instant.now().toString());
    }

    /**
     * 取出属于该账户的会话，否则抛。
     *
     * <p>先按 id 取、再比 `user_id`，而不是直接 `findByIdForUser` 了事：后者分不出
     * 「没有这个会话」与「是别人的会话」，而这两种要分别给 404 与 403。
     *
     * <p>public 是因为问答那一轮也要它：那里要拿会话的 `level` 与 `summary`，
     * 而「取之前先验归属」这件事不该在第二个地方再实现一遍。
     */
    public ChatSession requireOwned(long userId, String sessionId) {
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
