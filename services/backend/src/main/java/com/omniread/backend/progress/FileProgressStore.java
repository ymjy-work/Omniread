package com.omniread.backend.progress;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 单机阅读进度的本地文件存储：M0 单用户一条记录，不落 PostgreSQL（M0-01 §1）。
 *
 * 写入先落同目录临时文件再 rename，避免进程中途退出留下半截 JSON；
 * 读写在单个 JVM 内用 synchronized 串行化，M0 只有一个写者，不做跨进程文件锁。
 */
@Component
public class FileProgressStore {

    /** 未写过进度时读到第 1 章：契约 max_seq 下界是 1，0 不在合法范围。 */
    static final int FIRST_CHAPTER = 1;

    private static final String TEMP_PREFIX = "progress-";

    private static final String TEMP_SUFFIX = ".tmp";

    private final Path file;

    private final ObjectMapper mapper = JsonMapper.builder().build();

    public FileProgressStore(ProgressProperties properties) {
        this.file = properties.file();
    }

    /**
     * 读某本书的进度。文件不存在、记录属于另一本书时都返回初始进度（第 1 章）；
     * 文件存在但读不出来（被外部改坏）说明本地状态已不可信，报 RAG_UNAVAILABLE 而不是静默重置。
     */
    public synchronized Progress read(int bookId) {
        if (!Files.isRegularFile(file)) {
            return initial(bookId);
        }
        Progress stored;
        try {
            stored = mapper.readValue(file.toFile(), Progress.class);
        } catch (RuntimeException e) {
            throw new RagException(ErrorCode.RAG_UNAVAILABLE, "读取阅读进度失败：" + e.getMessage(), e);
        }
        if (stored == null || stored.bookId() != bookId) {
            return initial(bookId);
        }
        return new Progress(bookId, stored.maxSeq());
    }

    /** 覆盖写某本书的进度。max_seq 的边界由 Controller 用 chapter_count 校验后再进来。 */
    public synchronized Progress write(int bookId, int maxSeq) {
        Progress progress = new Progress(bookId, maxSeq);
        persist(progress);
        return progress;
    }

    private void persist(Progress progress) {
        Path directory = file.toAbsolutePath().getParent();
        Path temp = null;
        try {
            Files.createDirectories(directory);
            temp = Files.createTempFile(directory, TEMP_PREFIX, TEMP_SUFFIX);
            mapper.writeValue(temp.toFile(), progress);
            move(temp, file);
        } catch (IOException | RuntimeException e) {
            throw new RagException(ErrorCode.RAG_UNAVAILABLE, "写入阅读进度失败：" + e.getMessage(), e);
        } finally {
            deleteQuietly(temp);
        }
    }

    /**
     * 同目录 rename。ATOMIC_MOVE 在目标已存在时的语义依赖文件系统，
     * 不支持就退回普通 replace —— 先写临时文件这一点不变，最坏只是少了原子性。
     */
    private static void move(Path source, Path target) throws IOException {
        try {
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static void deleteQuietly(Path path) {
        if (path == null) {
            return;
        }
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // 临时文件残留不影响正确性，下一次写会另建一个。
        }
    }

    private static Progress initial(int bookId) {
        return new Progress(bookId, FIRST_CHAPTER);
    }
}
