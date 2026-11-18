package com.omniread.chat.model;

/** chat_message 表行；citations_json 仅 assistant 消息有值。 */
public class ChatMessageEntity {

	private Long id;
	private Long sessionId;
	private String role;
	private String content;
	private String citationsJson;
	private String createdAt;

	public Long getId() {
		return id;
	}

	public void setId(Long id) {
		this.id = id;
	}

	public Long getSessionId() {
		return sessionId;
	}

	public void setSessionId(Long sessionId) {
		this.sessionId = sessionId;
	}

	public String getRole() {
		return role;
	}

	public void setRole(String role) {
		this.role = role;
	}

	public String getContent() {
		return content;
	}

	public void setContent(String content) {
		this.content = content;
	}

	public String getCitationsJson() {
		return citationsJson;
	}

	public void setCitationsJson(String citationsJson) {
		this.citationsJson = citationsJson;
	}

	public String getCreatedAt() {
		return createdAt;
	}

	public void setCreatedAt(String createdAt) {
		this.createdAt = createdAt;
	}
}
