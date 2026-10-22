"""Model gateway: routing, price guard, cache, retry, usage accounting."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from studio.models import GenerationRequest, GenerationResult, UsageRecord
from studio.providers import build_providers
from studio.providers.base import Provider
from studio.store import Store

LOG = logging.getLogger("studio.gateway")


class BudgetExceeded(RuntimeError):
    pass


class UnitCostExceeded(BudgetExceeded):
    pass


class ProviderError(RuntimeError):
    pass


class Budget:
    def __init__(self, config: dict[str, Any]):
        self.max_cost_per_run = float(config.get("max_cost_per_run", 5.0))
        self.max_cost_per_image = float(config.get("max_cost_per_image", 0.10))
        self.max_cost_per_image_premium = float(config.get("max_cost_per_image_premium", 2.0))
        self.max_cost_per_video_minute = float(config.get("max_cost_per_video_minute", 1.0))
        self.max_cost_per_video_minute_premium = float(
            config.get("max_cost_per_video_minute_premium", 30.0)
        )
        self.spent = 0.0

    @property
    def remaining(self) -> float:
        return round(max(0.0, self.max_cost_per_run - self.spent), 6)

    def check_unit(self, request: GenerationRequest, price: float) -> None:
        premium = request.quality == "premium"
        if request.task in ("image.generate", "image.edit"):
            limit = self.max_cost_per_image_premium if premium else self.max_cost_per_image
            if price > limit + 1e-9:
                raise UnitCostExceeded(
                    f"image unit cost ¥{price:.4f} exceeds limit ¥{limit:.2f}"
                )
        elif request.task == "video.generate":
            seconds = request.duration_seconds or 5.0
            per_minute = price / seconds * 60.0
            limit = (
                self.max_cost_per_video_minute_premium
                if premium
                else self.max_cost_per_video_minute
            )
            if per_minute > limit + 1e-9:
                raise UnitCostExceeded(
                    f"video cost ¥{per_minute:.2f}/min exceeds limit ¥{limit:.2f}/min"
                )

    def check_total(self, price: float) -> None:
        if self.spent + price > self.max_cost_per_run + 1e-9:
            raise BudgetExceeded(
                f"run budget exhausted: spent ¥{self.spent:.4f}, "
                f"next ¥{price:.4f}, limit ¥{self.max_cost_per_run:.2f}"
            )

    def record(self, price: float) -> None:
        self.spent = round(self.spent + price, 6)


class Gateway:
    def __init__(
        self,
        config: dict[str, Any],
        store: Store,
        providers: dict[str, Provider] | None = None,
    ):
        self.config = config
        self.store = store
        self.currency = str(config.get("currency", "CNY"))
        self.providers = providers or build_providers(config.get("providers") or {})
        self.routing = config.get("routing") or {}
        self.budget = Budget(config.get("budget") or {})
        retry = config.get("retry") or {}
        self.max_attempts = max(1, int(retry.get("max_attempts", 2)))
        self.base_delay = float(retry.get("base_delay_seconds", 0.2))
        self.cache_enabled = bool((config.get("cache") or {}).get("enabled", True))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate(self, request: GenerationRequest, run_id: str, output_dir: Path) -> GenerationResult:
        candidates = self._candidates(request.task, request.quality)
        if not candidates:
            raise ProviderError(f"no route for task={request.task} quality={request.quality}")

        errors: list[str] = []
        for provider_name, model in candidates:
            provider = self.providers.get(provider_name)
            if provider is None:
                errors.append(f"{provider_name}/{model}: provider not registered")
                continue
            if not provider.supports(model, request.task):
                errors.append(f"{provider_name}/{model}: does not support {request.task}")
                continue
            price = provider.price(model, request)
            try:
                self.budget.check_unit(request, price)
            except UnitCostExceeded as exc:
                errors.append(f"{provider_name}/{model}: {exc}")
                LOG.warning("skip provider: %s", errors[-1])
                continue

            cache_key = self._cache_key(provider_name, model, request)
            if self.cache_enabled:
                cached = self._cache_hit(
                    cache_key, request, run_id, output_dir, provider_name, model
                )
                if cached is not None:
                    return cached

            for attempt in range(self.max_attempts):
                try:
                    self.budget.check_total(price)
                    result = provider.generate(model, request, output_dir)
                    result.cost = price
                    result.currency = self.currency
                    self.budget.record(price)
                    if self.cache_enabled:
                        self.store.cache_store(cache_key, result.to_dict(), Path(result.output_path))
                    self._record_usage(run_id, result)
                    self._event(run_id, "generation.succeeded", request, result)
                    return result
                except BudgetExceeded:
                    raise
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{provider_name}/{model} attempt {attempt + 1}: {exc}")
                    LOG.warning("generation failed: %s", errors[-1])
                    if attempt + 1 < self.max_attempts:
                        time.sleep(self.base_delay * (2 ** attempt))

        raise ProviderError("all providers failed:\n- " + "\n- ".join(errors))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _candidates(self, task: str, quality: str) -> list[tuple[str, str]]:
        route = self.routing.get(task) or {}
        refs = route.get(quality) or route.get("standard") or []
        candidates: list[tuple[str, str]] = []
        for ref in refs:
            if "/" not in ref:
                continue
            provider, model = ref.split("/", 1)
            candidates.append((provider, model))
        return candidates

    def _cache_key(self, provider: str, model: str, request: GenerationRequest) -> str:
        payload = {
            "provider": provider,
            "model": model,
            "request": request.to_dict(),
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def _cache_hit(
        self,
        key: str,
        request: GenerationRequest,
        run_id: str,
        output_dir: Path,
        provider: str,
        model: str,
    ) -> GenerationResult | None:
        meta = self.store.cache_lookup(key)
        if not meta:
            return None
        filename = meta.get("cached_filename")
        if not filename:
            return None
        source = self.store.cache_path(key) / filename
        if not source.exists():
            return None
        output_dir.mkdir(parents=True, exist_ok=True)
        copied = output_dir / filename
        shutil.copy2(source, copied)
        result = GenerationResult(
            provider=provider,
            model=model,
            task=request.task,
            output_path=str(copied),
            cost=0.0,
            currency=self.currency,
            latency_ms=0,
            cached=True,
            metadata={"cache_key": key, "cached_from": meta.get("output_path", "")},
        )
        self._record_usage(run_id, result)
        self._event(run_id, "generation.cached", request, result)
        return result

    def _record_usage(self, run_id: str, result: GenerationResult) -> None:
        record = UsageRecord(
            run_id=run_id,
            provider=result.provider,
            model=result.model,
            task=result.task,
            cost=result.cost,
            currency=result.currency,
            latency_ms=result.latency_ms,
            cached=result.cached,
            ts=time.time(),
        )
        self.store.record_usage(record.to_dict())

    def _event(
        self,
        run_id: str,
        event_type: str,
        request: GenerationRequest,
        result: GenerationResult,
    ) -> None:
        self.store.log_event(
            run_id,
            {
                "ts": time.time(),
                "type": event_type,
                "task": request.task,
                "quality": request.quality,
                "provider": result.provider,
                "model": result.model,
                "cost": result.cost,
                "cached": result.cached,
                "output_path": result.output_path,
                "seed": request.seed,
                "reference_pack_id": request.metadata.get("reference_pack_id"),
            },
        )
