package com.omniread.chat;

import java.util.List;

import com.omniread.chat.model.ChatMessageEntity;
import com.omniread.chat.model.ChatSessionEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface ChatMapper {

	@Insert("INSERT INTO chat_session(user_id, book_id, title, created_at, updated_at) "
			+ "VALUES(#{userId}, #{bookId}, #{title}, #{createdAt}, #{updatedAt})")
	@Options(useGeneratedKeys = true, keyProperty = "id")
	int insertSession(ChatSessionEntity session);

	@Select("SELECT * FROM chat_session WHERE id = #{id}")
	ChatSessionEntity findSessionById(@Param("id") long id);

	@Select("<script>SELECT * FROM chat_session WHERE user_id = #{userId} "
			+ "<if test='bookId != null'>AND book_id = #{bookId}</if> "
			+ "ORDER BY updated_at DESC, id DESC</script>")
	List<ChatSessionEntity> listSessions(@Param("userId") long userId, @Param("bookId") Long bookId);

	@Update("UPDATE chat_session SET updated_at = #{updatedAt} WHERE id = #{id}")
	int touchSession(@Param("id") long id, @Param("updatedAt") String updatedAt);

	@Insert("INSERT INTO chat_message(session_id, role, content, citations_json, created_at) "
			+ "VALUES(#{sessionId}, #{role}, #{content}, #{citationsJson}, #{createdAt})")
	@Options(useGeneratedKeys = true, keyProperty = "id")
	int insertMessage(ChatMessageEntity message);

	@Select("SELECT * FROM chat_message WHERE session_id = #{sessionId} ORDER BY id")
	List<ChatMessageEntity> listMessages(@Param("sessionId") long sessionId);

	@Select("SELECT * FROM chat_message WHERE session_id = #{sessionId} ORDER BY id DESC LIMIT #{limit}")
	List<ChatMessageEntity> listRecentMessages(@Param("sessionId") long sessionId, @Param("limit") int limit);
}
