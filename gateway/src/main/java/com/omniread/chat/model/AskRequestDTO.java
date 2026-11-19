package com.omniread.chat.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/** level 缺省 past（防剧透）；mode 缺省 auto。platform/byok 的 provider/model 规则在 Service 校验。 */
public record AskRequestDTO(
		@NotBlank String question,
		@Pattern(regexp = "past|full", message = "level 只能是 past 或 full") String level,
		@Pattern(regexp = "auto|platform|byok", message = "mode 只能是 auto、platform 或 byok") String mode,
		String provider,
		String model) {
}
