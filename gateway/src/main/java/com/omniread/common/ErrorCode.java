package com.omniread.common;

/** 业务错误码及对应的 HTTP 状态。 */
public enum ErrorCode {

	OK(0, "ok", 200),
	BAD_REQUEST(40000, "参数错误", 400),
	UNAUTHORIZED(40100, "未登录或凭证失效", 401),
	FORBIDDEN(40300, "无权访问该资源", 403),
	NOT_FOUND(40400, "资源不存在", 404),
	TOO_MANY_REQUESTS(42900, "尝试过于频繁，请稍后再试", 429),
	INSUFFICIENT_CREDITS(40201, "积分不足", 400),
	INSUFFICIENT_BALANCE(40202, "余额不足，请联系管理员充值", 400),
	INTERNAL_ERROR(50000, "服务内部错误", 500),
	RAG_ERROR(50200, "检索服务不可用", 502),
	UPSTREAM_ERROR(50201, "模型服务不可用", 502);

	private final int code;
	private final String message;
	private final int httpStatus;

	ErrorCode(int code, String message, int httpStatus) {
		this.code = code;
		this.message = message;
		this.httpStatus = httpStatus;
	}

	public int getCode() {
		return code;
	}

	public String getMessage() {
		return message;
	}

	public int getHttpStatus() {
		return httpStatus;
	}
}
