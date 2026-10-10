package com.omniread.backend.web;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonUnwrapped;
import com.omniread.backend.contract.model.QueryResponse;

/**
 * 外部问答响应：共有核心 + 网关分配的两个标识。
 *
 * <p>`@JsonUnwrapped` 而不是把上游那几个字段逐个抄进来：抄一遍的话，`QueryResponse`
 * 将来多一个字段（契约改一处、生成器重跑一次，上游就带上了），这里会**静静地漏掉它**
 * ——前端看不到、后端也不报错，只有对比两份响应体时才发现。
 * 展开就没有这个中间层可漏。
 *
 * <p>`message_id` 是这一轮 assistant 消息在库里的 id（`chat_messages.id`，**不是 `seq`**）：
 * 前端拿它定位「从哪一条重新生成」。
 */
public class SessionQueryResponse {

    @JsonUnwrapped
    private QueryResponse upstream;

    @JsonProperty("session_id")
    private String sessionId;

    @JsonProperty("message_id")
    private Long messageId;

    public QueryResponse getUpstream() {
        return upstream;
    }

    public SessionQueryResponse setUpstream(QueryResponse upstream) {
        this.upstream = upstream;
        return this;
    }

    public String getSessionId() {
        return sessionId;
    }

    public SessionQueryResponse setSessionId(String sessionId) {
        this.sessionId = sessionId;
        return this;
    }

    public Long getMessageId() {
        return messageId;
    }

    public SessionQueryResponse setMessageId(Long messageId) {
        this.messageId = messageId;
        return this;
    }
}
