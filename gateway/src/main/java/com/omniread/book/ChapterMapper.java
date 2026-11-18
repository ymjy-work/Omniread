package com.omniread.book;

import java.util.List;

import com.omniread.book.model.ChapterEntity;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface ChapterMapper {

	@Select("SELECT id, book_id, chapter_index, title, created_at FROM chapter "
			+ "WHERE book_id = #{bookId} ORDER BY chapter_index")
	List<ChapterEntity> listByBook(@Param("bookId") long bookId);

	@Select("SELECT * FROM chapter WHERE book_id = #{bookId} ORDER BY chapter_index")
	List<ChapterEntity> listWithTextByBook(@Param("bookId") long bookId);

	@Select("SELECT * FROM chapter WHERE book_id = #{bookId} AND chapter_index = #{chapterIndex}")
	ChapterEntity findByIndex(@Param("bookId") long bookId, @Param("chapterIndex") int chapterIndex);

	@Select("SELECT COUNT(*) FROM chapter WHERE book_id = #{bookId}")
	long countByBook(@Param("bookId") long bookId);

	@Insert("INSERT INTO chapter(book_id, chapter_index, title, text, created_at) "
			+ "VALUES(#{bookId}, #{chapterIndex}, #{title}, #{text}, #{createdAt})")
	@Options(useGeneratedKeys = true, keyProperty = "id")
	int insert(ChapterEntity chapter);

	@Insert("INSERT INTO chapter(book_id, chapter_index, title, text, created_at) "
			+ "VALUES(#{bookId}, #{chapterIndex}, #{title}, #{text}, #{createdAt}) "
			+ "ON CONFLICT(book_id, chapter_index) DO UPDATE SET title = excluded.title, text = excluded.text")
	int upsert(ChapterEntity chapter);

	@Update("UPDATE chapter SET title = #{title}, text = #{text} "
			+ "WHERE book_id = #{bookId} AND chapter_index = #{chapterIndex}")
	int updateContent(@Param("bookId") long bookId, @Param("chapterIndex") int chapterIndex,
			@Param("title") String title, @Param("text") String text);

	@Delete("DELETE FROM chapter WHERE book_id = #{bookId} AND chapter_index = #{chapterIndex}")
	int deleteByIndex(@Param("bookId") long bookId, @Param("chapterIndex") int chapterIndex);
}
