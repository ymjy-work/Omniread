package com.omniread.chat.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/** level 缺省按 past（防剧透）处理。 */
public record AskRequestDTO(
		@NotBlank String question,
		@Pattern(regexp = "past|full", message = "level 只能是 past 或 full") String level) {
}
