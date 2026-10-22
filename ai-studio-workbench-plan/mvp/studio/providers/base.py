"""Provider interface + shared pricing logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from studio.models import GenerationRequest, GenerationResult


class Provider(ABC):
    """A model provider adapter.

    Contract:
      - price() is pure and must not call the network.
      - generate() writes exactly one primary artifact into output_dir and
        returns its path. Errors are raised; the gateway handles retries.
    """

    name: str

    def __init__(self, name: str, models: dict[str, dict[str, Any]]):
        self.name = name
        self.models = models or {}

    def model_config(self, model: str) -> dict[str, Any]:
        if model not in self.models:
            raise KeyError(f"provider {self.name} has no model {model}")
        return self.models[model]

    def supports(self, model: str, task: str) -> bool:
        cfg = self.model_config(model)
        tasks = cfg.get("tasks")
        return not tasks or task in tasks

    def price(self, model: str, request: GenerationRequest) -> float:
        cfg = self.model_config(model)
        unit = cfg.get("unit", "request")
        unit_price = float(cfg.get("price", 0.0))
        if unit == "second":
            seconds = request.duration_seconds or 5.0
            return round(unit_price * seconds, 6)
        if unit == "minute":
            seconds = request.duration_seconds or 60.0
            return round(unit_price * seconds / 60.0, 6)
        return round(unit_price, 6)

    @abstractmethod
    def generate(self, model: str, request: GenerationRequest, output_dir: Path) -> GenerationResult:
        raise NotImplementedError
