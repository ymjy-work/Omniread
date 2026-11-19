package com.omniread.chat;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface UsageRecordMapper {

	@Insert("INSERT INTO usage_record(user_id, session_id, mode, provider, model, "
			+ "prompt_tokens, completion_tokens, credits, created_at) "
			+ "VALUES(#{userId}, #{sessionId}, #{mode}, #{provider}, #{model}, "
			+ "#{promptTokens}, #{completionTokens}, #{credits}, #{createdAt})")
	int insert(@Param("userId") long userId, @Param("sessionId") long sessionId,
			@Param("mode") String mode, @Param("provider") String provider, @Param("model") String model,
			@Param("promptTokens") long promptTokens, @Param("completionTokens") long completionTokens,
			@Param("credits") int credits, @Param("createdAt") String createdAt);
}
