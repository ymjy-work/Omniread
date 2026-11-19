package com.omniread.chat.model;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record AskResponseVO(String answer, List<CitationVO> citations, UsageVO usage) {

	/** 引用只带 chapter_id 定位信息，前端凭它向 gateway 取整章。 */
	public record CitationVO(String chapterId, int chapterIndex, String title, String quote) {
	}

	/** 本次回答的模式与实际路由、token 用量。 */
	public record UsageVO(String mode, String provider, String model, long promptTokens,
			long completionTokens) {
	}
}
