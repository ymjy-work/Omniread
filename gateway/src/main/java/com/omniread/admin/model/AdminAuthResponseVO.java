package com.omniread.admin.model;

import com.omniread.auth.model.UserEntity;

/** 管理员后台登录会话：token + 带 role 的用户信息。 */
public record AdminAuthResponseVO(String token, UserVO user) {

	public static AdminAuthResponseVO of(String token, UserEntity user) {
		return new AdminAuthResponseVO(token,
				new UserVO(user.getId(), user.getUsername(), user.getDisplayName(), user.getRole()));
	}

	public record UserVO(long id, String username, String displayName, String role) {
	}
}
