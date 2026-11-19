package com.omniread.byok;

import java.util.List;

/** BYOK 固定提供商清单（均为 OpenAI 兼容端点）。 */
public final class ByokProviders {

	public static final List<String> ALL = List.of("bailian", "openai", "deepseek", "siliconflow");

	private ByokProviders() {
	}

	public static boolean contains(String provider) {
		return provider != null && ALL.contains(provider);
	}
}
