package com.omniread.common;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/** 全局异常 → 统一 Result，HTTP 状态与错误码对齐。 */
@RestControllerAdvice
public class GlobalExceptionHandler {

	private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

	@ExceptionHandler(BusinessException.class)
	public ResponseEntity<Result<Void>> handleBusiness(BusinessException e) {
		ErrorCode ec = e.getErrorCode();
		return ResponseEntity.status(ec.getHttpStatus()).body(Result.error(ec, e.getMessage()));
	}

	@ExceptionHandler(MethodArgumentNotValidException.class)
	public ResponseEntity<Result<Void>> handleValidation(MethodArgumentNotValidException e) {
		String message = e.getBindingResult().getFieldErrors().stream()
				.map(err -> err.getField() + " " + err.getDefaultMessage())
				.findFirst()
				.orElse(ErrorCode.BAD_REQUEST.getMessage());
		return ResponseEntity.status(ErrorCode.BAD_REQUEST.getHttpStatus())
				.body(Result.error(ErrorCode.BAD_REQUEST, message));
	}

	@ExceptionHandler(HttpMessageNotReadableException.class)
	public ResponseEntity<Result<Void>> handleUnreadable(HttpMessageNotReadableException e) {
		return ResponseEntity.status(ErrorCode.BAD_REQUEST.getHttpStatus())
				.body(Result.error(ErrorCode.BAD_REQUEST, "请求体缺失或格式错误"));
	}

	@ExceptionHandler(NoResourceFoundException.class)
	public ResponseEntity<Result<Void>> handleNoResource(NoResourceFoundException e) {
		return ResponseEntity.status(ErrorCode.NOT_FOUND.getHttpStatus())
				.body(Result.error(ErrorCode.NOT_FOUND));
	}

	@ExceptionHandler(Exception.class)
	public ResponseEntity<Result<Void>> handleOther(Exception e) {
		log.error("未处理异常", e);
		return ResponseEntity.status(ErrorCode.INTERNAL_ERROR.getHttpStatus())
				.body(Result.error(ErrorCode.INTERNAL_ERROR));
	}
}
