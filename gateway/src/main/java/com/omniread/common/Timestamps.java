package com.omniread.common;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

/** 库中 created_at / updated_at 的统一格式：定宽毫秒 ISO 字符串，可按字典序比较。 */
public final class Timestamps {

	private static final DateTimeFormatter FORMAT =
			DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC);

	private Timestamps() {
	}

	public static String now() {
		return FORMAT.format(Instant.now());
	}
}
