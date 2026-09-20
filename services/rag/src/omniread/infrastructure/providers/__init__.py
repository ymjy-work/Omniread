"""模型 provider 适配器：GLM 回答、阿里百炼 embedding / rerank，以及测试用的确定性假 provider。

接口（`ChatModel` / `EmbeddingModel` / `RerankModel`）与 `ModelRegistry` 见 M0-01 §5；
客户端复用 `httpx`，不引入 LangChain。
"""

from __future__ import annotations

from omniread.infrastructure.providers.ali import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    RERANK_MODEL,
    AliEmbeddingAdapter,
    AliRerankAdapter,
)
from omniread.infrastructure.providers.base import (
    ChatChunk,
    ChatMessage,
    ChatModel,
    ChatOptions,
    ChatResponse,
    EmbeddingModel,
    RerankModel,
    RerankResult,
)
from omniread.infrastructure.providers.errors import (
    ProviderConfigError,
    ProviderError,
    ProviderResponseError,
    ProviderTimeoutError,
    to_rag_error,
)
from omniread.infrastructure.providers.fake import (
    FakeChatModel,
    FakeEmbeddingModel,
    FakeRerankModel,
    FaultyChatModel,
)
from omniread.infrastructure.providers.glm import (
    GLM_ANSWER_MODEL,
    GLM_API_KEY_ENV,
    GLM_BASE_URL,
    GlmChatAdapter,
)

__all__ = [
    "EMBEDDING_DIM",
    "EMBEDDING_MODEL",
    "GLM_ANSWER_MODEL",
    "GLM_API_KEY_ENV",
    "GLM_BASE_URL",
    "RERANK_MODEL",
    "AliEmbeddingAdapter",
    "AliRerankAdapter",
    "ChatChunk",
    "ChatMessage",
    "ChatModel",
    "ChatOptions",
    "ChatResponse",
    "EmbeddingModel",
    "FakeChatModel",
    "FakeEmbeddingModel",
    "FakeRerankModel",
    "FaultyChatModel",
    "GlmChatAdapter",
    "ProviderConfigError",
    "ProviderError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "RerankModel",
    "RerankResult",
    "to_rag_error",
]
