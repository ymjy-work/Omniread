package com.omniread.backend.orchestration;

import com.omniread.backend.contract.model.HistoryMessage;
import com.omniread.backend.session.ChatMessage;
import java.util.ArrayList;
import java.util.List;

/**
 * 库里的消息 → 上游契约的 `HistoryMessage`（`role` + 截断后的 `content`）。
 *
 * <p>两个请求共用它：问答的 `history` 与摘要的 `messages`。契约给 `content` 限了
 * 8000 字（`maxLength: 8000`），而库里的正文没有上限——两处各写一份截断，迟早漂成两个
 * 长度口径，而超长的那一份换来的是 422，看起来像请求构造错了。
 *
 * <p>**截断而不是让请求失败**：历史是上下文，不是答案来源；为一条陈年长消息把当前这一轮
 * 整个打回，代价远大于少一段上下文。补一句标记是为了不静默——模型读得到，
 * 排查的人从库里也读得到。
 */
public final class UpstreamHistory {

    /** 契约里 `HistoryMessage.content` 的上限。 */
    public static final int MAX_CONTENT = 8000;

    public static final String TRUNCATION_MARK = "……（历史消息过长，已截断）";

    private UpstreamHistory() {
    }

    public static List<HistoryMessage> of(List<ChatMessage> messages) {
        List<HistoryMessage> contract = new ArrayList<>(messages.size());
        for (ChatMessage message : messages) {
            String content = truncate(message.getContent());
            if (isBlank(content)) {
                continue;
            }
            contract.add(new HistoryMessage(HistoryMessage.RoleEnum.fromValue(message.getRole()), content));
        }
        return contract;
    }

    /**
     * 空正文不进上游信封。契约给 `content` 定的是 `minLength: 1`，夹带一条空消息出去，
     * **整条请求**被判 400——症状是「请求非法」，而请求看上去没有任何问题。
     *
     * <p>它只会出现在模型一个 token 都没吐的那一轮（{@code AnswerStreamRecorder} 攒出来的是空串），
     * 也就是说这条消息本身是零信息，丢掉它没有人会少知道什么。不丢的后果比多一条少一条重得多：
     * 那条消息会一直留在「待压缩区间」里（区间起点由 `summary_upto` 钉住，而它推不动），
     * 于是每一次摘要都失败——一个「失败不推进、下次可重试」的设计被变成**永久失败**。
     */
    private static boolean isBlank(String content) {
        return content == null || content.isBlank();
    }

    public static String truncate(String content) {
        if (content == null || content.length() <= MAX_CONTENT) {
            return content;
        }
        return content.substring(0, MAX_CONTENT - TRUNCATION_MARK.length()) + TRUNCATION_MARK;
    }
}
