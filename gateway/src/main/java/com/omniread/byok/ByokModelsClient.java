package com.omniread.byok;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/** 用用户已存 Key 调提供商的 OpenAI 兼容 /models；Key 只进请求头，不写日志、不进异常信息。 */
@Component
public class ByokModelsClient {

	private static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(5);
	private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(20);

	private final Function<String, String> baseUrls;
	private final HttpClient httpClient;
	private final ObjectMapper mapper = JsonMapper.builder().build();

	public ByokModelsClient() {
		this(ByokProviders::baseUrl);
	}

	ByokModelsClient(Function<String, String> baseUrls) {
		this.baseUrls = baseUrls;
		this.httpClient = HttpClient.newBuilder()
				// 统一固定 HTTP/1.1，避免上游 h2c 升级差异
				.version(HttpClient.Version.HTTP_1_1)
				.connectTimeout(CONNECT_TIMEOUT)
				.build();
	}

	/** 返回按字母序去重后的模型 ID。 */
	public List<String> listModels(String provider, String apiKey) {
		try {
			HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrls.apply(provider) + "/models"))
					.timeout(REQUEST_TIMEOUT)
					.header("Authorization", "Bearer " + apiKey)
					.GET()
					.build();
			HttpResponse<String> response = httpClient.send(request,
					HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
			if (response.statusCode() / 100 != 2) {
				throw new BusinessException(ErrorCode.UPSTREAM_ERROR,
						provider + " /models 返回 HTTP " + response.statusCode());
			}
			JsonNode root = mapper.readTree(response.body());
			if (root == null) {
				throw new BusinessException(ErrorCode.UPSTREAM_ERROR, provider + " 模型列表响应为空");
			}
			List<String> models = new ArrayList<>();
			for (JsonNode node : root.path("data")) {
				String id = node.path("id").asString();
				if (id != null && !id.isBlank()) {
					models.add(id);
				}
			}
			return models.stream().distinct().sorted().toList();
		}
		catch (IOException e) {
			throw new BusinessException(ErrorCode.UPSTREAM_ERROR, "无法连接 " + provider + " 模型服务");
		}
		catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new BusinessException(ErrorCode.UPSTREAM_ERROR, provider + " 模型列表请求被中断");
		}
		catch (JacksonException e) {
			throw new BusinessException(ErrorCode.UPSTREAM_ERROR, provider + " 模型列表响应解析失败");
		}
	}
}
