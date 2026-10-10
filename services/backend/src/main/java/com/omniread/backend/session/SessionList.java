package com.omniread.backend.session;

import java.util.List;

/**
 * 会话列表，与外部契约的 `SessionList` 一致。
 *
 * <p>包一层对象而不是直接返回数组：顶上再加字段（分页、总数）时不必换形状，
 * 而换形状会让前端那一次改动落在「解析根节点」这种最难看出问题的地方。
 */
public record SessionList(List<ChatSessionSummary> sessions) {
}
