package com.omniread.byok.model;

import jakarta.validation.constraints.NotBlank;

public record ApiKeySaveDTO(@NotBlank String provider, @NotBlank String key) {
}
