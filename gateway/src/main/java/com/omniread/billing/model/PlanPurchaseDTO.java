package com.omniread.billing.model;

import jakarta.validation.constraints.NotBlank;

public record PlanPurchaseDTO(@NotBlank String plan) {
}
