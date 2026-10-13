package com.omniread.backend.orchestration;

import com.omniread.backend.contract.model.ContextChapter;
import com.omniread.backend.contract.model.QueryResponse;
import com.omniread.backend.contract.model.Usage;
import com.omniread.backend.session.ChatMessage;
import com.omniread.backend.session.ChatSession;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.BiFunction;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 把一条 SSE 流折叠成「一条要落库的回答」，同时把终止帧改写成带上网关分配的
 * `session_id` / `message_id`。
 *
 * <p>为什么非解析不可：回答正文只出现在若干 `answer_delta` 里，而终止帧的负载
 * （契约写死的 `status` / `context_chapters` / `usage`）**不含正文**——不把 delta 攒起来，
 * 落库的那条消息就是空的，而它看起来只是「回答很短」。
 *
 * <p>除终止帧外一律返回 `null`（原样转发）：折叠归折叠，转发仍是逐帧即刷。
 */
public class AnswerStreamRecorder implements BiFunction<String, String, String> {

    private static final String EVENT_ANSWER_DELTA = "answer_delta";

    private static final String EVENT_QUERY_DONE = "query_done";

    private static final String EVENT_REWRITE_COMPLETED = "rewrite_completed";

    /** 流里的错误：`query_error` 是 Python 发的业务错误帧，`error` 是网关自己补的传输失败帧。 */
    private static final String EVENT_QUERY_ERROR = "query_error";

    private static final String EVENT_ERROR = "error";

    private static final ObjectMapper MAPPER = JsonMapper.builder().build();

    private final QueryOrchestrator orchestrator;
    private final ChatSession session;

    private final StringBuilder answer = new StringBuilder();

    /**
     * 改写后的问题。`null` 表示**改写没跑**——契约把这条写死为
     * 「`null` ⟺ 改写没跑」，而 `skipped` 按规则不发帧，所以「没收到帧」就是 null。
     */
    private String rewrittenQuery;

    /** 流被标记为已落库：终止帧可能重复出现（上游重发），只认第一次。 */
    private boolean recorded;

    /** 流里出现过错误帧。额度退还用它——**状态码在这里帮不上忙**（开流时就已经是 200）。 */
    private boolean failed;

    public AnswerStreamRecorder(QueryOrchestrator orchestrator, ChatSession session) {
        this.orchestrator = orchestrator;
        this.session = session;
    }

    /** 这一轮有没有以错误收场（provider 5xx、上游中断）。 */
    public boolean failed() {
        return failed;
    }

    @Override
    public String apply(String event, String data) {
        if (EVENT_ERROR.equals(event) || EVENT_QUERY_ERROR.equals(event)) {
            failed = true;
            return null;
        }
        if (EVENT_ANSWER_DELTA.equals(event)) {
            Object text = parse(data).get("text");
            if (text instanceof String piece) {
                answer.append(piece);
            }
            return null;
        }
        if (EVENT_REWRITE_COMPLETED.equals(event)) {
            Object effective = parse(data).get("effective");
            rewrittenQuery = effective instanceof String value ? value : null;
            return null;
        }
        if (EVENT_QUERY_DONE.equals(event)) {
            return finish(data);
        }
        return null;
    }

    /** 终止帧：先落库拿到 `message_id`，再把它与 `session_id` 补进负载。 */
    private String finish(String data) {
        if (recorded) {
            return data;
        }
        recorded = true;
        Map<String, Object> payload = parse(data);
        ChatMessage replied = orchestrator.recordAnswer(session, toResponse(payload));
        return withIds(data, replied.getId());
    }

    private QueryResponse toResponse(Map<String, Object> payload) {
        QueryResponse response = new QueryResponse()
                .answer(answer.toString())
                .requestId("")
                .contextChapters(toContextChapters(payload))
                .rewrittenQuery(rewrittenQuery);
        Object status = payload.get("status");
        if (status instanceof String value) {
            response.setStatus(QueryResponse.StatusEnum.fromValue(value));
        }
        response.setUsage(toUsage(payload));
        return response;
    }

    @SuppressWarnings("unchecked")
    private static List<ContextChapter> toContextChapters(Map<String, Object> payload) {
        List<ContextChapter> chapters = new ArrayList<>();
        if (payload.get("context_chapters") instanceof List<?> items) {
            for (Object item : items) {
                if (item instanceof Map<?, ?> chapter) {
                    Object index = chapter.get("chapter_index");
                    Object title = chapter.get("chapter_title");
                    if (index instanceof Number number) {
                        chapters.add(new ContextChapter(number.intValue(), String.valueOf(title)));
                    }
                }
            }
        }
        return chapters;
    }

    private static Usage toUsage(Map<String, Object> payload) {
        if (!(payload.get("usage") instanceof Map<?, ?> usage)) {
            return null;
        }
        Usage model = new Usage();
        Object provider = usage.get("answer_provider");
        Object name = usage.get("answer_model");
        Object latency = usage.get("latency_ms");
        model.setAnswerProvider(provider == null ? null : String.valueOf(provider));
        model.setAnswerModel(name == null ? null : String.valueOf(name));
        model.setLatencyMs(latency instanceof Number number ? number.intValue() : null);
        return model;
    }

    /**
     * 把两个 id 并进原来那行 JSON。
     *
     * <p>**不去反序列化再序列化**：那样会把上游的字段顺序与数字格式一起改掉，
     * 前端与测试看到的字节就与 Python 写出的不再一致——而「帧长什么样」是 Python 适配器的
     * 职责，网关只该往上加东西。所以先取原负载的最后一个 `}`，插在两个新字段之前。
     */
    private String withIds(String data, Long messageId) {
        String trimmed = data.trim();
        if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
            return data;
        }
        String head = trimmed.substring(0, trimmed.length() - 1);
        String separator = head.length() > 1 ? "," : "";
        return head + separator + "\"session_id\":\"" + session.getId() + "\",\"message_id\":" + messageId
                + "}";
    }

    private static Map<String, Object> parse(String data) {
        try {
            Map<String, Object> parsed = MAPPER.readValue(data, Map.class);
            return parsed == null ? Map.of() : parsed;
        } catch (JacksonException e) {
            return Map.of();
        }
    }
}
