from __future__ import annotations

from studio.cost import image_cost, i2v_minute_cost, light_motion_cost


def test_image_target_is_met_with_cheap_api() -> None:
    assert image_cost(0.06) <= 0.10
    assert image_cost(0.10) <= 0.10
    assert image_cost(0.15) > 0.10


def test_light_motion_target_is_met() -> None:
    assert light_motion_cost() <= 1.00


def test_full_i2v_target_is_not_met_at_normal_prices() -> None:
    assert i2v_minute_cost(0.05) <= 1.00
    assert i2v_minute_cost(0.10) > 1.00
