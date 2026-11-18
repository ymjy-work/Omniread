package com.omniread.chat.model;

import jakarta.validation.constraints.NotNull;

public record SessionCreateDTO(@NotNull Long bookId, String title) {
}
