package com.omniread.backend.session;

import java.sql.SQLException;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Component;

/**
 * 往会话里追加消息，负责 `seq` 的取号与冲突重试。
 *
 * <p>取号规则是「写入前取 `MAX(seq)`，冲突重试」。之所以不能把取号塞进一条
 * `INSERT ... SELECT MAX(seq)+1`：调用方需要知道这条消息的 `seq`（分叉要按它切、
 * 前端要按它排序），而那种写法算出来的 `seq` 不会回传给调用方，还得再查一次。
 *
 * <p>**判冲突要看 SQLite 自己的错误码，不能只认 Spring 的异常类型**：Spring 对 SQLite 的
 * 约束错误翻译未必到位。所以这里两种都认——先认
 * `DataAccessException`，再回落到 `SQLException` 的错误码。
 */
@Component
public class ChatMessageStore {

    private static final Logger log = LoggerFactory.getLogger(ChatMessageStore.class);

    /**
     * 重试上限。定得比「够用」宽：撞车本身不罕见（两个标签页同开一个会话就会撞），
     * 而失败的表现是**整个请求报错**，代价远大于多等几十毫秒。
     */
    private static final int MAX_ATTEMPTS = 12;

    /**
     * 退避基数（毫秒）。**没有退避的重试在多个写者下会互相饿死**：大家在同一瞬间重取号、
     * 同一瞬间再撞，五次很快就烧完了——实测 6 个写者时必现。随机退避把重试点错开，
     * 让其中一个稳定地先过。取值很小，因为正常情况（一两个写者）根本不会退避。
     */
    private static final long BACKOFF_BASE_MILLIS = 2;

    /** SQLite 的 SQLITE_CONSTRAINT；扩展码低 8 位也是它（1555 / 2067 分别是主键与唯一冲突）。 */
    private static final int SQLITE_CONSTRAINT = 19;

    private final ChatMessageMapper mapper;

    public ChatMessageStore(ChatMessageMapper mapper) {
        this.mapper = mapper;
    }

    /**
     * 追加一条消息并返回它（`id` 与 `seq` 都已回填）。
     *
     * <p>每条消息独立一条 SQL，所以**调用方要自己保证 user 消息与它的 assistant 消息不交错**——
     * 目前一轮的写入是串行的，这个前提成立。
     */
    public ChatMessage append(
            String sessionId, String role, String content, Integer tokenCount, String meta) {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            ChatMessage message = new ChatMessage();
            message.setSessionId(sessionId);
            message.setSeq(nextSeq(sessionId));
            message.setRole(role);
            message.setContent(content);
            message.setTokenCount(tokenCount);
            message.setCreatedAt(Instant.now().toString());
            message.setMeta(meta);
            try {
                mapper.insert(message);
                return message;
            } catch (DataAccessException e) {
                if (!isSeqCollision(e)) {
                    throw e;
                }
                log.debug("seq 撞车，重取：session={} attempt={}", sessionId, attempt);
                backOff(attempt);
            }
        }
        throw new IllegalStateException(
                "连续 " + MAX_ATTEMPTS + " 次都没拿到 seq：会话 " + sessionId + " 的写入过于拥挤");
    }

    /** 随机退避：把并发写者的重试点错开，否则它们会同步地反复撞在一起。 */
    private static void backOff(int attempt) {
        try {
            Thread.sleep(ThreadLocalRandom.current().nextLong(BACKOFF_BASE_MILLIS * attempt + 1));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("等待重取 seq 时被中断", e);
        }
    }

    private int nextSeq(String sessionId) {
        Integer max = mapper.maxSeq(sessionId);
        return (max == null ? 0 : max) + 1;
    }

    /**
     * 这个异常是不是「`seq` 被别人抢先」。
     *
     * <p>SQLite 把唯一约束违反报成 `SQLITE_CONSTRAINT`（19）或它的扩展码。只看异常类型会漏：
     * 翻译器认不出 SQLite 的错误文本时给的是通用的 `DataIntegrityViolationException`，
     * 而那种异常也可能是外键失败——外键失败重试多少次都不会成功，混在一起会白转五圈。
     */
    private static boolean isSeqCollision(DataAccessException e) {
        Throwable cause = e.getMostSpecificCause();
        return cause instanceof SQLException sql && errorCodeIsConstraint(sql.getErrorCode());
    }

    private static boolean errorCodeIsConstraint(int code) {
        return code == SQLITE_CONSTRAINT || (code & 0xFF) == SQLITE_CONSTRAINT;
    }
}
