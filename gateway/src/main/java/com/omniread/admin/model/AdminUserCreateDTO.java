package com.omniread.admin.model;

import jakarta.validation.constraints.NotBlank;

public record AdminUserCreateDTO(@NotBlank String username, @NotBlank String password,
		String displayName) {
}
