package com.omniread.reading;

import com.omniread.reading.model.ReadingProgressEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface ProgressMapper {

	@Select("SELECT * FROM reading_progress WHERE user_id = #{userId} AND book_id = #{bookId}")
	ReadingProgressEntity findByUserAndBook(@Param("userId") long userId, @Param("bookId") long bookId);

	@Insert("INSERT INTO reading_progress(user_id, book_id, chapter_index, scroll_ratio, updated_at) "
			+ "VALUES(#{userId}, #{bookId}, #{chapterIndex}, #{scrollRatio}, #{updatedAt}) "
			+ "ON CONFLICT(user_id, book_id) DO UPDATE SET "
			+ "chapter_index = excluded.chapter_index, scroll_ratio = excluded.scroll_ratio, "
			+ "updated_at = excluded.updated_at")
	int upsert(ReadingProgressEntity progress);
}
