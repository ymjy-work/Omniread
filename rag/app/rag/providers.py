from dataclasses import dataclass, field
from typing import Any

PROVIDER_BASE_URLS: dict[str, str] = {
    "bailian": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
}


@dataclass(frozen=True, slots=True)
class ChatTarget:
    provider: str
    model: str
    api_key: str = field(repr=False)
    fallback: bool = False

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"


def build_chat_model(provider: str, model: str, api_key: str) -> Any:
    if provider not in PROVIDER_BASE_URLS:
        raise ValueError(f"unsupported provider: {provider}")

    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "base_url": PROVIDER_BASE_URLS[provider],
        "api_key": api_key,
        "model": model,
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    if provider == "bailian" and model.startswith("qwen"):
        kwargs["extra_body"] = {"enable_thinking": False}
    return ChatOpenAI(**kwargs)


def redact_secrets(text: str, *secrets: str | None) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text
