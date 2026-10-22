"""Configuration loading: YAML + environment variables, secrets never in YAML."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

try:  # optional in tests, but listed in requirements
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs):
        return False


DEFAULTS: dict[str, Any] = {
    "currency": "CNY",
    "data_dir": "data",
    "budget": {
        "max_cost_per_run": 5.00,
        "max_cost_per_image": 0.10,
        "max_cost_per_image_premium": 2.00,
        "max_cost_per_video_minute": 1.00,
        "max_cost_per_video_minute_premium": 30.00,
    },
    "retry": {
        "max_attempts": 2,
        "base_delay_seconds": 0.2,
    },
    "cache": {
        "enabled": True,
    },
    "qa": {
        "consistency_threshold": 0.85,
        "prompt_adherence_threshold": 0.70,
    },
    "providers": {
        "mock": {
            "type": "mock",
            "models": {
                "image.cheap": {
                    "unit": "image", "price": 0.06,
                    "tasks": ["image.generate", "image.edit"],
                },
                "image.premium": {
                    "unit": "image", "price": 0.30,
                    "tasks": ["image.generate", "image.edit"],
                },
                "llm.cheap": {
                    "unit": "request", "price": 0.002,
                    "tasks": ["llm.chat"],
                },
                "vision.qa": {
                    "unit": "request", "price": 0.005,
                    "tasks": ["vision.qa"],
                },
                "video.cheap": {
                    "unit": "second", "price": 0.01,
                    "tasks": ["video.generate"],
                },
            },
        }
    },
    "routing": {
        "image.generate": {
            "standard": ["mock/image.cheap"],
            "premium": ["mock/image.premium"],
        },
        "image.edit": {
            "standard": ["mock/image.cheap"],
            "premium": ["mock/image.premium"],
        },
        "llm.chat": {
            "standard": ["mock/llm.cheap"],
            "premium": ["mock/llm.cheap"],
        },
        "vision.qa": {
            "standard": ["mock/vision.qa"],
            "premium": ["mock/vision.qa"],
        },
        "video.generate": {
            "standard": ["mock/video.cheap"],
            "premium": ["mock/video.cheap"],
        },
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config.yaml if present, then apply environment overrides.

    Environment variables:
      STUDIO_DATA_DIR
      STUDIO_MAX_COST_PER_RUN
      STUDIO_MAX_COST_PER_IMAGE
      STUDIO_MAX_COST_PER_VIDEO_MINUTE
    API keys are read by providers from environment variables, not YAML.
    """

    root = Path.cwd()
    load_dotenv(root / ".env", override=False)

    config = copy.deepcopy(DEFAULTS)
    config_path = Path(path) if path else root / "config.yaml"
    if config_path.exists():
        with config_path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"config must be a mapping: {config_path}")
        config = _deep_merge(config, loaded)

    if os.getenv("STUDIO_DATA_DIR"):
        config["data_dir"] = os.environ["STUDIO_DATA_DIR"]
    budget = config.setdefault("budget", {})
    for env_key, cfg_key in (
        ("STUDIO_MAX_COST_PER_RUN", "max_cost_per_run"),
        ("STUDIO_MAX_COST_PER_IMAGE", "max_cost_per_image"),
        ("STUDIO_MAX_COST_PER_VIDEO_MINUTE", "max_cost_per_video_minute"),
    ):
        if os.getenv(env_key):
            budget[cfg_key] = float(os.environ[env_key])

    config["_root"] = str(root)
    return config


def data_dir(config: dict[str, Any]) -> Path:
    path = Path(config.get("data_dir", "data"))
    if not path.is_absolute():
        path = Path(config.get("_root", Path.cwd())) / path
    return path.resolve()


def provider_configs(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return config.get("providers") or {}
