package com.omniread.backend.reading;

import com.omniread.backend.config.ReadingProperties;
import com.omniread.backend.contract.model.ChapterDetail;
import com.omniread.backend.contract.model.ChapterDetailImagesInner;
import com.omniread.backend.contract.model.ChapterList;
import com.omniread.backend.contract.model.ChapterListChaptersInner;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import com.omniread.backend.gateway.RagGatewayClient;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * 阅读范围：**阅读页只开放配置的那一卷**（产品上的刻意取舍，
 * 不是权限 bug）。问答不受它限制——「读有边界、问无边界」。
 *
 * <p>过滤在 Java 侧做：Python 不感知账户与阅读范围，内部契约因此不必新增字段。
 *
 * <p>区间是**从章节表推导**的（按 volume_index 筛出来求最小/最大章号），不写死 1..11：
 * 语料重导入换了卷结构时，写死的那份会静默地放行或挡住错误的章。
 *
 * <p>两份缓存都不设失效：语料在一次部署里是静态的（重导入要重启服务），
 * 而它们每次都要问 Python 要整份章节表 / 逐章要插图清单。**缓存的是「配置 + 语料」的
 * 导出量，不是用户数据**，所以共享一份没有串号问题。
 */
@Component
public class ReadingRange {

    private final RagGatewayClient gateway;

    private final ReadingProperties properties;

    private final Map<Integer, ChapterRange> ranges = new ConcurrentHashMap<>();

    private final Map<Integer, Set<String>> imageKeys = new ConcurrentHashMap<>();

    public ReadingRange(RagGatewayClient gateway, ReadingProperties properties) {
        this.gateway = gateway;
        this.properties = properties;
    }

    /** 可读的章号区间（闭区间）。 */
    public record ChapterRange(int lo, int hi) {

        public boolean contains(int chapterIndex) {
            return chapterIndex >= lo && chapterIndex <= hi;
        }
    }

    public ChapterRange rangeOf(int bookId) {
        return ranges.computeIfAbsent(bookId, this::loadRange);
    }

    public boolean chapterReadable(int bookId, int chapterIndex) {
        return rangeOf(bookId).contains(chapterIndex);
    }

    /** 插图是否在可读范围内：**按「可读章节引用了它」判**，不按文件名或目录名猜。 */
    public boolean imageReadable(int bookId, String path) {
        return imageKeys(bookId).contains(imageKey(path));
    }

    private ChapterRange loadRange(int bookId) {
        ChapterList list = gateway.listChapters(bookId);
        int lo = Integer.MAX_VALUE;
        int hi = 0;
        if (list.getChapters() != null) {
            for (ChapterListChaptersInner chapter : list.getChapters()) {
                if (Integer.valueOf(properties.volumeIndex()).equals(chapter.getVolumeIndex())) {
                    lo = Math.min(lo, chapter.getChapterIndex());
                    hi = Math.max(hi, chapter.getChapterIndex());
                }
            }
        }
        if (hi < lo) {
            // 配置的卷在语料里不存在：这是**部署配错了**，不是用户请求的问题。
            // 宁可 503 让大家看见，也不要静默放行全本书。
            throw new RagException(
                    ErrorCode.RAG_UNAVAILABLE,
                    "book_id " + bookId + " 里没有第 " + properties.volumeIndex() + " 卷的章节，阅读范围配置有误");
        }
        return new ChapterRange(lo, hi);
    }

    private Set<String> imageKeys(int bookId) {
        return imageKeys.computeIfAbsent(bookId, id -> {
            Set<String> allowed = new HashSet<>();
            ChapterRange range = rangeOf(id);
            for (int chapterIndex = range.lo(); chapterIndex <= range.hi(); chapterIndex++) {
                ChapterDetail detail = gateway.getChapter(id, chapterIndex);
                if (detail.getImages() == null) {
                    continue;
                }
                for (ChapterDetailImagesInner image : detail.getImages()) {
                    allowed.add(imageKey(image.getUrl()));
                }
            }
            return Set.copyOf(allowed);
        });
    }

    /**
     * 把两种写法归一到同一个键：契约里图片的 `url`（`/api/v1/books/1/images/01_第1卷/007.jpg`）
     * 与客户端请求里的路径（`01_第1卷/007.jpg`，可能还带着 URL 编码）。
     *
     * <p>只解码含 `%` 的串：`URLDecoder` 会把 `+` 解成空格，而文件名里的 `+` 是合法字符，
     * 一律解码会把一份好端端的路径变成另一个键——症状是图片 403，且看不出为什么。
     */
    public static String imageKey(String pathOrUrl) {
        String value = pathOrUrl == null ? "" : pathOrUrl;
        int marker = value.indexOf("/images/");
        if (marker >= 0) {
            value = value.substring(marker + "/images/".length());
        }
        while (value.startsWith("/")) {
            value = value.substring(1);
        }
        if (value.indexOf('%') < 0) {
            return value;
        }
        try {
            return URLDecoder.decode(value, StandardCharsets.UTF_8);
        } catch (IllegalArgumentException malformed) {
            return value;
        }
    }
}
