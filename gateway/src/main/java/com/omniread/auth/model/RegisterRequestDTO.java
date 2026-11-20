package com.omniread.auth.model;

import jakarta.validation.constraints.NotBlank;

/** 注册请求；displayName 缺省时用 username。 */
public record RegisterRequestDTO(@NotBlank String username, @NotBlank String password,
		String displayName) {
}
