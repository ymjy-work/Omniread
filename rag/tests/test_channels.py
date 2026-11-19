import json
from pathlib import Path

from app.rag.channels import Channel, load_channels


def write_channels(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_channels_sorts_by_priority_and_skips_invalid(
    tmp_path: Path,
) -> None:
    path = write_channels(
        tmp_path / "channels.json",
        [
            {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "sk-b",
                "priority": 20,
                "enabled": True,
            },
            {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "api_key": "sk-a",
                "priority": 10,
                "enabled": True,
            },
            {
                "provider": "siliconflow",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "api_key": "sk-disabled",
                "priority": 1,
                "enabled": False,
            },
            {
                "provider": "unknown",
                "model": "x",
                "api_key": "sk-unknown",
                "priority": 0,
                "enabled": True,
            },
            {
                "provider": "bailian",
                "model": "qwen3.7-plus",
                "api_key": "",
                "priority": 5,
                "enabled": True,
            },
        ],
    )

    channels = load_channels(str(path))

    assert [(item.provider, item.model) for item in channels] == [
        ("deepseek", "deepseek-chat"),
        ("openai", "gpt-4o-mini"),
    ]


def test_missing_channels_file_returns_empty(tmp_path: Path) -> None:
    assert load_channels(str(tmp_path / "missing.json")) == []


def test_invalid_json_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "channels.json"
    path.write_text("{not json", encoding="utf-8")

    assert load_channels(str(path)) == []


def test_channel_repr_hides_api_key() -> None:
    channel = Channel("openai", "gpt-4o-mini", "sk-secret", priority=1)

    assert "sk-secret" not in repr(channel)