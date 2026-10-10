package com.omniread.backend.orchestration;

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

    @NotNull
    private String sessionId;

    /**
     * `@JsonProperty` 落在**读写方法**上而不是字段上——生成的那份 `QueryRequest` 就是这么
     * 标的，而两边不一致时 Jackson 会把 `session_id` 与 `sessionId` 当成两个属性：
     * 传进来的 `session_id` 没人接（字段留空），校验注解随即报 400，
     * 而报错信息说的是「sessionId 不能为空」——看起来像前端没传。
     */
    @JsonProperty("session_id")
    public String getSessionId() {
        return sessionId;
    }

    @JsonProperty("session_id")
    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }
}
