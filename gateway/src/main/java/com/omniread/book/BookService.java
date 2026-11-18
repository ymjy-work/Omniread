package com.omniread.book;

import java.util.List;

import com.omniread.book.model.BookCreateDTO;
import com.omniread.book.model.BookDetailVO;
import com.omniread.book.model.BookEntity;
import com.omniread.book.model.ChapterEntity;
import com.omniread.book.model.ChapterVO;
import com.omniread.book.model.ChapterWriteDTO;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Timestamps;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

	private final BookMapper bookMapper;
	private final ChapterMapper chapterMapper;
	private final BookIndexService bookIndexService;

	public BookService(BookMapper bookMapper, ChapterMapper chapterMapper,
			BookIndexService bookIndexService) {
		this.bookMapper = bookMapper;
		this.chapterMapper = chapterMapper;
		this.bookIndexService = bookIndexService;
	}

	public List<BookEntity> listBooks() {
		return bookMapper.findAll();
	}

	public BookDetailVO getBook(long id) {
		return BookDetailVO.of(requireBook(id), chapterMapper.countByBook(id));
	}

	public List<ChapterVO> listChapters(long bookId) {
		requireBook(bookId);
		return chapterMapper.listByBook(bookId).stream().map(ChapterVO::of).toList();
	}

	public ChapterVO getChapter(long bookId, int chapterIndex) {
		requireBook(bookId);
		ChapterEntity chapter = chapterMapper.findByIndex(bookId, chapterIndex);
		if (chapter == null) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "章节不存在");
		}
		return ChapterVO.of(chapter);
	}

	@Transactional
	public BookDetailVO createBook(BookCreateDTO request) {
		BookEntity book = new BookEntity();
		book.setTitle(request.title());
		book.setAuthor(request.author());
		book.setCoverUrl(request.coverUrl());
		book.setCreatedAt(Timestamps.now());
		bookMapper.insert(book);
		return BookDetailVO.of(book, 0);
	}

	@Transactional
	public ChapterVO createChapter(long bookId, ChapterWriteDTO request) {
		requireBook(bookId);
		if (request.chapterIndex() == null || request.chapterIndex() < 1) {
			throw new BusinessException(ErrorCode.BAD_REQUEST, "chapterIndex 必须为正整数");
		}
		if (chapterMapper.findByIndex(bookId, request.chapterIndex()) != null) {
			throw new BusinessException(ErrorCode.BAD_REQUEST, "章节号已存在");
		}
		ChapterEntity chapter = new ChapterEntity();
		chapter.setBookId(bookId);
		chapter.setChapterIndex(request.chapterIndex());
		chapter.setTitle(request.title());
		chapter.setText(request.text());
		chapter.setCreatedAt(Timestamps.now());
		chapterMapper.insert(chapter);
		bookIndexService.triggerReindex(bookId);
		return ChapterVO.of(chapter);
	}

	@Transactional
	public ChapterVO updateChapter(long bookId, int chapterIndex, ChapterWriteDTO request) {
		requireBook(bookId);
		if (chapterMapper.updateContent(bookId, chapterIndex, request.title(), request.text()) == 0) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "章节不存在");
		}
		bookIndexService.triggerReindex(bookId);
		return ChapterVO.of(chapterMapper.findByIndex(bookId, chapterIndex));
	}

	@Transactional
	public void deleteChapter(long bookId, int chapterIndex) {
		requireBook(bookId);
		if (chapterMapper.deleteByIndex(bookId, chapterIndex) == 0) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "章节不存在");
		}
		bookIndexService.triggerReindex(bookId);
	}

	private BookEntity requireBook(long id) {
		BookEntity book = bookMapper.findById(id);
		if (book == null) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "书籍不存在");
		}
		return book;
	}
}
