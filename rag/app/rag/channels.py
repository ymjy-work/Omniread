import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.config.settings import settings
from app.rag.providers import PROVIDER_BASE_URLS, ChatTarget

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Channel:
    provider: str
    model: str
    api_key: str = field(repr=False)
    priority: int = 0
    enabled: bool = True

    def to_target(self) -> ChatTarget:
        return ChatTarget(
            provider=self.provider,
            model=self.model,
            api_key=self.api_key,
        )


def _parse_channel(index: int, item: object) -> Channel | None:
    if not isinstance(item, dict):
        logger.warning("skip channel #%d: entry is not an object", index)
        return None

    provider = item.get("provider")
    model = item.get("model")
    api_key = item.get("api_key")
    priority = item.get("priority", 0)
    enabled = item.get("enabled", True)

    if not isinstance(provider, str) or provider not in PROVIDER_BASE_URLS:
        logger.warning("skip channel #%d: unsupported provider", index)
        return None
    if not isinstance(model, str) or not model.strip():
        logger.warning("skip channel #%d: model is required", index)
        return None
    if not isinstance(api_key, str) or not api_key.strip():
        logger.warning("skip channel #%d: api_key is required", index)
        return None
    if not isinstance(priority, int) or isinstance(priority, bool):
        logger.warning("skip channel #%d: priority must be an integer", index)
        return None
    if not isinstance(enabled, bool):
        logger.warning("skip channel #%d: enabled must be a boolean", index)
        return None
    if not enabled:
        return None

    return Channel(
        provider=provider,
        model=model.strip(),
        api_key=api_key.strip(),
        priority=priority,
        enabled=True,
    )


def load_channels(path: str | None = None) -> list[Channel]:
    channel_path = Path(path or settings.channels_file)
    try:
        raw = channel_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        logger.warning("failed to read channels file %s: %s", channel_path, exc)
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("channels file %s is not valid JSON: %s", channel_path, exc)
        return []

    if not isinstance(data, list):
        logger.warning("channels file %s must contain a JSON array", channel_path)
        return []

    channels: list[Channel] = []
    for index, item in enumerate(data):
        channel = _parse_channel(index, item)
        if channel is not None:
            channels.append(channel)

    channels.sort(key=lambda channel: channel.priority)
    return channels