package com.omniread.backend.web;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.gateway.RagStream;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.function.BiFunction;

/**
 * SSE 逐帧搬运。
 *
 * <p>M0 是纯字节透传（Java 不解析事件）。多轮之后必须解析：**回答要落库**，而回答正文
 * 分散在若干 `answer_delta` 里；而终止帧还要带上刚落库的 `message_id`（前端靠它定位
 * 「从哪一条重新生成」）。所以这里逐帧切、逐帧转，仍然是**读到就刷**——只有
 * `query_done` 那一帧会停一下，因为它的负载要等落库。
 *
 * <p>帧格式与 Python 侧 `api/adapters.py::encode_frame` 逐字对应：
 * `event: <名>\ndata: <单行 JSON>\n\n`；成功终止是没有 event 行的 `data: [DONE]`。
 * **按空行切帧、按行重放**，所以除了被改写的那一帧，出去的字节与进来的逐字节相同。
 */
final class SseRelay {

    private static final String EVENT_PREFIX = "event: ";

    private static final String DATA_PREFIX = "data: ";

    static void relay(
            RagStream stream,
            String requestId,
            OutputStream out,
            BiFunction<String, String, String> sink) {
        try (BufferedReader reader =
                new BufferedReader(new InputStreamReader(stream.body(), StandardCharsets.UTF_8))) {
            StringBuilder frame = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    emit(out, frame.toString(), sink);
                    frame.setLength(0);
                } else {
                    frame.append(line).append('\n');
                }
            }
            // 上游没以空行收尾时，最后一帧仍然要发出去——静默吞掉它等于吞掉一次终止。
            if (!frame.isEmpty()) {
                emit(out, frame.toString(), sink);
            }
        } catch (Exception failure) {
            writeErrorFrame(out, requestId, ErrorCode.fromTransportFailure(failure));
        }
    }

    /**
     * 切出 `event` / `data`，把 data 交给 sink（可能被换掉），再按原样拼回一帧。
     *
     * <p>钩子是 `BiFunction<event, data, 新 data>`（新 data 为 null 表示原样转发）——
     * 用 JDK 自带的函数式类型而不是自定义接口，这样折叠逻辑可以住在 `orchestration` 里，
     * 不必为了一个签名把接口提到跨包的可见性。
     */
    private static void emit(OutputStream out, String frame, BiFunction<String, String, String> sink) {
        String event = null;
        String data = null;
        for (String line : frame.split("\n", -1)) {
            if (line.startsWith(EVENT_PREFIX)) {
                event = line.substring(EVENT_PREFIX.length());
            } else if (line.startsWith(DATA_PREFIX)) {
                data = line.substring(DATA_PREFIX.length());
            }
        }
        // 没有 data 行的帧（理论上不该有）原样发走，不猜它是什么。
        String rewritten = data == null ? null : sink.apply(event, data);
        String payload = rewritten == null ? frame : rebuild(event, rewritten);
        write(out, payload.endsWith("\n\n") ? payload : payload + "\n");
    }

    private static String rebuild(String event, String data) {
        StringBuilder rebuilt = new StringBuilder();
        if (event != null) {
            rebuilt.append(EVENT_PREFIX).append(event).append('\n');
        }
        return rebuilt.append(DATA_PREFIX).append(data).append("\n\n").toString();
    }

    private static void write(OutputStream out, String payload) {
        try {
            out.write(payload.getBytes(StandardCharsets.UTF_8));
            out.flush();
        } catch (IOException ignored) {
            // 客户端已断开；没有接收方，后续帧自然也会失败。
        }
    }

    private static void writeErrorFrame(OutputStream out, String requestId, ErrorCode code) {
        String message = code == ErrorCode.RAG_TIMEOUT ? "RAG 服务调用超时" : "RAG 服务不可达";
        write(out, rebuild(
                "error",
                "{\"request_id\":\"" + requestId + "\",\"code\":\"" + code.name()
                        + "\",\"message\":\"" + message + "\"}"));
    }

    private SseRelay() {
    }
}
