package com.omniread.byok;

import java.util.List;

import com.omniread.byok.model.UserApiKeyEntity;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface ApiKeyMapper {

	@Select("SELECT * FROM user_api_key WHERE user_id = #{userId} ORDER BY provider")
	List<UserApiKeyEntity> listByUser(@Param("userId") long userId);

	@Select("SELECT * FROM user_api_key WHERE user_id = #{userId} AND provider = #{provider}")
	UserApiKeyEntity findByUserAndProvider(@Param("userId") long userId,
			@Param("provider") String provider);

	@Insert("INSERT INTO user_api_key(user_id, provider, encrypted_key, key_mask, status, created_at) "
			+ "VALUES(#{userId}, #{provider}, #{encryptedKey}, #{keyMask}, 'active', #{createdAt}) "
			+ "ON CONFLICT(user_id, provider) DO UPDATE SET "
			+ "encrypted_key = excluded.encrypted_key, key_mask = excluded.key_mask, "
			+ "status = 'active', last_checked_at = NULL")
	int upsert(UserApiKeyEntity key);

	@Delete("DELETE FROM user_api_key WHERE user_id = #{userId} AND provider = #{provider}")
	int deleteByUserAndProvider(@Param("userId") long userId, @Param("provider") String provider);
}
