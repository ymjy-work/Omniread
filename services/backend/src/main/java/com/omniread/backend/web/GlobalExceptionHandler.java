package com.omniread.backend.web;

import com.omniread.backend.contract.model.ErrorBody;
import com.omniread.backend.error.ErrorCode;
import com.omniread.backend.error.QuotaException;
import com.omniread.backend.error.RagException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestValueException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

/**
 * 非 2xx 一律 {request_id, code, message}：三字段扁平、不套 error 对象。
 *
 * 这里只覆盖网关自己会产生错误的几条路径。未知 URL 的 404、方法不支持的 405
 * 交给框架默认处理 —— 它们不属于契约里的错误语义，用 RAG 的 code 去描述反而是错的。
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(RagException.class)
    public ResponseEntity<ErrorBody> handleRag(RagException failure, HttpServletRequest request) {
        return errorBody(failure.code(), failure.httpStatus(), failure.getMessage(), request);
    }

    /**
     * 超限：与其它错误体同形状，外加一个 `Retry-After`（秒）。
     *
     * <p>四个 429 的差别就在「要等多久」上，而这个数只有产生它的地方算得出来
     * （分钟窗口的最早一次、到明天零点的秒数、锁到什么时候），所以它随异常一起传上来，
     * 而不是在这里按 code 猜。
     */
    @ExceptionHandler(QuotaException.class)
    public ResponseEntity<ErrorBody> handleQuota(QuotaException failure, HttpServletRequest request) {
        return ResponseEntity.status(failure.httpStatus())
                .header(HttpHeaders.RETRY_AFTER, Long.toString(failure.retryAfterSeconds()))
                .contentType(MediaType.APPLICATION_JSON)
                .body(body(failure.code(), failure.getMessage(), request));
    }

    /**
     * 请求体 / 参数不符合形状（缺字段、类型不对、超长）一律 RAG_INVALID_REQUEST / 400。
     *
     * 这些是「前端该修自己」那一类：请求根本没描述清楚要做什么。RAG_INVALID_REALM 留给
     * 另一种 400 —— 「问题超出你声明的进度」，它的处置是提示用户改档位或改进度。
     * 两者同为 400，而前端只按 code 分支，混在一起就分不出该提示谁。
     *
     * 边界值（如进度 0 与 194）**不走这里**：它们由 {@code RealmValidator} 统一判，
     * 免得同一个字段的上下界各返回一个码。
     */
    @ExceptionHandler({MethodArgumentNotValidException.class, HandlerMethodValidationException.class,
            ConstraintViolationException.class, HttpMessageNotReadableException.class,
            MissingRequestValueException.class, MethodArgumentTypeMismatchException.class})
    public ResponseEntity<ErrorBody> handleInvalidInput(Exception failure, HttpServletRequest request) {
        // 六种异常共用一个出口，而**响应里看不出是哪一种**——排查时只知道「400」，
        // 不知道是请求体读不出来、还是某个 @RequestAttribute 没挂上、还是字段校验没过。
        // 只记异常类型，不记 message（后者可能把请求体片段带进日志）。
        log.warn(
                "入参校验失败：{} path={} cause={}",
                failure.getClass().getSimpleName(),
                request.getRequestURI(),
                failure.getCause() == null ? failure.getMessage() : failure.getCause().getMessage());
        return errorBody(
                ErrorCode.RAG_INVALID_REQUEST, ErrorCode.RAG_INVALID_REQUEST.httpStatus(), describe(failure), request);
    }

    private String describe(Exception failure) {
        if (failure instanceof MethodArgumentNotValidException invalid) {
            FieldError first = invalid.getBindingResult().getFieldErrors().stream().findFirst().orElse(null);
            if (first != null) {
                return "请求参数非法：" + first.getField() + " " + first.getDefaultMessage();
            }
        }
        return "请求参数非法";
    }

    private ResponseEntity<ErrorBody> errorBody(ErrorCode code, HttpStatusCode status, String message,
            HttpServletRequest request) {
        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body(code, message, request));
    }

    private ErrorBody body(ErrorCode code, String message, HttpServletRequest request) {
        return new ErrorBody(
                RequestIds.current(request),
                ErrorBody.CodeEnum.valueOf(code.name()),
                message);
    }
}
