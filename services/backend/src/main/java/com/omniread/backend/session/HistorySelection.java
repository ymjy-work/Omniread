package com.omniread.backend.session;

import java.util.List;

/**
 * 拼装结果。
 *
 * <p>除了要发给 Python 的 {@code messages}，还带几个**只有出问题时才看、但缺了就没法查**的
 * 计数：裁掉了几轮、锚点是不是额外补的。多轮的回答不连贯时，第一个要回答的问题是
 * 「这一轮到底带了哪些历史」——只留一个消息列表就只能靠猜。
 *
 * @param messages 按时间升序的历史消息（含锚点）
 * @param estimatedTokens 被计入预算的那部分 token（**不含锚点**，锚点不参与裁剪）
 * @param turnsIncluded 完整取进来的轮数
 * @param turnsDropped 因超预算被裁掉的轮数
 * @param anchorAdded 锚点是否因为是额外补上的（而不是本来就在保留范围内）
 */
public record HistorySelection(
        List<ChatMessage> messages,
        int estimatedTokens,
        int turnsIncluded,
        int turnsDropped,
        boolean anchorAdded) {

    static HistorySelection empty() {
        return new HistorySelection(List.of(), 0, 0, 0, false);
    }

    public boolean isEmpty() {
        return messages.isEmpty();
    }
}
