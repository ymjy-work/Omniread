package com.omniread.billing.model;

public record AccountVO(String role, String plan, long credits, double balance, String planExpiresAt) {
}
