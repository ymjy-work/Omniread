package com.omniread.chat.model;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record MessageVO(long id, String role, String content,
		List<AskResponseVO.CitationVO> citations, String createdAt) {
}
