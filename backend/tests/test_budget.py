from app.services.budget import check_budget, remaining_fen


def test_allows_when_budget_enough():
    ok, reason = check_budget(unit_price_fen=3, spent_fen=0, budget_fen=500)
    assert ok is True
    assert reason == ""


def test_blocks_when_single_price_over_budget():
    ok, reason = check_budget(unit_price_fen=600, spent_fen=0, budget_fen=500)
    assert ok is False
    assert "预算不足" in reason


def test_allows_when_exactly_equal():
    ok, _ = check_budget(unit_price_fen=500, spent_fen=0, budget_fen=500)
    assert ok is True


def test_blocks_zero_or_negative_budget():
    ok, reason = check_budget(unit_price_fen=3, spent_fen=0, budget_fen=0)
    assert ok is False
    assert "预算上限" in reason


def test_blocks_when_spent_plus_current_exceeds():
    ok, reason = check_budget(unit_price_fen=3, spent_fen=499, budget_fen=500)
    assert ok is False
    assert "预算不足" in reason


def test_blocks_when_unit_price_invalid():
    ok, reason = check_budget(unit_price_fen=0, spent_fen=0, budget_fen=500)
    assert ok is False
    assert "单价" in reason


def test_remaining_never_negative():
    assert remaining_fen(500, 600) == 0
    assert remaining_fen(500, 200) == 300
    assert remaining_fen(500, -10) == 500
