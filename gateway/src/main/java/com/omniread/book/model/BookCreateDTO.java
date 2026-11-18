package com.omniread.book.model;

import jakarta.validation.constraints.NotBlank;

public record BookCreateDTO(@NotBlank String title, String author, String coverUrl) {
}
