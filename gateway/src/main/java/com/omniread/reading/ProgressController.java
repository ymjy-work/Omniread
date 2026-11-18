package com.omniread.reading;

import com.omniread.auth.AuthInterceptor;
import com.omniread.common.Result;
import com.omniread.reading.model.ProgressDTO;
import com.omniread.reading.model.ReadingProgressEntity;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books/{bookId}/progress")
public class ProgressController {

	private final ProgressService progressService;

	public ProgressController(ProgressService progressService) {
		this.progressService = progressService;
	}

	@GetMapping
	public Result<ReadingProgressEntity> get(@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId,
			@PathVariable long bookId) {
		return Result.ok(progressService.get(userId, bookId));
	}

	@PutMapping
	public Result<ReadingProgressEntity> put(@RequestAttribute(AuthInterceptor.USER_ID_ATTR) long userId,
			@PathVariable long bookId, @Valid @RequestBody ProgressDTO request) {
		return Result.ok(progressService.put(userId, bookId, request));
	}
}
