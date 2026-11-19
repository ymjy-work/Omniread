from app.rag.providers import (
    PROVIDER_BASE_URLS,
    ChatTarget,
    build_chat_model,
    redact_secrets,
)


def test_provider_base_urls_are_fixed() -> None:
    assert PROVIDER_BASE_URLS == {
        "bailian": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "siliconflow": "https://api.siliconflow.cn/v1",
    }


def test_bailian_qwen_disables_thinking() -> None:
    model = build_chat_model("bailian", "qwen3.7-plus", "sk-test")

    assert model.openai_api_base == PROVIDER_BASE_URLS["bailian"]
    assert model.extra_body == {"enable_thinking": False}


def test_other_models_do_not_receive_thinking_flag() -> None:
    cases = [
        ("bailian", "deepseek-v3"),
        ("openai", "gpt-4o-mini"),
        ("deepseek", "deepseek-chat"),
        ("siliconflow", "Qwen/Qwen2.5-7B-Instruct"),
    ]
    for provider, model_name in cases:
        model = build_chat_model(provider, model_name, "sk-test")
        assert model.openai_api_base == PROVIDER_BASE_URLS[provider]
        assert model.extra_body is None


def test_chat_target_repr_hides_api_key() -> None:
    target = ChatTarget("openai", "gpt-4o-mini", "sk-secret")

    assert "sk-secret" not in repr(target)
    assert "sk-secret" not in str(target)


def test_redact_secrets_replaces_all_occurrences() -> None:
    text = "bad key=sk-one and sk-two"

    assert redact_secrets(text, "sk-one", "sk-two") == (
        "bad key=[redacted] and [redacted]"
    )