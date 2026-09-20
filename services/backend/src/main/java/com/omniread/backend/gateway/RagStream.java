package com.omniread.backend.gateway;

import java.io.InputStream;
import org.springframework.http.MediaType;

/**
 * 上游未读尽的响应体：图片字节流与 SSE 帧流共用。
 *
 * 刻意不把内容读成 byte[] —— 图片可能很大，SSE 更是无终点，
 * 读进内存再转发会把「流式」变成「先攒完再发」。
 * 拿到本对象的一方负责关闭 body。
 */
public record RagStream(MediaType contentType, long contentLength, InputStream body) {
}
