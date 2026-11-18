package com.omniread.book.model;

import jakarta.validation.constraints.NotBlank;

/** 章节新增/编辑入参；新增时 chapterIndex 必填，编辑时以路径为准。 */
public record ChapterWriteDTO(Integer chapterIndex, @NotBlank String title, @NotBlank String text) {
}
