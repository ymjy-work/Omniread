package com.omniread.book.model;

/** chapter 表行；列表查询不带 text。 */
public class ChapterEntity {

	private Long id;
	private Long bookId;
	private Integer chapterIndex;
	private String title;
	private String text;
	private String createdAt;

	public Long getId() {
		return id;
	}

	public void setId(Long id) {
		this.id = id;
	}

	public Long getBookId() {
		return bookId;
	}

	public void setBookId(Long bookId) {
		this.bookId = bookId;
	}

	public Integer getChapterIndex() {
		return chapterIndex;
	}

	public void setChapterIndex(Integer chapterIndex) {
		this.chapterIndex = chapterIndex;
	}

	public String getTitle() {
		return title;
	}

	public void setTitle(String title) {
		this.title = title;
	}

	public String getText() {
		return text;
	}

	public void setText(String text) {
		this.text = text;
	}

	public String getCreatedAt() {
		return createdAt;
	}

	public void setCreatedAt(String createdAt) {
		this.createdAt = createdAt;
	}
}
