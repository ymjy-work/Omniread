package com.omniread.backend.validation;

import com.omniread.backend.contract.model.QueryRequest;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;

/**
 * level / progress 在 Java 边界校验（M0-01 §7）：Python 不重复校验，
 * 因为校验需要 chapter_count，而 chapter_count 来自 GET /books —— 让 Java 当唯一的裁判，
 * 非法输入就不会先跑到检索层再被拒。
 *
 * 越界一律 RAG_INVALID_REALM / 400，与其他入参非法同一出口。
 */
public final class RealmValidator {

    public static void validateQuery(QueryRequest.LevelEnum level, Integer progress, int chapterCount) {
        if (level == QueryRequest.LevelEnum.PAST && progress == null) {
            throw invalid("level=past 时 progress 必填");
        }
        // progress 只要出现就必须落在该书章节范围内；level=full 时它不参与过滤，
        // 但接受一个越界值等于默许客户端把「已读到的章」写错。
        if (progress != null) {
            validateProgress(progress, chapterCount);
        }
    }

    public static void validateProgress(int maxSeq, int chapterCount) {
        if (maxSeq < 1 || maxSeq > chapterCount) {
            throw invalid("progress 必须在 1.." + chapterCount + " 内，收到 " + maxSeq);
        }
    }

    private static RagException invalid(String message) {
        return new RagException(ErrorCode.RAG_INVALID_REALM, message);
    }

    private RealmValidator() {
    }
}
