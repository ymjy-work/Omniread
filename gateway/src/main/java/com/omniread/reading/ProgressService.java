package com.omniread.reading;

import com.omniread.book.BookMapper;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Timestamps;
import com.omniread.reading.model.ProgressDTO;
import com.omniread.reading.model.ReadingProgressEntity;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProgressService {

	private final ProgressMapper progressMapper;
	private final BookMapper bookMapper;

	public ProgressService(ProgressMapper progressMapper, BookMapper bookMapper) {
		this.progressMapper = progressMapper;
		this.bookMapper = bookMapper;
	}

	public ReadingProgressEntity get(long userId, long bookId) {
		requireBook(bookId);
		ReadingProgressEntity progress = progressMapper.findByUserAndBook(userId, bookId);
		if (progress != null) {
			return progress;
		}
		// 无记录时返回起始位置，不落库
		ReadingProgressEntity initial = new ReadingProgressEntity();
		initial.setUserId(userId);
		initial.setBookId(bookId);
		initial.setChapterIndex(1);
		initial.setScrollRatio(0.0);
		return initial;
	}

	@Transactional
	public ReadingProgressEntity put(long userId, long bookId, ProgressDTO request) {
		requireBook(bookId);
		ReadingProgressEntity progress = new ReadingProgressEntity();
		progress.setUserId(userId);
		progress.setBookId(bookId);
		progress.setChapterIndex(request.chapterIndex());
		progress.setScrollRatio(request.scrollRatio());
		progress.setUpdatedAt(Timestamps.now());
		progressMapper.upsert(progress);
		return progressMapper.findByUserAndBook(userId, bookId);
	}

	private void requireBook(long bookId) {
		if (bookMapper.findById(bookId) == null) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "书籍不存在");
		}
	}
}
