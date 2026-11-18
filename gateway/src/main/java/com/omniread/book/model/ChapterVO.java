package com.omniread.book.model;

import com.fasterxml.jackson.annotation.JsonInclude;

/** 章节出参；列表场景 text 为 null 不输出，单章查询带完整正文。 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ChapterVO(long id, long bookId, int chapterIndex, String title, String text,
		String createdAt) {

	public static ChapterVO of(ChapterEntity chapter) {
		return new ChapterVO(chapter.getId(), chapter.getBookId(), chapter.getChapterIndex(),
				chapter.getTitle(), chapter.getText(), chapter.getCreatedAt());
	}
}
