"""智谱 BigModel（GLM）回答适配器（M0-01 §5.2）。

协议转换在 `openai_compat.OpenAiCompatibleChatAdapter` 里——GLM 与 DeepSeek 的对话接口
是同一个形状（`POST {base_url}/chat/completions`、SSE 以 `[DONE]` 收尾），
写两份就会有两份要一起改的代码。这里只放这一家的常量与采样参数。

采样参数固定为官方建议值（`temperature=1`、`top_p=0.95`、`reasoning_effort=max`），
M0 的管线不覆盖；`ChatOptions` 显式给出的值仍然生效，覆盖是调用方的显式行为。

凭据只读环境变量 `GLM_API_KEY`，缺失时构造即抛 `ProviderConfigError`：不静默降级，
也不在日志里回显密钥。
"""

from __future__ import annotations

from typing import Any, ClassVar

from omniread.infrastructure.providers.openai_compat import (
    CHAT_TIMEOUT_SECONDS,
    OpenAiCompatibleChatAdapter,
)

GLM_API_KEY_ENV = "GLM_API_KEY"

GLM_ANSWER_MODEL = "glm-5.3-flash"

GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 官方建议采样参数（M0-01 §5.2）；M0 的管线不覆盖。
GLM_TEMPERATURE = 1.0

GLM_TOP_P = 0.95

GLM_REASONING_EFFORT = "max"


class GlmChatAdapter(OpenAiCompatibleChatAdapter):
    """`ChatModel` 的 GLM 实现，`model` 默认 `glm-5.3-flash`。"""

    provider = "glm"
    display_name = "GLM"
    api_key_env = GLM_API_KEY_ENV
    default_model = GLM_ANSWER_MODEL
    default_base_url = GLM_BASE_URL
    default_temperature = GLM_TEMPERATURE
    default_top_p = GLM_TOP_P
    # GLM 特有字段：只在这一家的请求体里出现，所以放在这里而不是基类。
    extra_payload: ClassVar[dict[str, Any]] = {"reasoning_effort": GLM_REASONING_EFFORT}


__all__ = [
    "CHAT_TIMEOUT_SECONDS",
    "GLM_ANSWER_MODEL",
    "GLM_API_KEY_ENV",
    "GLM_BASE_URL",
    "GLM_REASONING_EFFORT",
    "GLM_TEMPERATURE",
    "GLM_TOP_P",
    "GlmChatAdapter",
]
