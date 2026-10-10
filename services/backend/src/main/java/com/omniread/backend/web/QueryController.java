package com.omniread.backend.web;

import com.omniread.backend.gateway.RagStream;
import com.omniread.backend.orchestration.AnswerStreamRecorder;
import com.omniread.backend.orchestration.QueryOrchestrator;
import com.omniread.backend.orchestration.SessionQueryRequest;
import com.omniread.backend.orchestration.SessionQueryResponse;
import com.omniread.backend.user.AuthenticatedUser;
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
    public SessionQueryResponse query(@RequestBody @Valid SessionQueryRequest request,
            @RequestAttribute(RequestIds.ATTRIBUTE) String requestId,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        return orchestrator.query(request, user.id(), requestId);
    }

    /**
     * SSE：逐帧转发，同时把这一轮折叠成一条落库的回答。
     *
     * <p>M0 是纯字节透传（「Java 不解析事件」）；多轮之后必须解析——回答正文只出现在
     * `answer_delta` 里，不攒起来落库的就是一条空消息，而它看起来只是「回答很短」。
     * 除终止帧外仍旧逐帧即刷，只有 `query_done` 那一刻等一次落库（它要带 `message_id`）。
     *
     * <p>直接写响应流而不是返回 StreamingResponseBody：后者把 flush 攒到任务结束，
     * 首字节要等整条流跑完才到客户端。代价是整段流占用一个请求线程，M0 单机可接受。
     */
    @PostMapping(path = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public void stream(@RequestBody @Valid SessionQueryRequest request,
            @RequestAttribute(RequestIds.ATTRIBUTE) String requestId,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user,
            HttpServletResponse response) throws IOException {
        QueryOrchestrator.PreparedQuery prepared = orchestrator.prepare(request, user.id());
        orchestrator.recordQuestion(prepared.session(), request.getQuestion());

        RagStream upstream = orchestrator.openStream(prepared, request, requestId);
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType(MediaType.TEXT_EVENT_STREAM_VALUE);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache");
        response.setHeader("X-Accel-Buffering", "no");
        SseRelay.relay(
                upstream,
                requestId,
                response.getOutputStream(),
                new AnswerStreamRecorder(orchestrator, prepared.session()));
    }
}
