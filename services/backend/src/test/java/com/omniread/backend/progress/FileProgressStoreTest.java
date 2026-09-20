package com.omniread.backend.progress;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 进度落在本地文件，读写往返与「没写过时读到什么」是这条链路的全部行为面。
 * 越界拒绝发生在 Controller（要 chapter_count），见 CatalogControllerTest。
 */
class FileProgressStoreTest {

    private static FileProgressStore store(Path file) {
        return new FileProgressStore(new ProgressProperties(file));
    }

    @Test
    @DisplayName("写入后能原样读回，父目录不存在会自动创建")
    void roundTripCreatesDirectory(@TempDir Path dir) {
        Path file = dir.resolve("nested").resolve("progress.json");
        FileProgressStore store = store(file);

        Progress written = store.write(1, 42);

        assertThat(written).isEqualTo(new Progress(1, 42));
        assertThat(store.read(1)).isEqualTo(new Progress(1, 42));
        assertThat(Files.isRegularFile(file)).isTrue();
    }

    @Test
    @DisplayName("文件不存在时读到第 1 章，且读不创建文件")
    void missingFileReadsFirstChapter(@TempDir Path dir) {
        Path file = dir.resolve("progress.json");
        FileProgressStore store = store(file);

        assertThat(store.read(1)).isEqualTo(new Progress(1, 1));
        assertThat(Files.exists(file)).isFalse();
    }

    @Test
    @DisplayName("覆盖写替换旧值，文件内容是完整 JSON")
    void overwrite(@TempDir Path dir) throws Exception {
        Path file = dir.resolve("progress.json");
        FileProgressStore store = store(file);

        store.write(1, 5);
        store.write(1, 9);

        assertThat(store.read(1)).isEqualTo(new Progress(1, 9));
        assertThat(Files.readString(file)).contains("\"max_seq\":9");
    }

    @Test
    @DisplayName("记录属于另一本书时按未读处理")
    void otherBookIsUnread(@TempDir Path dir) {
        FileProgressStore store = store(dir.resolve("progress.json"));
        store.write(1, 42);

        assertThat(store.read(2)).isEqualTo(new Progress(2, 1));
    }
}
