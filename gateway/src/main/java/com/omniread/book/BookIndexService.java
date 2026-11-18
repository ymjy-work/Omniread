package com.omniread.book;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.omniread.book.model.ChapterEntity;
import com.omniread.chat.RagClient;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** 章节变更后在后台单线程触发全书重建索引；同一本书的连续变更合并为一次调用。 */
@Service
public class BookIndexService {

	private static final Logger log = LoggerFactory.getLogger(BookIndexService.class);

	private final ChapterMapper chapterMapper;
	private final RagClient ragClient;
	private final ConcurrentHashMap<Long, Boolean> pending = new ConcurrentHashMap<>();
	private final ExecutorService executor = Executors.newSingleThreadExecutor(runnable -> {
		Thread thread = new Thread(runnable, "rag-index");
		thread.setDaemon(true);
		return thread;
	});

	public BookIndexService(ChapterMapper chapterMapper, RagClient ragClient) {
		this.chapterMapper = chapterMapper;
		this.ragClient = ragClient;
	}

	/** 事务内调用时延迟到提交后再触发，避免后台线程读到未提交数据。 */
	public void triggerReindex(long bookId) {
		if (TransactionSynchronizationManager.isSynchronizationActive()) {
			TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
				@Override
				public void afterCommit() {
					submitReindex(bookId);
				}
			});
			return;
		}
		submitReindex(bookId);
	}

	private void submitReindex(long bookId) {
		if (pending.putIfAbsent(bookId, Boolean.TRUE) != null) {
			return;
		}
		executor.submit(() -> {
			pending.remove(bookId);
			try {
				List<ChapterEntity> chapters = chapterMapper.listWithTextByBook(bookId);
				if (chapters.isEmpty()) {
					return;
				}
				int indexed = ragClient.index(bookId, chapters);
				log.info("book {} 索引完成，indexed_chunks={}", bookId, indexed);
			}
			catch (Exception e) {
				log.warn("book {} 索引失败，下次章节变更时重试: {}", bookId, e.getMessage());
			}
		});
	}

	@PreDestroy
	public void shutdown() {
		executor.shutdown();
	}
}
