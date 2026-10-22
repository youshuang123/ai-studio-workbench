"""Provider factory."""

from __future__ import annotations

from typing import Any

from studio.providers.base import Provider
from studio.providers.http import HTTPProvider
from studio.providers.mock import MockProvider


def build_provider(name: str, config: dict[str, Any]) -> Provider:
    kind = str(config.get("type", "mock")).lower()
    if kind == "mock":
        return MockProvider(name, config.get("models") or {})
    if kind == "http":
        return HTTPProvider(name, config)
    raise ValueError(f"unknown provider type: {kind}")


def build_providers(configs: dict[str, dict[str, Any]]) -> dict[str, Provider]:
    return {name: build_provider(name, cfg) for name, cfg in configs.items()}
