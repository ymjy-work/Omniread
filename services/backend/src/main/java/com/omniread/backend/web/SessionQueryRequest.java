package com.omniread.backend.web;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.omniread.backend.contract.model.QueryRequest;
import jakarta.validation.constraints.NotNull;

/**
 * 外部问答请求体：共有核心 + 网关自己的 `session_id`。
 *
 * <p>**继承生成的 {@link QueryRequest} 而不是重抄一遍**：契约那边就是 `allOf`
 * （共有核心 + 各自扩展），生成出来的 `QueryRequest` 正是那个核心，而 `session_id`
 * 是「只有 Java 认」的字段——契约里那句话写明了。重抄一遍等于把核心的字段与约束
 * 复制成第二份，之后契约改一处、这里漏一处，而漏掉的那处只表现为
 * 「前端传了但后端没收到」，两边都不报错。
 */
public class SessionQueryRequest extends QueryRequest {

    @JsonProperty("session_id")
    @NotNull
    private String sessionId;

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }
}
