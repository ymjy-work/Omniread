package com.omniread.book;

import java.util.List;

import com.omniread.book.model.BookCreateDTO;
import com.omniread.book.model.BookDetailVO;
import com.omniread.book.model.BookEntity;
import com.omniread.book.model.ChapterVO;
import com.omniread.book.model.ChapterWriteDTO;
import com.omniread.common.Result;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

	private final BookService bookService;

	public BookController(BookService bookService) {
		this.bookService = bookService;
	}

	@GetMapping
	public Result<List<BookEntity>> listBooks() {
		return Result.ok(bookService.listBooks());
	}

	@PostMapping
	public Result<BookDetailVO> createBook(@Valid @RequestBody BookCreateDTO request) {
		return Result.ok(bookService.createBook(request));
	}

	@GetMapping("/{id}")
	public Result<BookDetailVO> getBook(@PathVariable long id) {
		return Result.ok(bookService.getBook(id));
	}

	@GetMapping("/{id}/chapters")
	public Result<List<ChapterVO>> listChapters(@PathVariable long id) {
		return Result.ok(bookService.listChapters(id));
	}

	@GetMapping("/{id}/chapters/{chapterIndex}")
	public Result<ChapterVO> getChapter(@PathVariable long id, @PathVariable int chapterIndex) {
		return Result.ok(bookService.getChapter(id, chapterIndex));
	}

	@PostMapping("/{id}/chapters")
	public Result<ChapterVO> createChapter(@PathVariable long id,
			@Valid @RequestBody ChapterWriteDTO request) {
		return Result.ok(bookService.createChapter(id, request));
	}

	@PutMapping("/{id}/chapters/{chapterIndex}")
	public Result<ChapterVO> updateChapter(@PathVariable long id, @PathVariable int chapterIndex,
			@Valid @RequestBody ChapterWriteDTO request) {
		return Result.ok(bookService.updateChapter(id, chapterIndex, request));
	}

	@DeleteMapping("/{id}/chapters/{chapterIndex}")
	public Result<Void> deleteChapter(@PathVariable long id, @PathVariable int chapterIndex) {
		bookService.deleteChapter(id, chapterIndex);
		return Result.ok();
	}
}
