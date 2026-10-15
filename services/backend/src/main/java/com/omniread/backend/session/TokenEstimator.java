package com.omniread.backend.session;

/**
 * 字符级的 token 估算。**Java 侧不引分词器**（`docs/方案.md（依赖与选型一节）` §五）：
 * 这个数字只用来裁剪「近轮原文」的预算，差几个百分点不影响结果；真实用量由 Python 的
 * `usage` 回报，那才是权威值。
 *
 * <p>系数取自本项目自己的实测：chunking profile 记 {@code hanzi_per_600_tokens = 738.7}，
 * 即每个汉字约 {@code 600 / 738.7 ≈ 0.81} token；标点、字母、数字按约 0.3 估。
 *
 * <p>**这不是「算得准的近似」，是「算得稳的标尺」**：同一段文字每次都得到同一个数，
 * 裁剪结果才可复现。换系数等于换基线，与检索参数同理。
 */
public final class TokenEstimator {

    /** 每个汉字的 token 数。 */
    static final double HANZI_TOKENS = 0.81;

    /** 非汉字字符（标点 / 字母 / 数字 / 空白）的 token 数。 */
    static final double OTHER_TOKENS = 0.3;

    private TokenEstimator() {
    }

    /** 估算一段文本的 token 数；空串为 0。 */
    public static int estimate(String text) {
        if (text == null || text.isEmpty()) {
            return 0;
        }
        long hanzi = 0;
        long other = 0;
        int index = 0;
        while (index < text.length()) {
            int codePoint = text.codePointAt(index);
            if (Character.UnicodeScript.of(codePoint) == Character.UnicodeScript.HAN) {
                hanzi++;
            } else {
                other++;
            }
            index += Character.charCount(codePoint);
        }
        return (int) Math.round(hanzi * HANZI_TOKENS + other * OTHER_TOKENS);
    }
}
