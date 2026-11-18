package com.omniread.reading.model;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record ProgressDTO(
		@NotNull @Min(1) Integer chapterIndex,
		@NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double scrollRatio) {
}
