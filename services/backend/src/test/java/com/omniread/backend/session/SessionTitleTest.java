package com.omniread.backend.session;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 首轮问话 → 会话标题。
 *
 * <p>纯函数，而它的输出会长期留在库里、出现在每一行列表上——所以边界要一条条钉住：
 * 切多长、换行怎么办、空问话怎么办、代理对会不会被切坏。
 */
class SessionTitleTest {

    @Test
    @DisplayName("短问话原样用，前后空白去掉")
    void shortQuestionIsUsedAsIs() {
        assertThat(SessionTitle.of("  政近为什么离开周防家？  ")).isEqualTo("政近为什么离开周防家？");
    }

    @Test
    @DisplayName("换行与连续空白压成一个空格：标题是一行")
    void whitespaceIsFlattened() {
        assertThat(SessionTitle.of("那她后来呢？\n\n顺便说说\t那个杯子"))
                .isEqualTo("那她后来呢？ 顺便说说 那个杯子");
    }

    @Test
    @DisplayName("恰好到上限不加省略号，超一个码点才加")
    void truncatesOnlyWhenTooLong() {
        String exact = "字".repeat(SessionTitle.MAX_LENGTH);

        assertThat(SessionTitle.of(exact)).isEqualTo(exact);
        assertThat(SessionTitle.of(exact + "多")).isEqualTo(exact + "…");
    }

    @Test
    @DisplayName("按码点切，不切出半个代理对")
    void neverSplitsASurrogatePair() {
        String title = SessionTitle.of("🙂".repeat(30));

        assertThat(title).endsWith("…");
        assertThat(title.codePointCount(0, title.length()))
                .as("20 个 emoji + 省略号")
                .isEqualTo(SessionTitle.MAX_LENGTH + 1);
        assertThat(hasLoneSurrogate(title)).as("落单的代理对存进库就是坏字符").isFalse();
    }

    @Test
    @DisplayName("空白问话给 null，调用方保留占位标题")
    void blankQuestionYieldsNull() {
        assertThat(SessionTitle.of(null)).isNull();
        assertThat(SessionTitle.of("")).isNull();
        assertThat(SessionTitle.of("   \n\t ")).isNull();
    }

    private static boolean hasLoneSurrogate(String text) {
        for (int index = 0; index < text.length(); index++) {
            char current = text.charAt(index);
            if (Character.isHighSurrogate(current)) {
                if (index + 1 >= text.length() || !Character.isLowSurrogate(text.charAt(index + 1))) {
                    return true;
                }
                index++;
            } else if (Character.isLowSurrogate(current)) {
                return true;
            }
        }
        return false;
    }
}
