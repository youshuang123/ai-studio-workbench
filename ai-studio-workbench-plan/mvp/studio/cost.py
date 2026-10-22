"""Cost formulas from the PRD.

All amounts are CNY unless stated otherwise. These are planning models, not
vendor invoices; replace the assumptions with your negotiated prices.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostAssumptions:
    retry_rate: float = 0.15
    cache_hit: float = 0.20
    image_qa: float = 0.005
    image_storage: float = 0.002
    video_audio_per_min: float = 0.05
    video_qa_per_min: float = 0.02
    video_storage_per_min: float = 0.02
    motion_render_per_min: float = 0.02
    keyframes_per_min: int = 10

    target_image: float = 0.10
    target_video_minute: float = 1.00


def image_cost(api_price: float, assumptions: CostAssumptions | None = None) -> float:
    a = assumptions or CostAssumptions()
    return round(
        api_price * (1 + a.retry_rate) * (1 - a.cache_hit) + a.image_qa + a.image_storage,
        4,
    )


def light_motion_cost(assumptions: CostAssumptions | None = None, keyframe_price: float = 0.06) -> float:
    a = assumptions or CostAssumptions()
    keyframes = a.keyframes_per_min * image_cost(keyframe_price, a)
    return round(
        keyframes + a.motion_render_per_min + a.video_audio_per_min
        + a.video_qa_per_min + a.video_storage_per_min,
        4,
    )


def i2v_minute_cost(
    api_price_per_5s: float,
    assumptions: CostAssumptions | None = None,
    seconds_per_clip: float = 5.0,
) -> float:
    a = assumptions or CostAssumptions()
    clips_per_min = 60.0 / seconds_per_clip
    generation = api_price_per_5s * clips_per_min * (1 + a.retry_rate)
    return round(
        generation + a.video_audio_per_min + a.video_qa_per_min + a.video_storage_per_min,
        4,
    )


def check_image_target(api_price: float, assumptions: CostAssumptions | None = None) -> tuple[bool, float]:
    a = assumptions or CostAssumptions()
    cost = image_cost(api_price, a)
    return cost <= a.target_image, cost


def check_video_target(api_price_per_5s: float, assumptions: CostAssumptions | None = None) -> tuple[bool, float]:
    a = assumptions or CostAssumptions()
    cost = i2v_minute_cost(api_price_per_5s, a)
    return cost <= a.target_video_minute, cost
