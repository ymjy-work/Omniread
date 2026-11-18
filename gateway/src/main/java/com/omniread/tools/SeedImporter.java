package com.omniread.tools;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import com.omniread.book.BookIndexService;
import com.omniread.book.BookMapper;
import com.omniread.book.ChapterMapper;
import com.omniread.book.model.BookEntity;
import com.omniread.book.model.ChapterEntity;
import com.omniread.common.Timestamps;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/** 语料导入：--omniread.seed.enabled=true 时执行，幂等导入 book=1 与全部章节后触发一次索引。 */
@Component
@Order(2)
@ConditionalOnProperty(name = "omniread.seed.enabled", havingValue = "true")
public class SeedImporter implements ApplicationRunner {

	private static final Logger log = LoggerFactory.getLogger(SeedImporter.class);
	private static final long BOOK_ID = 1;
	private static final String BOOK_TITLE = "不时轻声地以俄语遮羞的邻座艾莉同学";
	private static final String BOOK_AUTHOR = "灿灿SUN";
	private static final String DEFAULT_JSONL = "../《不时轻声地以俄语遮羞的邻座艾莉同学》/index.jsonl";

	private final BookMapper bookMapper;
	private final ChapterMapper chapterMapper;
	private final BookIndexService bookIndexService;
	private final String configuredPath;
	private final ObjectMapper mapper = JsonMapper.builder().build();

	public SeedImporter(BookMapper bookMapper, ChapterMapper chapterMapper,
			BookIndexService bookIndexService,
			@Value("${omniread.seed.jsonl:}") String configuredPath) {
		this.bookMapper = bookMapper;
		this.chapterMapper = chapterMapper;
		this.bookIndexService = bookIndexService;
		this.configuredPath = configuredPath;
	}

	@Override
	public void run(ApplicationArguments args) throws Exception {
		String jsonl = configuredPath != null && !configuredPath.isBlank()
				? configuredPath
				: System.getenv().getOrDefault("OMNIREAD_SEED_JSONL", DEFAULT_JSONL);
		Path path = Path.of(jsonl);
		if (!Files.isRegularFile(path)) {
			throw new IllegalStateException("语料索引文件不存在: " + path.toAbsolutePath()
					+ "（可用环境变量 OMNIREAD_SEED_JSONL 指定）");
		}
		List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8).stream()
				.filter(line -> !line.isBlank()).toList();
		if (bookMapper.findById(BOOK_ID) != null && chapterMapper.countByBook(BOOK_ID) == lines.size()) {
			log.info("book {} 已有 {} 章，跳过导入", BOOK_ID, lines.size());
			return;
		}
		if (bookMapper.findById(BOOK_ID) == null) {
			BookEntity book = new BookEntity();
			book.setId(BOOK_ID);
			book.setTitle(BOOK_TITLE);
			book.setAuthor(BOOK_AUTHOR);
			book.setCreatedAt(Timestamps.now());
			bookMapper.insert(book);
		}
		String now = Timestamps.now();
		for (int i = 0; i < lines.size(); i++) {
			JsonNode node = mapper.readTree(lines.get(i));
			ChapterEntity chapter = new ChapterEntity();
			chapter.setBookId(BOOK_ID);
			chapter.setChapterIndex(i + 1);
			chapter.setTitle(node.path("title").asString());
			chapter.setText(node.path("text").asString());
			chapter.setCreatedAt(now);
			chapterMapper.upsert(chapter);
		}
		log.info("book {} 导入完成，共 {} 章", BOOK_ID, lines.size());
		bookIndexService.triggerReindex(BOOK_ID);
	}
}
