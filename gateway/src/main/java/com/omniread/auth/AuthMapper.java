package com.omniread.auth;

import java.util.List;

import com.omniread.auth.model.UserEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface AuthMapper {

	@Select("SELECT * FROM user WHERE username = #{username}")
	UserEntity findUserByUsername(@Param("username") String username);

	@Select("SELECT * FROM user WHERE id = #{id}")
	UserEntity findUserById(@Param("id") long id);

	@Select("SELECT * FROM user ORDER BY id")
	List<UserEntity> findAllUsers();

	@Insert("INSERT INTO user(username, password_hash, display_name, created_at, role, plan, credits, "
			+ "plan_started_at, plan_expires_at, balance) "
			+ "VALUES(#{username}, #{passwordHash}, #{displayName}, #{createdAt}, #{role}, #{plan}, #{credits}, "
			+ "#{planStartedAt}, #{planExpiresAt}, #{balance})")
	@Options(useGeneratedKeys = true, keyProperty = "id")
	int insertUser(UserEntity user);

	@Update("UPDATE user SET role = #{role} WHERE id = #{id}")
	int updateRole(@Param("id") long id, @Param("role") String role);

	@Update("UPDATE user SET plan = #{plan}, credits = #{credits}, "
			+ "plan_started_at = #{startedAt}, plan_expires_at = #{expiresAt} WHERE id = #{id}")
	int startCycle(@Param("id") long id, @Param("plan") String plan, @Param("credits") long credits,
			@Param("startedAt") String startedAt, @Param("expiresAt") String expiresAt);

	@Update("UPDATE user SET balance = balance + #{amount} WHERE id = #{id}")
	int addBalance(@Param("id") long id, @Param("amount") double amount);

	@Update("UPDATE user SET balance = balance - #{amount} WHERE id = #{id} AND balance >= #{amount}")
	int deductBalance(@Param("id") long id, @Param("amount") double amount);

	@Update("UPDATE user SET credits = credits - 1 WHERE id = #{id} AND credits >= 1")
	int deductCredit(@Param("id") long id);

	@Insert("INSERT INTO login_attempt(username, ip, success, created_at) "
			+ "VALUES(#{username}, #{ip}, #{success}, #{createdAt})")
	int insertLoginAttempt(@Param("username") String username, @Param("ip") String ip,
			@Param("success") boolean success, @Param("createdAt") String createdAt);

	@Select("SELECT COUNT(*) FROM login_attempt "
			+ "WHERE success = 0 AND created_at >= #{since} AND (username = #{username} OR ip = #{ip})")
	long countRecentFailures(@Param("username") String username, @Param("ip") String ip,
			@Param("since") String since);
}
