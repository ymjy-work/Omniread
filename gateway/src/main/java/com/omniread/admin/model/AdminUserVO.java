package com.omniread.admin.model;

import com.omniread.auth.model.UserEntity;

public record AdminUserVO(long id, String username, String displayName, String role, String plan,
		long credits, double balance, String planExpiresAt, String createdAt) {

	public static AdminUserVO of(UserEntity user) {
		return new AdminUserVO(user.getId(), user.getUsername(), user.getDisplayName(), user.getRole(),
				user.getPlan(), user.getCredits(), user.getBalance(), user.getPlanExpiresAt(),
				user.getCreatedAt());
	}
}
