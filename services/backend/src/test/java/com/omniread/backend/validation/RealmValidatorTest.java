package com.omniread.backend.validation;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.omniread.backend.contract.model.QueryRequest;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * realm 校验发生在 Java 边界（M0-01 §7）：Python 不重复校验，
 * 所以这里的漏判就是整条链的漏判 —— 越界的 progress 会直接变成检索范围。
 */
class RealmValidatorTest {

    private static final int CHAPTER_COUNT = 193;

    @Test
    @DisplayName("level=past 缺 progress 即非法")
    void pastRequiresProgress() {
        assertThatThrownBy(() -> RealmValidator.validateQuery(QueryRequest.LevelEnum.PAST, null, CHAPTER_COUNT))
                .isInstanceOf(RagException.class)
                .extracting(failure -> ((RagException) failure).code())
                .isEqualTo(ErrorCode.RAG_INVALID_REALM);
    }

    @Test
    @DisplayName("progress 超出 1..chapter_count 即非法")
    void progressOutOfBounds() {
        assertThatThrownBy(() -> RealmValidator.validateQuery(QueryRequest.LevelEnum.PAST, 0, CHAPTER_COUNT))
                .isInstanceOf(RagException.class);
        assertThatThrownBy(() -> RealmValidator.validateQuery(QueryRequest.LevelEnum.PAST, 194, CHAPTER_COUNT))
                .isInstanceOf(RagException.class);
        assertThatThrownBy(() -> RealmValidator.validateQuery(QueryRequest.LevelEnum.FULL, 194, CHAPTER_COUNT))
                .isInstanceOf(RagException.class);
    }

    @Test
    @DisplayName("边界值 1 与 chapter_count 合法")
    void boundsAreInclusive() {
        assertThatCode(() -> RealmValidator.validateQuery(QueryRequest.LevelEnum.PAST, 1, CHAPTER_COUNT))
                .doesNotThrowAnyException();
        assertThatCode(() -> RealmValidator.validateQuery(QueryRequest.LevelEnum.PAST, CHAPTER_COUNT, CHAPTER_COUNT))
                .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("level=full 时 progress 可省")
    void fullAllowsMissingProgress() {
        assertThatCode(() -> RealmValidator.validateQuery(QueryRequest.LevelEnum.FULL, null, CHAPTER_COUNT))
                .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("写进度同样受 chapter_count 约束")
    void progressWriteBounds() {
        assertThatCode(() -> RealmValidator.validateProgress(4, CHAPTER_COUNT)).doesNotThrowAnyException();
        assertThatThrownBy(() -> RealmValidator.validateProgress(0, CHAPTER_COUNT)).isInstanceOf(RagException.class);
        assertThatThrownBy(() -> RealmValidator.validateProgress(194, CHAPTER_COUNT)).isInstanceOf(RagException.class);
    }
}
