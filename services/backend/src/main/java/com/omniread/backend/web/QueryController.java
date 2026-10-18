package com.omniread.backend.web;

import com.omniread.backend.gateway.RagStream;
import com.omniread.backend.orchestration.AnswerStreamRecorder;
import com.omniread.backend.orchestration.QueryOrchestrator;
import com.omniread.backend.orchestration.SessionQueryRequest;
import com.omniread.backend.orchestration.SessionQueryResponse;
import com.omniread.backend.quota.QuotaService;
import com.omniread.backend.user.AuthenticatedUser;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.io.IOException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * 单轮问答。两个入口用路径区分（`/query` 与 `/query-stream`），不做 Accept 内容协商：
 * 适配器选择是显式的，省掉协商分支与 Accept 解析的边界情况。
 *
 * <p>两条路径各自写全，**不用类级 `@RequestMapping("/api/v1/query")` 加方法级后缀**：
 * 后者会强制 `/query-stream` 长成 `/query/stream`（子资源形状），而它与 `/query` 是
 * **并列的两个操作**、不是「query 的 stream 子资源」。kebab 也与内部契约的
 * `rag/query-stream`、`rag/retrieval-only` 同一个拼法。
 *
 * <p>两者都只是协议入口，编排在 QueryOrchestrator。
 */
@RestController
public class QueryController {

    private final QueryOrchestrator orchestrator;

    private final QuotaService quota;

    public QueryController(QueryOrchestrator orchestrator, QuotaService quota) {
        this.orchestrator = orchestrator;
        this.quota = quota;
    }

    @PostMapping("/api/v1/query")
    public SessionQueryResponse query(@RequestBody @Valid SessionQueryRequest request,
            @RequestAttribute(RequestIds.ATTRIBUTE) String requestId,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user) {
        return orchestrator.query(request, user.userId(), requestId);
    }

    /**
     * SSE：逐帧转发，同时把这一轮折叠成一条落库的回答。
     *
     * <p>这里必须解析事件，不能只做纯字节透传：回答正文只出现在
     * `answer_delta` 里，不攒起来落库的就是一条空消息，而它看起来只是「回答很短」。
     * 除终止帧外仍旧逐帧即刷，只有 `query_done` 那一刻等一次落库（它要带 `message_id`）。
     *
     * <p>直接写响应流而不是返回 StreamingResponseBody：后者把 flush 攒到任务结束，
     * 首字节要等整条流跑完才到客户端。代价是整段流占用一个请求线程，单机可接受。
     */
    @PostMapping(path = "/api/v1/query-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public void stream(@RequestBody @Valid SessionQueryRequest request,
            @RequestAttribute(RequestIds.ATTRIBUTE) String requestId,
            @RequestAttribute(AuthInterceptor.USER_ATTRIBUTE) AuthenticatedUser user,
            HttpServletRequest servletRequest,
            HttpServletResponse response) throws IOException {
        QueryOrchestrator.PreparedQuery prepared = orchestrator.prepare(request, user.userId());
        orchestrator.recordQuestion(prepared.session(), request.getQuestion());

        RagStream upstream = orchestrator.openStream(prepared, request, requestId);
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType(MediaType.TEXT_EVENT_STREAM_VALUE);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache");
        response.setHeader("X-Accel-Buffering", "no");
        AnswerStreamRecorder recorder = new AnswerStreamRecorder(orchestrator, prepared.session());
        SseRelay.relay(upstream, requestId, response.getOutputStream(), recorder);

        // 流里出过错（provider 5xx / 上游中断）：这一轮没有结果，把日额度还回去。
        // **不能靠状态码**——开流那一刻它就已经是 200 了，这是网关自己发的字节流，
        // 后到的失败只能以 `error` / `query_error` 帧表达。
        if (recorder.failed()) {
            quota.refund(QuotaInterceptor.leaseOf(servletRequest));
        }
    }
}
