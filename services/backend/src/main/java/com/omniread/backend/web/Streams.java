package com.omniread.backend.web;

import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.gateway.RagStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/**
 * 把上游的未读尽响应体搬给客户端。
 *
 * 同步写、固定 8KB 缓冲、每片即刷：图片不整读进内存，SSE 上一旦 Python 写出帧就立刻到浏览器。
 * 不用 StreamingResponseBody（异步）走这条路：它的输出流把 flush 攒到任务结束才落盘，
 * 实测首个字节要等整条流跑完才到客户端 —— 那就不是流式了。
 */
final class Streams {

    private static final int BUFFER_SIZE = 8 * 1024;

    /** 图片等一次性响应体：读完即关，异常直接上抛（此时状态码还可以改）。 */
    static void forward(RagStream stream, OutputStream out) throws IOException {
        try (InputStream in = stream.body()) {
            pump(in, out);
        }
    }

    /**
     * SSE：帧已经开始发之后 HTTP 状态码改不了，失败只能用终止帧表达（契约 §8.5）。
     * 连接已经断开时写终止帧同样会失败，忽略即可 —— 没有接收方了。
     */
    static void forwardSse(RagStream stream, String requestId, OutputStream out) {
        try (InputStream in = stream.body()) {
            pump(in, out);
        } catch (Exception failure) {
            writeErrorFrame(out, requestId, ErrorCode.fromTransportFailure(failure));
        }
    }

    private static void pump(InputStream in, OutputStream out) throws IOException {
        byte[] buffer = new byte[BUFFER_SIZE];
        int read;
        while ((read = in.read(buffer)) != -1) {
            out.write(buffer, 0, read);
            out.flush();
        }
    }

    private static void writeErrorFrame(OutputStream out, String requestId, ErrorCode code) {
        String message = code == ErrorCode.RAG_TIMEOUT ? "RAG 服务调用超时" : "RAG 服务不可达";
        String frame = "event: error\ndata: {\"request_id\":\"" + requestId
                + "\",\"code\":\"" + code.name()
                + "\",\"message\":\"" + escape(message) + "\"}\n\n";
        try {
            out.write(frame.getBytes(StandardCharsets.UTF_8));
            out.flush();
        } catch (IOException ignored) {
            // 客户端已断开，终止帧无人接收。
        }
    }

    private static String escape(String text) {
        return text.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private Streams() {
    }
}
