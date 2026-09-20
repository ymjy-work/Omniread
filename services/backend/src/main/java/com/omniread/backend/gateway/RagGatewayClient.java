package com.omniread.backend.gateway;

import com.omniread.backend.config.RagProperties;
import com.omniread.backend.contract.model.BookList;
import com.omniread.backend.contract.model.ChapterDetail;
import com.omniread.backend.contract.model.ChapterList;
import com.omniread.backend.contract.model.ErrorBody;
import com.omniread.backend.contract.model.QueryRequest;
import com.omniread.backend.contract.model.QueryResponse;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.RagException;
import com.omniread.backend.web.RequestIds;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.retry.Retry;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.function.Supplier;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriUtils;

/**
 * 调用 Python RAG 服务内部契约（M0-01 §7）。
 *
 * 只做传输与错误翻译，不含编排：realm 校验、request_id 生成都在上层。
 * 出错一律抛 {@link RagException}，调用方不必认识 Spring 的 HTTP 异常类型。
 */
@Component
public class RagGatewayClient {

    private final RestClient restClient;
    private final RagProperties properties;
    private final Retry retry;
    private final CircuitBreaker circuitBreaker;

    public RagGatewayClient(RestClient ragRestClient, RagProperties properties, Retry ragRetry,
            CircuitBreaker ragCircuitBreaker) {
        this.restClient = ragRestClient;
        this.properties = properties;
        this.retry = ragRetry;
        this.circuitBreaker = ragCircuitBreaker;
    }

    public BookList listBooks() {
        return call(restClient.get().uri(uri("/internal/v1/books")), BookList.class);
    }

    public ChapterList listChapters(int bookId) {
        return call(restClient.get().uri(uri("/internal/v1/books/" + bookId + "/chapters")), ChapterList.class);
    }

    public ChapterDetail getChapter(int bookId, int chapterIndex) {
        return call(restClient.get().uri(uri("/internal/v1/books/" + bookId + "/chapters/" + chapterIndex)),
                ChapterDetail.class);
    }

    /** 插图字节流，原样转发不落内存。 */
    public RagStream openImage(int bookId, String relativePath) {
        return guard(() -> openStream(restClient.get().uri(imageUri(bookId, relativePath))));
    }

    /** 单轮问答：request_id 走请求头透传，请求体与外部契约 §8.1 完全一致。 */
    public QueryResponse query(QueryRequest body, String requestId) {
        return call(restClient.post()
                .uri(uri("/internal/v1/rag/query"))
                .header(RequestIds.HEADER, requestId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body), QueryResponse.class);
    }

    /** SSE 帧流：不解析、不重组，字节级透传（事件语义由 Python 侧适配器负责）。 */
    public RagStream openQueryStream(QueryRequest body, String requestId) {
        return guard(() -> openStream(restClient.post()
                .uri(uri("/internal/v1/rag/query-stream"))
                .header(RequestIds.HEADER, requestId)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .body(body)));
    }

    /** 一次下游调用：2xx 转成模型，非 2xx 翻成 RagException。 */
    private <T> T call(RestClient.RequestHeadersSpec<?> spec, Class<T> type) {
        return guard(() -> spec.exchange((request, response) -> {
            HttpStatusCode status = response.getStatusCode();
            if (status.isError()) {
                throw upstreamError(status, response);
            }
            T body = response.bodyTo(type);
            if (body == null) {
                throw new RagException(ErrorCode.RAG_UNAVAILABLE, "RAG 服务返回空响应体");
            }
            return body;
        }));
    }

    /**
     * 未读尽的响应体：交给上层边读边转发。
     *
     * exchange(..., false) 不能省：默认的 exchange 在回调返回时就关掉上游响应，
     * 拿到手的 InputStream 立刻变成 closed —— 流式转发正是要在回调之外继续读。
     * 关闭责任随之转到持有 RagStream 的一方。
     */
    private RagStream openStream(RestClient.RequestHeadersSpec<?> spec) {
        return spec.exchange((request, response) -> {
            HttpStatusCode status = response.getStatusCode();
            if (status.isError()) {
                RagException failure = upstreamError(status, response);
                // close=false 放弃了框架的收尾，异常路径要自己关，否则连接一直挂着。
                response.close();
                throw failure;
            }
            return new RagStream(
                    response.getHeaders().getContentType(),
                    response.getHeaders().getContentLength(),
                    response.getBody());
        }, false);
    }

    /**
     * 上游非 2xx → 本网关错误码。message 取自上游短描述，契约已禁止它夹带内部细节；
     * HTTP 状态原样带出去，目录端点文档化的 404 才不会被压成 5xx。
     */
    private RagException upstreamError(HttpStatusCode status, RestClient.RequestHeadersSpec.ConvertibleClientHttpResponse response) {
        String upstreamCode = null;
        String upstreamMessage = null;
        try {
            ErrorBody body = response.bodyTo(ErrorBody.class);
            if (body != null) {
                upstreamCode = body.getCode() == null ? null : body.getCode().name();
                upstreamMessage = body.getMessage();
            }
        } catch (RuntimeException ignored) {
            // 上游错误体不是契约形状（网关自身 500、连接半途断掉）时按状态码兜底。
        }
        ErrorCode code = ErrorCode.fromUpstream(status.value(), upstreamCode);
        String message = upstreamMessage != null ? upstreamMessage : "RAG 服务返回 " + status.value();
        return new RagException(code, message, status);
    }

    /**
     * 重试 + 熔断：装饰的是「一次完整的下游调用」。业务错误（RagException）直接上抛，
     * 只有传输失败会被重试，重试用尽或熔断打开后统一翻译成 RagException。
     */
    private <T> T guard(Supplier<T> call) {
        Supplier<T> decorated = Retry.decorateSupplier(retry, CircuitBreaker.decorateSupplier(circuitBreaker, call));
        try {
            return decorated.get();
        } catch (RagException e) {
            throw e;
        } catch (RuntimeException e) {
            ErrorCode code = ErrorCode.fromTransportFailure(e);
            String message = code == ErrorCode.RAG_TIMEOUT ? "RAG 服务调用超时" : "RAG 服务不可达";
            throw new RagException(code, message, e);
        }
    }

    private URI uri(String path) {
        return URI.create(properties.baseUrl() + path);
    }

    private URI imageUri(int bookId, String relativePath) {
        // 路径必须按段编码后拼进 URI：把整段当模板变量交给 UriBuilder 会把 '/' 变成 %2F，
        // Python 侧的 {path:path} 就匹配不上任何插图。
        String encodedPath = UriUtils.encodePath(relativePath, StandardCharsets.UTF_8);
        return URI.create(properties.baseUrl() + "/internal/v1/books/" + bookId + "/images/" + encodedPath);
    }
}
