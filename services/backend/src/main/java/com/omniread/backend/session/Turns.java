package com.omniread.backend.session;

import java.util.ArrayList;
import java.util.List;

/**
 * 把一串消息配对成**轮次**（一问一答）。
 *
 * <p>两个地方要用同一个定义：{@link HistoryAssembler} 要「从最新往回取完整轮次」，
 * 摘要要「倒数第 N 轮之前」。各写一份就会漂成两个「第几轮」，而漂了之后两边都不报错，
 * 只是带上模型的上下文少一段或多一段。
 *
 * <p>正常形状是严格交替的 `user, assistant, user, assistant…`，但库里可能出现两种残缺：
 * 尾部一条没有回答的用户消息（上一轮失败留下的），或一条前面没有用户的助手消息。
 * 两种都**单独成轮而不是丢掉**——丢掉会让模型看到一段凭空开始的对话，
 * 而它并不知道前面少了一段。
 */
public final class Turns {

    private Turns() {
    }

    /** 输入按 `seq` 升序（`findBySession` 就是这么返回的）。 */
    public static List<Turn> of(List<ChatMessage> messages) {
        List<Turn> turns = new ArrayList<>();
        int index = 0;
        while (index < messages.size()) {
            ChatMessage current = messages.get(index);
            if (ChatMessage.ROLE_USER.equals(current.getRole())) {
                ChatMessage next = index + 1 < messages.size() ? messages.get(index + 1) : null;
                if (next != null && ChatMessage.ROLE_ASSISTANT.equals(next.getRole())) {
                    turns.add(new Turn(current, next));
                    index += 2;
                    continue;
                }
                turns.add(new Turn(current, null));
                index += 1;
                continue;
            }
            turns.add(new Turn(null, current));
            index += 1;
        }
        return turns;
    }

    /** 一轮：一问一答。残缺时其中一侧为 null。 */
    public record Turn(ChatMessage user, ChatMessage assistant) {

        public List<ChatMessage> messages() {
            if (user == null) {
                return List.of(assistant);
            }
            if (assistant == null) {
                return List.of(user);
            }
            return List.of(user, assistant);
        }

        public int tokens() {
            return Turns.tokens(messages());
        }
    }

    /**
     * 若干消息的 token 之和。
     *
     * <p>没记过 token 数的消息按内容现算：老数据或异常路径可能留空，当成 0 会让它变成
     * 「免费」的历史，一路把预算撑爆。
     */
    public static int tokens(List<ChatMessage> messages) {
        int total = 0;
        for (ChatMessage message : messages) {
            Integer count = message.getTokenCount();
            total += count != null ? count : TokenEstimator.estimate(message.getContent());
        }
        return total;
    }
}
