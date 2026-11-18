package com.omniread.book;

import java.util.List;

import com.omniread.book.model.BookEntity;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface BookMapper {

	@Select("SELECT * FROM book ORDER BY id")
	List<BookEntity> findAll();

	@Select("SELECT * FROM book WHERE id = #{id}")
	BookEntity findById(@Param("id") long id);

	@Insert("INSERT INTO book(id, title, author, cover_url, created_at) "
			+ "VALUES(#{id}, #{title}, #{author}, #{coverUrl}, #{createdAt})")
	@Options(useGeneratedKeys = true, keyProperty = "id")
	int insert(BookEntity book);
}
