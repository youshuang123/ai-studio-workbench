from __future__ import annotations

from pathlib import Path

import pytest

from studio.config import load_config
from studio.gateway import BudgetExceeded, Gateway, ProviderError
from studio.models import GenerationRequest
from studio.store import Store


def make_gateway(tmp_path: Path, **budget_overrides) -> Gateway:
    config = load_config(tmp_path / "missing.yaml")
    config["data_dir"] = str(tmp_path / "data")
    config["budget"].update(budget_overrides)
    store = Store(config["data_dir"])
    return Gateway(config, store)


def image_request() -> GenerationRequest:
    return GenerationRequest(
        task="image.generate",
        prompt="电商主图，商品 SKU-001，颜色 #1f6feb，保持形状和 logo 一致。",
        seed=42,
        metadata={"sku": "SKU-001"},
    )


def test_image_unit_cost_guard_skips_expensive_provider(tmp_path: Path) -> None:
    gateway = make_gateway(tmp_path, max_cost_per_image=0.05)
    with pytest.raises(ProviderError, match="exceeds limit"):
        gateway.generate(image_request(), "run-1", tmp_path / "run-1")


def test_run_budget_guard_stops_calls(tmp_path: Path) -> None:
    gateway = make_gateway(tmp_path, max_cost_per_image=0.10, max_cost_per_run=0.01)
    with pytest.raises(BudgetExceeded, match="run budget exhausted"):
        gateway.generate(image_request(), "run-1", tmp_path / "run-1")


def test_cache_hit_costs_zero_and_copies_asset(tmp_path: Path) -> None:
    gateway = make_gateway(tmp_path)
    first = gateway.generate(image_request(), "run-1", tmp_path / "run-1")
    second = gateway.generate(image_request(), "run-2", tmp_path / "run-2")

    assert first.cached is False
    assert first.cost == pytest.approx(0.06)
    assert second.cached is True
    assert second.cost == 0.0
    assert Path(second.output_path).exists()
    assert gateway.budget.spent == pytest.approx(0.06)
