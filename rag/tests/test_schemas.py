import pytest
from pydantic import ValidationError

from app.schemas import AskRequest


def make_request(**overrides: object) -> AskRequest:
    payload: dict[str, object] = {
        "book_id": 1,
        "question": "问题",
        "level": "full",
    }
    payload.update(overrides)
    return AskRequest(**payload)


def test_defaults_to_auto_without_provider_fields() -> None:
    request = make_request()

    assert request.mode == "auto"
    assert request.provider is None
    assert request.model is None
    assert request.api_key is None


def test_platform_defaults_provider_to_bailian() -> None:
    request = make_request(mode="platform", model="qwen3.7-plus")

    assert request.provider == "bailian"
    assert request.model == "qwen3.7-plus"


@pytest.mark.parametrize(
    "overrides",
    [
        {"mode": "auto", "provider": "bailian"},
        {"mode": "auto", "model": "qwen3.7-plus"},
        {"mode": "auto", "api_key": "sk-secret"},
        {"mode": "platform"},
        {"mode": "platform", "model": "m", "provider": "openai"},
        {"mode": "platform", "model": "m", "api_key": "sk-secret"},
        {"mode": "byok", "provider": "openai", "model": "m"},
        {"mode": "byok", "provider": "openai", "api_key": "sk-secret"},
        {"mode": "byok", "provider": "unknown", "model": "m", "api_key": "sk"},
    ],
)
def test_invalid_mode_combinations_are_rejected(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        make_request(**overrides)


def test_byok_accepts_provider_model_and_key() -> None:
    request = make_request(
        mode="byok",
        provider="deepseek",
        model="deepseek-chat",
        api_key="sk-user-key",
    )

    assert request.provider == "deepseek"
    assert request.model == "deepseek-chat"
    assert request.api_key == "sk-user-key"


def test_request_repr_hides_api_key() -> None:
    request = make_request(
        mode="byok",
        provider="openai",
        model="gpt-4o-mini",
        api_key="sk-user-key",
    )

    assert "sk-user-key" not in repr(request)