package com.omniread.common;

/** 统一响应体：成功 code=0，失败 code 见 ErrorCode。 */
public class Result<T> {

	private int code;
	private String message;
	private T data;

	public Result() {
	}

	public Result(int code, String message, T data) {
		this.code = code;
		this.message = message;
		this.data = data;
	}

	public static <T> Result<T> ok(T data) {
		return new Result<>(ErrorCode.OK.getCode(), ErrorCode.OK.getMessage(), data);
	}

	public static Result<Void> ok() {
		return ok(null);
	}

	public static <T> Result<T> error(ErrorCode errorCode) {
		return new Result<>(errorCode.getCode(), errorCode.getMessage(), null);
	}

	public static <T> Result<T> error(ErrorCode errorCode, String message) {
		return new Result<>(errorCode.getCode(), message, null);
	}

	public int getCode() {
		return code;
	}

	public void setCode(int code) {
		this.code = code;
	}

	public String getMessage() {
		return message;
	}

	public void setMessage(String message) {
		this.message = message;
	}

	public T getData() {
		return data;
	}

	public void setData(T data) {
		this.data = data;
	}
}
