package com.omniread.backend.web;

import com.omniread.backend.gateway.RagStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * 把上游的未读尽响应体搬给客户端。
 *
 * 同步写、固定 8KB 缓冲、每片即刷：图片不整读进内存。
 * 不用 StreamingResponseBody（异步）走这条路：它的输出流把 flush 攒到任务结束才落盘，
 * 实测首个字节要等整条流跑完才到客户端 —— 那就不是流式了。
 *
 * SSE 不走这里：那条路要逐帧解析（回答得落库、终止帧要带 `message_id`），在 {@link SseRelay}。
 */
final class Streams {

    private static final int BUFFER_SIZE = 8 * 1024;

    /** 图片等一次性响应体：读完即关，异常直接上抛（此时状态码还可以改）。 */
    static void forward(RagStream stream, OutputStream out) throws IOException {
        try (InputStream in = stream.body()) {
            byte[] buffer = new byte[BUFFER_SIZE];
            int read;
            while ((read = in.read(buffer)) != -1) {
                out.write(buffer, 0, read);
                out.flush();
            }
        }
    }

    private Streams() {
    }
}
