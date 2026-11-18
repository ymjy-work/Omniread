package com.omniread.common;

import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class ResultAndExceptionTest {

	@Test
	void okResultHasCodeZero() {
		Result<String> result = Result.ok("hello");
		assertEquals(0, result.getCode());
		assertEquals("hello", result.getData());
		assertEquals(0, Result.ok().getCode());
	}

	@Test
	void errorResultCarriesCodeAndNoData() {
		Result<Void> result = Result.error(ErrorCode.NOT_FOUND, "章节不存在");
		assertEquals(40400, result.getCode());
		assertEquals("章节不存在", result.getMessage());
		assertNull(result.getData());
	}

	@Test
	void businessExceptionMapsToHttpStatusAndResult() {
		GlobalExceptionHandler handler = new GlobalExceptionHandler();
		ResponseEntity<Result<Void>> response =
				handler.handleBusiness(new BusinessException(ErrorCode.UNAUTHORIZED, "用户名或密码错误"));
		assertEquals(401, response.getStatusCode().value());
		assertEquals(40100, response.getBody().getCode());
		assertEquals("用户名或密码错误", response.getBody().getMessage());
	}

	@Test
	void unknownExceptionMapsTo500() {
		GlobalExceptionHandler handler = new GlobalExceptionHandler();
		ResponseEntity<Result<Void>> response = handler.handleOther(new RuntimeException("boom"));
		assertEquals(500, response.getStatusCode().value());
		assertEquals(50000, response.getBody().getCode());
	}
}
