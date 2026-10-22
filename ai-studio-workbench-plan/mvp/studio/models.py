"""Core data contracts for the AI Studio MVP skeleton.

Keep these dataclasses small and serializable: every run should be reproducible
from the request + provider/model + seed + reference pack.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GenerationRequest:
    """One generation/edit/QA request sent through the model gateway."""

    task: str
    prompt: str
    quality: str = "standard"  # standard | premium
    reference_images: list[str] = field(default_factory=list)
    seed: int | None = None
    width: int = 1024
    height: int = 1024
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GenerationResult:
    """What a provider returns. `output_path` is relative to the run directory."""

    provider: str
    model: str
    task: str
    output_path: str
    cost: float
    currency: str = "CNY"
    latency_ms: int = 0
    cached: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReferencePack:
    """Consistency inputs for a SKU or a character.

    API-only reality: we cannot assume every provider supports LoRA. The pack
    therefore carries reference images, a prompt template, a seed, and a color
    profile; providers that support custom models can add them as metadata.
    """

    id: str
    kind: str  # sku | character
    name: str
    prompt: str
    seed: int
    color: str = "#cccccc"
    references: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QAReport:
    asset_id: str
    passed: bool
    scores: dict[str, float]
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssetRecord:
    asset_id: str
    kind: str
    path: str
    provider: str
    model: str
    seed: int | None
    reference_pack_id: str
    cost: float
    qa_passed: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UsageRecord:
    run_id: str
    provider: str
    model: str
    task: str
    cost: float
    currency: str
    latency_ms: int
    cached: bool
    ts: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
