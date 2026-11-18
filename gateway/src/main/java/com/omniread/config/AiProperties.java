package com.omniread.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** rag 服务地址与超时。gateway 不接触模型 key。 */
@ConfigurationProperties(prefix = "omniread.rag")
public class AiProperties {

	private String baseUrl = "http://127.0.0.1:8000";
	private Duration connectTimeout = Duration.ofSeconds(5);
	private Duration askTimeout = Duration.ofSeconds(120);
	private Duration indexTimeout = Duration.ofSeconds(600);

	public String getBaseUrl() {
		return baseUrl;
	}

	public void setBaseUrl(String baseUrl) {
		this.baseUrl = baseUrl;
	}

	public Duration getConnectTimeout() {
		return connectTimeout;
	}

	public void setConnectTimeout(Duration connectTimeout) {
		this.connectTimeout = connectTimeout;
	}

	public Duration getAskTimeout() {
		return askTimeout;
	}

	public void setAskTimeout(Duration askTimeout) {
		this.askTimeout = askTimeout;
	}

	public Duration getIndexTimeout() {
		return indexTimeout;
	}

	public void setIndexTimeout(Duration indexTimeout) {
		this.indexTimeout = indexTimeout;
	}
}
