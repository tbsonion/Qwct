"""Documentation-backed protected entry preflight; NO simulated broker."""
from pathlib import Path

import pytest

from strategy.protected_entry import review_schwab_protected_entry


def test_multi_share_limit_entry_is_not_called_protected():
    result = review_schwab_protected_entry(
        side="long", shares=100, limit_price=100, stop_price=99.50,
        target_r=3, max_risk_usd=50,
    )
    assert result.risk_usd == 50
    assert result.target_price == 101.50
    assert not result.native_candidate
    assert not result.can_submit
    assert any("partial limit entry" in b for b in result.blockers)
    assert any("OCO" in b for b in result.blockers)


def test_short_multi_share_is_also_blocked():
    result = review_schwab_protected_entry(
        side="short", shares=10, limit_price=100, stop_price=101,
        target_r=3, max_risk_usd=50,
    )
    assert result.risk_usd == 10
    assert result.target_price == 97
    assert not result.can_submit
    assert not result.native_candidate


def test_one_whole_share_bracket_is_only_a_research_candidate():
    result = review_schwab_protected_entry(
        side="long", shares=1, limit_price=200, stop_price=199,
        target_r=3, max_risk_usd=50,
    )
    assert result.native_candidate
    assert result.target_price == 203
    assert not result.can_submit
    assert any("runtime-verified" in b for b in result.blockers)


def test_exceeding_planned_risk_is_explicitly_rejected():
    result = review_schwab_protected_entry(
        side="long", shares=100, limit_price=100, stop_price=99,
        target_r=3, max_risk_usd=50,
    )
    assert result.risk_usd == 100
    assert any("risk budget" in b for b in result.blockers)
    assert not result.can_submit


@pytest.mark.parametrize("kwargs", [
    dict(side="long", shares=0, limit_price=100, stop_price=99),
    dict(side="long", shares=True, limit_price=100, stop_price=99),
    dict(side="long", shares=1.2, limit_price=100, stop_price=99),
    dict(side="long", shares=1, limit_price=100, stop_price=100),
    dict(side="short", shares=1, limit_price=100, stop_price=99),
    dict(side="long", shares=1, limit_price=float("nan"), stop_price=99),
    dict(side="long", shares=1, limit_price=100, stop_price=float("inf")),
    dict(side="long", shares=1, limit_price=100, stop_price=-1),
    dict(side="unknown", shares=1, limit_price=100, stop_price=99),
])
def test_invalid_contract_fails_closed(kwargs):
    with pytest.raises(ValueError):
        review_schwab_protected_entry(
            **kwargs, target_r=3, max_risk_usd=50
        )


def test_order_submission_is_still_hard_disabled():
    main = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "self._native_exit_enabled = False" in main
    assert "self.bracket_order(" not in main
    assert "self.one_triggers_other_order(" not in main
    assert "self.limit_order(" not in main
    assert "self.stop_market_order(" not in main
