package com.omniread.common;

import java.util.List;

/** 分页数据载体，放在 Result.data 中。 */
public record PageResult<T>(List<T> list, long total, int page, int size) {
}
