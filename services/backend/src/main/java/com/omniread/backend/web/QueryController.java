package com.omniread.backend.web;

import com.omniread.backend.contract.model.QueryRequest;
import com.omniread.backend.contract.model.QueryResponse;
import com.omniread.backend.gateway.RagStream;
import com.omniread.backend.orchestration.QueryOrchestrator;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.io.IOException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 单轮问答。两个入口用路径区分（/query 与 /query/stream），不做 Accept 内容协商：
 * 适配器选择是显式的，省掉协商分支与 Accept 解析的边界情况（M0-01 §6.1）。
 *
 * 两者都只是协议入口，编排在 QueryOrchestrator。
 */
@RestController
@RequestMapping("/api/v1/query")
public class QueryController {

    private final QueryOrchestrator orchestrator;

    public QueryController(QueryOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @PostMapping
    public QueryResponse query(@RequestBody @Valid QueryRequest request,
            @RequestAttribute(RequestIds.ATTRIBUTE) String requestId) {
        return orchestrator.query(request, requestId);
    }

    /**
     * SSE 透传：Java 不解析事件、不重组帧，Python 适配器怎么写就怎么到浏览器。
     *
     * 直接写响应流而不是返回 StreamingResponseBody：后者把 flush 攒到任务结束，
     * 首字节要等整条流跑完才到客户端。代价是整段流占用一个请求线程，M0 单机可接受。
     */
    @PostMapping(path = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public void stream(@RequestBody @Valid QueryRequest request,
            @RequestAttribute(RequestIds.ATTRIBUTE) String requestId,
            HttpServletResponse response) throws IOException {
        RagStream upstream = orchestrator.stream(request, requestId);
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType(MediaType.TEXT_EVENT_STREAM_VALUE);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache");
        response.setHeader("X-Accel-Buffering", "no");
        Streams.forwardSse(upstream, requestId, response.getOutputStream());
    }
}
