"""DeepSeek 适配器：查询改写与摘要用的模型。

`https://api.deepseek.com` 是 OpenAI 兼容的根地址，对话接口在 `/chat/completions`
——与 GLM 同一个形状，所以协议转换走 `openai_compat` 的基类，这里只有常量。
（另有一个 Anthropic 兼容的 `https://api.deepseek.com/anthropic`，本项目不用它：
两侧的消息格式不同，为它再写一个适配器没有收益。）

**没有默认采样参数**：这一家不做官方建议值那一套，而调用方（改写与摘要）要的是
**尽量确定**的输出，所以由调用方显式给 `temperature=0`——不在这里替它选。

凭据只读环境变量 `DEEPSEEK_API_KEY`。与 GLM 不同的是，**这条链缺凭据时不该让整条
query 失败**：改写与摘要是增强步骤，缺凭据只降级。那个「只降级」的决定在装配处
（`api/app.py` 里单独 try），不在这里——适配器只管自己构造失败要抛什么。
"""

from __future__ import annotations

from omniread.infrastructure.providers.openai_compat import (
    CHAT_TIMEOUT_SECONDS,
    OpenAiCompatibleChatAdapter,
)

DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"

DEEPSEEK_MODEL = "deepseek-flash"

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekChatAdapter(OpenAiCompatibleChatAdapter):
    """`ChatModel` 的 DeepSeek 实现，`model` 默认 `deepseek-flash`。"""

    provider = "deepseek"
    display_name = "DeepSeek"
    api_key_env = DEEPSEEK_API_KEY_ENV
    default_model = DEEPSEEK_MODEL
    default_base_url = DEEPSEEK_BASE_URL


__all__ = [
    "CHAT_TIMEOUT_SECONDS",
    "DEEPSEEK_API_KEY_ENV",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DeepSeekChatAdapter",
]
