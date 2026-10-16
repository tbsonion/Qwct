"""QWCT 4.6 — source-grounded BSU types; all labels author-unverified."""
from datetime import datetime, timedelta, timezone
import pytest

from strategy.gerchik_level_types import (
    LevelBar, classify_typed_bsu, FIXED_CANDIDATE, UNKNOWN, FLOATING, KINDS
)

T = datetime(2024, 6, 3, 10, tzinfo=timezone.utc)
def b(n, o=101., h=102., l=100., c=101.):
    return LevelBar(T+timedelta(days=n), o, h, l, c)

def check(kind, bars, side="long", **kwargs):
    return classify_typed_bsu(
        kind=kind, price=100., side=side, tick_size=.01,
        bars=bars, as_of=T+timedelta(days=10), **kwargs)


def test_46_all_eight_source_families_explicit():
    assert set(KINDS)=={"TREND_TURN","HISTORICAL","MIRROR","LIMIT_PLAYER",
                       "PARANORMAL","CONSOLIDATION","GAP","FLOATING"}


def test_46_fixed_limit_three_exact_hits_no_pierce():
    e=check("LIMIT_PLAYER",[b(0),b(1),b(2)])
    assert e.status==FIXED_CANDIDATE and e.confirmation_end==b(2).end
    assert not e.author_verified and not e.can_trade


def test_46_limit_pierce_is_floating_but_other_kinds_not_auto_invalidated():
    e=check("LIMIT_PLAYER",[b(0),b(1,l=99.99),b(2)])
    assert e.status==FLOATING
    e=check("HISTORICAL",[b(0),b(1,l=99.99),b(2)])
    assert e.status==FIXED_CANDIDATE


def test_46_historical_requires_exact_repeated_price():
    assert check("HISTORICAL",[b(0),b(1,l=100.01)]).status==UNKNOWN
    assert check("HISTORICAL",[b(0),b(1,l=100.)]).status==FIXED_CANDIDATE


def test_46_mirror_role_change_both_directions():
    # Original resistance -> new support: breakout above and retest from above.
    long=check("MIRROR",[
        b(0,o=99.,h=100.,l=98.,c=99.),
        b(1,o=99.,h=102.,l=99.,c=101.),
        b(2,o=101.,h=102.,l=100.,c=101.)])
    assert long.status==FIXED_CANDIDATE
    # Original support -> new resistance: breakout below and retest from below.
    short=check("MIRROR",[
        b(0,o=101.,h=102.,l=100.,c=101.),
        b(1,o=101.,h=101.,l=98.,c=99.),
        b(2,o=99.,h=100.,l=98.,c=99.)],side="short")
    assert short.status==FIXED_CANDIDATE


def test_46_mirror_needs_break_and_exact_retest():
    assert check("MIRROR",[b(0,o=99.,h=100.,l=98.,c=99.),
                            b(1,o=99.,h=100.,l=98.,c=99.)]).status==UNKNOWN


def test_46_paranormal_needs_2atr_and_retest():
    bars=[b(0,o=102.,h=104.,l=100.,c=103.),b(1)]
    assert check("PARANORMAL",bars,atr=2.).status==FIXED_CANDIDATE
    assert check("PARANORMAL",bars,atr=3.).status==UNKNOWN
    assert check("PARANORMAL",bars).status==UNKNOWN


@pytest.mark.parametrize("kind",["GAP","CONSOLIDATION","TREND_TURN"])
def test_46_qualitative_origins_not_auto_certified(kind):
    assert check(kind,[b(0),b(1),b(2)]).status==UNKNOWN


def test_46_floating_is_not_fixed():
    assert check("FLOATING",[b(0),b(1)]).status==FLOATING


def test_46_no_future_lookahead_or_reversed_history():
    with pytest.raises(ValueError,match="FUTURE_BAR_FORBIDDEN"):
        classify_typed_bsu(kind="HISTORICAL",price=100.,side="long",
            tick_size=.01,bars=[b(0),b(2)],as_of=T+timedelta(days=1))
    with pytest.raises(ValueError,match="BARS_OUT_OF_ORDER"):
        check("HISTORICAL",[b(1),b(0)])


def test_46_bad_price_and_ohlc_fail_closed():
    with pytest.raises(ValueError,match="OFF_NATIVE_TICK"):
        classify_typed_bsu(kind="HISTORICAL",price=100.005,side="long",
            tick_size=.01,bars=[b(0),b(1)],as_of=T+timedelta(days=10))
    with pytest.raises(ValueError,match="INVALID_OHLC"):
        b(0,o=103.,h=102.)


def test_46_source_without_confirmation_not_fixed():
    assert check("HISTORICAL",[b(0)]).status==UNKNOWN
