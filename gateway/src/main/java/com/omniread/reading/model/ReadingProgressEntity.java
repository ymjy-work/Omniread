package com.omniread.reading.model;

/** reading_progress 表行。 */
public class ReadingProgressEntity {

	private Long id;
	private Long userId;
	private Long bookId;
	private Integer chapterIndex;
	private Double scrollRatio;
	private String updatedAt;

	public Long getId() {
		return id;
	}

	public void setId(Long id) {
		this.id = id;
	}

	public Long getUserId() {
		return userId;
	}

	public void setUserId(Long userId) {
		this.userId = userId;
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

	public Double getScrollRatio() {
		return scrollRatio;
	}

	public void setScrollRatio(Double scrollRatio) {
		this.scrollRatio = scrollRatio;
	}

	public String getUpdatedAt() {
		return updatedAt;
	}

	public void setUpdatedAt(String updatedAt) {
		this.updatedAt = updatedAt;
	}
}
