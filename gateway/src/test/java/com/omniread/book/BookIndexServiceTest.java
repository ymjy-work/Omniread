package com.omniread.book;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import com.omniread.book.model.ChapterEntity;
import com.omniread.chat.RagClient;
import com.omniread.config.AiProperties;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BookIndexServiceTest {

	private final AtomicInteger indexCalls = new AtomicInteger();
	private final CountDownLatch indexed = new CountDownLatch(1);

	private final ChapterMapper chapterMapper = new ChapterMapper() {
		@Override
		public List<ChapterEntity> listByBook(long bookId) {
			throw new UnsupportedOperationException();
		}

		@Override
		public List<ChapterEntity> listWithTextByBook(long bookId) {
			ChapterEntity chapter = new ChapterEntity();
			chapter.setBookId(bookId);
			chapter.setChapterIndex(1);
			chapter.setTitle("第1章");
			chapter.setText("正文");
			return List.of(chapter);
		}

		@Override
		public ChapterEntity findByIndex(long bookId, int chapterIndex) {
			throw new UnsupportedOperationException();
		}

		@Override
		public long countByBook(long bookId) {
			throw new UnsupportedOperationException();
		}

		@Override
		public int insert(ChapterEntity chapter) {
			throw new UnsupportedOperationException();
		}

		@Override
		public int upsert(ChapterEntity chapter) {
			throw new UnsupportedOperationException();
		}

		@Override
		public int updateContent(long bookId, int chapterIndex, String title, String text) {
			throw new UnsupportedOperationException();
		}

		@Override
		public int deleteByIndex(long bookId, int chapterIndex) {
			throw new UnsupportedOperationException();
		}
	};

	private final RagClient ragClient = new RagClient(new AiProperties()) {
		@Override
		public int index(long bookId, List<ChapterEntity> chapters) {
			indexCalls.incrementAndGet();
			indexed.countDown();
			return chapters.size();
		}
	};

	@Test
	void triggersOnlyAfterCommitWhenTransactionActive() throws Exception {
		BookIndexService service = new BookIndexService(chapterMapper, ragClient);
		TransactionSynchronizationManager.initSynchronization();
		try {
			service.triggerReindex(1);
			// 提交前后台线程不应发起索引；若未挂 afterCommit，此处早已调用
			Thread.sleep(200);
			assertEquals(0, indexCalls.get());

			List<TransactionSynchronization> synchronizations =
					TransactionSynchronizationManager.getSynchronizations();
			assertEquals(1, synchronizations.size());
			synchronizations.forEach(TransactionSynchronization::afterCommit);

			assertTrue(indexed.await(5, TimeUnit.SECONDS));
			assertEquals(1, indexCalls.get());
		}
		finally {
			TransactionSynchronizationManager.clearSynchronization();
			service.shutdown();
		}
	}

	@Test
	void triggersImmediatelyWithoutTransaction() throws Exception {
		BookIndexService service = new BookIndexService(chapterMapper, ragClient);
		try {
			service.triggerReindex(1);
			assertTrue(indexed.await(5, TimeUnit.SECONDS));
			assertEquals(1, indexCalls.get());
		}
		finally {
			service.shutdown();
		}
	}
}
