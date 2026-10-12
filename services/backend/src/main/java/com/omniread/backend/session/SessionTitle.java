package com.omniread.backend.session;

/**
 * 会话列表里的那一行标题：由**首轮那句问话**截出来（契约：`title`「首轮生成；还没问过时是占位标题」）。
 *
 * <p>**截断而不是概括**：标题是给列表认的，不是内容本身。概括要多一次模型调用，而那个调用
 * 换来的只是几个字；截出来的东西还**永远是用户自己说过的那句话**，不会被模型改写。
 *
 * <p>纯函数，所以「那句话会变成什么标题」能拿同一份输入重放——它是要长期留在库里、
 * 出现在每一行列表上的东西。
 */
public final class SessionTitle {

    /**
     * 上限。列表一行放得下十几个汉字，再多也只是被前端截掉；留 20 是让「这句话在问什么」
     * 还看得出来。
     */
    public static final int MAX_LENGTH = 20;

    private static final String ELLIPSIS = "…";

    private SessionTitle() {
    }

    /**
     * 首轮那句问话 → 标题。**空白问话返回 null**，调用方据此保留占位标题
     * （列是 NOT NULL，而空串标题在列表里就是一行什么都没有）。
     */
    public static String of(String question) {
        if (question == null) {
            return null;
        }
        // 换行与连续空白压成一个空格：标题是一行，带换行的标题在列表里会撑成两行。
        String flattened = question.strip().replaceAll("\\s+", " ");
        if (flattened.isEmpty()) {
            return null;
        }
        // 按**码点**数而不是 char 数：一个 emoji 占两个 char，按 char 切会切出半个代理对，
        // 存进库就是坏字符（同 TokenEstimator 里按码点遍历的理由）。
        if (flattened.codePointCount(0, flattened.length()) <= MAX_LENGTH) {
            return flattened;
        }
        return flattened.substring(0, flattened.offsetByCodePoints(0, MAX_LENGTH)) + ELLIPSIS;
    }
}
