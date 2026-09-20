package com.omniread.backend.web;

import jakarta.servlet.http.HttpServletRequest;
import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.regex.Pattern;

/**
 * request_id 由 Java 生成并向下透传（X-Request-Id），Python 不自己造。
 *
 * 格式固定为 `req_` + 32 位小写十六进制（共 36 字符），与契约 pattern 一致；
 * 两侧日志按同一个 id 对齐，客户端拿到的错误体里也是它。
 */
public final class RequestIds {

    /** 请求头名与请求属性名。属性名是编译期常量，供 @RequestAttribute 直接引用。 */
    public static final String HEADER = "X-Request-Id";

    public static final String ATTRIBUTE = "omniread.requestId";

    /** MDC 键名，与 application.yml 日志 pattern 里的 %X{...} 逐字一致。 */
    public static final String MDC_KEY = "request_id";

    private static final Pattern FORMAT = Pattern.compile("^req_[0-9a-f]{32}$");

    private static final SecureRandom RANDOM = new SecureRandom();

    public static String next() {
        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);
        return "req_" + HexFormat.of().formatHex(bytes);
    }

    /** 当前请求的 request_id；过滤器未覆盖时（理论上不发生）现场生成一个。 */
    public static String current(HttpServletRequest request) {
        Object existing = request.getAttribute(ATTRIBUTE);
        if (existing instanceof String requestId) {
            return requestId;
        }
        String requestId = next();
        request.setAttribute(ATTRIBUTE, requestId);
        return requestId;
    }

    public static boolean isValid(String value) {
        return value != null && FORMAT.matcher(value).matches();
    }

    private RequestIds() {
    }
}
