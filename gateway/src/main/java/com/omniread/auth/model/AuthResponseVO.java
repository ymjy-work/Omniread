package com.omniread.auth.model;

public record AuthResponseVO(String token, UserVO user) {

	public record UserVO(long id, String username, String displayName) {
	}
}
