package com.omniread.backend.session;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 把会话的历史消息裁成能塞进这一轮上下文的那一段（`docs/m1/多轮会话落地方案.md` §三）。
 *
 * <p>**纯函数**：不查库、不看时间、不依赖 Spring，输入定了输出就定了。多轮的问题几乎都出在
 * 「这一轮到底带了哪些历史」上，把它做成纯函数才测得动——出问题时能拿着同一份输入重放。
 *
 * <p>五条规则，每条都有它防的事：
 *
 * <ol>
 *   <li><b>从最新往回取完整轮次</b>，累加 token 直到超预算 —— 半个轮次（只有问没有答）
 *       比不带更容易把模型带偏。
 *   <li><b>会话首轮用户消息始终带</b>，且不参与裁剪 —— 它是话题锚点。丢了它，
 *       一个一路追问下来的会话在第 20 轮时，模型已经无从知道最初问的是什么。
 *   <li><b>至少保留 {@code minRecentTurns} 轮</b>，即使超预算 —— 预算是个软目标，
 *       「这一轮完全没有上下文」比「稍微超一点」糟得多。
 *   <li><b>摘要单独传，不计入这里的预算</b> —— 它由调用方持有
 *       （{@code chat_sessions.summary}），不在这条链上。
 *   <li><b>历史不含当前这一轮</b> —— 调用方传进来的就是「这一轮之前」的消息。
 *       时序上天然成立：拼装发生在写当前 user 消息之前。
 * </ol>
 */
public final class HistoryAssembler {

    private HistoryAssembler() {
    }

    /**
     * @param messages 该会话在**这一轮之前**的全部消息，按 `seq` 升序
     */
    public static HistorySelection assemble(List<ChatMessage> messages, ContextBudget budget) {
        if (messages == null || messages.isEmpty()) {
            return HistorySelection.empty();
        }

        List<Turn> turns = toTurns(messages);
        List<Turn> selected = new ArrayList<>();
        int tokens = 0;

        // 规则 1 + 3：从最新往回整轮地取。
        for (int i = turns.size() - 1; i >= 0; i--) {
            Turn turn = turns.get(i);
            boolean mustKeep = selected.size() < budget.minRecentTurns();
            if (!mustKeep && tokens + turn.tokens() > budget.historyBudgetTokens()) {
                break;
            }
            selected.add(0, turn);
            tokens += turn.tokens();
        }

        // 规则 2：锚点。已经被选中的话不重复加。
        List<ChatMessage> included = new ArrayList<>();
        for (Turn turn : selected) {
            included.addAll(turn.messages());
        }
        ChatMessage anchor = firstUserMessage(messages);
        boolean anchorAdded = false;
        if (anchor != null && !included.contains(anchor)) {
            // 单独成条，不带它的回答：规则要的是「首轮用户消息」，不是「首轮对话」。
            included.add(0, anchor);
            anchorAdded = true;
        }

        return new HistorySelection(
                Collections.unmodifiableList(included),
                tokens,
                selected.size(),
                turns.size() - selected.size(),
                anchorAdded);
    }

    private static ChatMessage firstUserMessage(List<ChatMessage> messages) {
        for (ChatMessage message : messages) {
            if (ChatMessage.ROLE_USER.equals(message.getRole())) {
                return message;
            }
        }
        return null;
    }

    /**
     * 配对成轮次。
     *
     * <p>正常形状是严格交替的 `user, assistant, user, assistant…`，但库里可能出现两种残缺：
     * 尾部一条没有回答的用户消息（上一轮失败留下的），或一条前面没有用户的助手消息。
     * 两种都**单独成轮而不是丢掉**——丢掉会让模型看到一段凭空开始的对话，
     * 而它并不知道前面少了一段。
     */
    private static List<Turn> toTurns(List<ChatMessage> messages) {
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
    private record Turn(ChatMessage user, ChatMessage assistant) {

        List<ChatMessage> messages() {
            if (user == null) {
                return List.of(assistant);
            }
            if (assistant == null) {
                return List.of(user);
            }
            return List.of(user, assistant);
        }

        int tokens() {
            int total = 0;
            for (ChatMessage message : messages()) {
                Integer count = message.getTokenCount();
                // 没记过 token 数的消息按内容现算：老数据或异常路径可能留空，
                // 当成 0 会让它变成「免费」的历史，一路把预算撑爆。
                total += count != null ? count : TokenEstimator.estimate(message.getContent());
            }
            return total;
        }
    }
}
