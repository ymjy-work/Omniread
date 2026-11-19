package com.omniread.byok;

import java.util.List;
import java.util.Map;

/** BYOK 固定提供商清单（均为 OpenAI 兼容端点）。 */
public final class ByokProviders {

	public static final List<String> ALL = List.of("bailian", "openai", "deepseek", "siliconflow");

	private static final Map<String, String> BASE_URLS = Map.of(
			"bailian", "https://dashscope.aliyuncs.com/compatible-mode/v1",
			"openai", "https://api.openai.com/v1",
			"deepseek", "https://api.deepseek.com/v1",
			"siliconflow", "https://api.siliconflow.cn/v1");

	private ByokProviders() {
	}

	public static boolean contains(String provider) {
		return provider != null && ALL.contains(provider);
	}

	public static String baseUrl(String provider) {
		return BASE_URLS.get(provider);
	}
}
