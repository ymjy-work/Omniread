package com.omniread.backend.web;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.gateway.RagStream;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BiFunction;

/**
 * SSE 逐帧搬运。
 *
 * <p>多轮之后必须解析事件，不能只做纯字节透传：**回答要落库**，而回答正文
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

    private static final String EVENT_ERROR = "error";

    /**
     * 逐帧搬运。
     *
     * <p>`onClientGone` 在**首次写失败**时触发一次，之后仍把上游读完。为什么不能半路退出：
     * 这一轮的回答要靠终止帧落库，提前退出会留下「提问已落库、回答永远不来」的悬空轮。
     * 而写失败本身是同步 servlet 里唯一能感知客户端断开的方式——所以检测是尽力而为，
     * TCP 缓冲可能让断开后的前几帧「写成功」，那种情况下要等下一帧或上游空闲超时才察觉。
     */
    static void relay(
            RagStream stream,
            String requestId,
            OutputStream out,
            BiFunction<String, String, String> sink,
            Runnable onClientGone) {
        AtomicBoolean clientGone = new AtomicBoolean();
        try (BufferedReader reader =
                new BufferedReader(new InputStreamReader(stream.body(), StandardCharsets.UTF_8))) {
            StringBuilder frame = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    emit(out, frame.toString(), sink, clientGone, onClientGone);
                    frame.setLength(0);
                } else {
                    frame.append(line).append('\n');
                }
            }
            // 上游没以空行收尾时，最后一帧仍然要发出去——静默吞掉它等于吞掉一次终止。
            if (!frame.isEmpty()) {
                emit(out, frame.toString(), sink, clientGone, onClientGone);
            }
        } catch (Exception failure) {
            writeErrorFrame(out, requestId, ErrorCode.fromTransportFailure(failure), sink);
        }
    }

    /**
     * 切出 `event` / `data`，把 data 交给 sink（可能被换掉），再按原样拼回一帧。
     *
     * <p>钩子是 `BiFunction<event, data, 新 data>`（新 data 为 null 表示原样转发）——
     * 用 JDK 自带的函数式类型而不是自定义接口，这样折叠逻辑可以住在 `orchestration` 里，
     * 不必为了一个签名把接口提到跨包的可见性。
     */
    private static void emit(OutputStream out, String frame,
            BiFunction<String, String, String> sink,
            AtomicBoolean clientGone, Runnable onClientGone) {
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
        if (!write(out, payload.endsWith("\n\n") ? payload : payload + "\n")
                && clientGone.compareAndSet(false, true)) {
            notifyClientGone(onClientGone);
        }
    }

    /**
     * 客户端走了的通知。**回调失败不能中断搬运**：上游还得读完、这一轮的回答还要落库，
     * 半路退出等于把「已经落库的提问」配一条永远不来的回答。回调本身只做「早还并发位」，
     * 它失败不该影响数据完整性。
     */
    private static void notifyClientGone(Runnable onClientGone) {
        try {
            onClientGone.run();
        } catch (RuntimeException ignored) {
            // 见方法注释：这里吞掉的代价只是并发位晚一点归还。
        }
    }

    private static String rebuild(String event, String data) {
        StringBuilder rebuilt = new StringBuilder();
        if (event != null) {
            rebuilt.append(EVENT_PREFIX).append(event).append('\n');
        }
        return rebuilt.append(DATA_PREFIX).append(data).append("\n\n").toString();
    }

    /** 写一帧。客户端已断开时返回 false——此时没有接收方，后续帧必然也失败。 */
    private static boolean write(OutputStream out, String payload) {
        try {
            out.write(payload.getBytes(StandardCharsets.UTF_8));
            out.flush();
            return true;
        } catch (IOException gone) {
            return false;
        }
    }

    /**
     * 网关自己补的传输失败帧。
     *
     * <p>**先过一遍 sink 再写**：recorder 靠「看到 error 帧」把这一轮标记成失败，而额度退还
     * 依赖 `recorder.failed()`。直接 write 会绕过那一步，于是 provider 中途失败的那一轮白吃
     * 日额度——状态码在这里帮不上忙，开流那一刻它就已经是 200。
     */
    private static void writeErrorFrame(
            OutputStream out, String requestId, ErrorCode code,
            BiFunction<String, String, String> sink) {
        String message = code == ErrorCode.RAG_TIMEOUT ? "RAG 服务调用超时" : "RAG 服务不可达";
        String data = "{\"request_id\":\"" + requestId + "\",\"code\":\"" + code.name()
                + "\",\"message\":\"" + message + "\"}";
        try {
            sink.apply(EVENT_ERROR, data);
        } catch (RuntimeException ignored) {
            // 这一步只为让 recorder 标记失败；它失败也得把帧发出去。
        }
        write(out, rebuild(EVENT_ERROR, data));
    }

    private SseRelay() {
    }
}
