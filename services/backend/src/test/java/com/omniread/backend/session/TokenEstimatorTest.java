package com.omniread.backend.session;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * token 估算的标尺（`docs/m1/java-依赖与选型.md` §五）。
 *
 * <p>它不是「算得准的近似」，是「算得稳的标尺」——同一段文字每次都得到同一个数，
 * 裁剪结果才可复现。所以这里钉的是**系数与口径**，不是与真实分词器的误差。
 */
class TokenEstimatorTest {

    @Test
    @DisplayName("汉字按 0.81、其它字符按 0.3")
    void followsTheDocumentedCoefficients() {
        assertThat(TokenEstimator.estimate("")).isZero();
        assertThat(TokenEstimator.estimate(null)).isZero();

        // 10 个汉字 × 0.81 = 8.1 → 8
        assertThat(TokenEstimator.estimate("一二三四五六七八九十")).isEqualTo(8);
        // 10 个字母 × 0.3 = 3
        assertThat(TokenEstimator.estimate("abcdefghij")).isEqualTo(3);
        // 3 个汉字 + 3 个标点 = 2.43 + 0.9 = 3.33 → 3
        assertThat(TokenEstimator.estimate("你好吗？？？")).isEqualTo(3);
    }

    @Test
    @DisplayName("标点、字母、数字都算「其它」——它们不占汉字的额度")
    void punctuationAndDigitsAreNotHanzi() {
        String hanziOnly = "四个汉字";
        String withPunctuation = "四个汉字！！";

        assertThat(TokenEstimator.estimate(withPunctuation))
                .isGreaterThan(TokenEstimator.estimate(hanziOnly));
    }

    @Test
    @DisplayName("同一段文字每次都得到同一个数")
    void isStableForTheSameInput() {
        String text = "政近忘带参考书，向邻座的艾莉莎借了一本。";

        assertThat(TokenEstimator.estimate(text)).isEqualTo(TokenEstimator.estimate(text));
        // 新串但内容相同：这是裁剪可复现的前提。
        assertThat(TokenEstimator.estimate(new String(text.toCharArray())))
                .isEqualTo(TokenEstimator.estimate(text));
    }

    @Test
    @DisplayName("按码点计数：代理对不会被拆成两个字符")
    void countsByCodePointNotByChar() {
        // 一个星形符号是代理对（两个 char、一个码点）。用 charAt 遍历会把它算成 2 个「其它」，
        // 估算随文本里 emoji 的多少漂移。
        assertThat(TokenEstimator.estimate("🌟")).isEqualTo(0); // 1 个码点 × 0.3 → 0
        assertThat(TokenEstimator.estimate("汉🌟")).isEqualTo(1); // 0.81 + 0.3 → 1
    }
}
