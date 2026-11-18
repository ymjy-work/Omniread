package com.omniread.book.model;

public record BookDetailVO(long id, String title, String author, String coverUrl, long chapterCount,
		String createdAt) {

	public static BookDetailVO of(BookEntity book, long chapterCount) {
		return new BookDetailVO(book.getId(), book.getTitle(), book.getAuthor(), book.getCoverUrl(),
				chapterCount, book.getCreatedAt());
	}
}
