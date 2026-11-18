package com.omniread.auth;

import com.omniread.auth.model.UserEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface AuthMapper {

	@Select("SELECT * FROM user WHERE username = #{username}")
	UserEntity findUserByUsername(@Param("username") String username);

	@Insert("INSERT INTO user(username, password_hash, display_name, created_at) "
			+ "VALUES(#{username}, #{passwordHash}, #{displayName}, #{createdAt})")
	@Options(useGeneratedKeys = true, keyProperty = "id")
	int insertUser(UserEntity user);

	@Insert("INSERT INTO login_attempt(username, ip, success, created_at) "
			+ "VALUES(#{username}, #{ip}, #{success}, #{createdAt})")
	int insertLoginAttempt(@Param("username") String username, @Param("ip") String ip,
			@Param("success") boolean success, @Param("createdAt") String createdAt);

	@Select("SELECT COUNT(*) FROM login_attempt "
			+ "WHERE success = 0 AND created_at >= #{since} AND (username = #{username} OR ip = #{ip})")
	long countRecentFailures(@Param("username") String username, @Param("ip") String ip,
			@Param("since") String since);
}
