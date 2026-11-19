package com.omniread.admin.model;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record BalanceGrantDTO(@NotNull @Positive Double amount, String reason) {
}
