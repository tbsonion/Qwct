"""Read-only opening relative-volume evidence learned from published ORB research.

Compare the REAL first 09:30-09:35 ET M5 share volume of one US equity with
the same first-five-minute volume on the preceding 14 completed sessions.
This is an OPTIONAL Stocks-in-Play research metric, NOT a canonical Gerchik
rule, signal, stock universe, backtest, trading order or native data feed.

The caller MUST supply genuine LEAN-completed M5 TradeBar observations.
No default historical baseline, filled missing dates, volume normalization,
interpolated bars, estimated seasonal curves or look-ahead are allowed.
"""
from dataclasses import dataclass
from datetime import datetime, time
from math import isfinite
from zoneinfo import ZoneInfo


_ET = ZoneInfo("America/New_York")
_OPEN_END = time(9, 35)
_WINDOW = 14


@dataclass(frozen=True)
class OpeningVolumeBar:
    symbol: str
    end_time: datetime
    shares: float
    volume_basis: str
    is_fill_forward: bool = False


@dataclass(frozen=True)
class OpeningVolumeEvidence:
    symbol: str
    ratio: float | None
    current_shares: float | None
    mean_prior_shares: float | None
    prior_sessions: int
    status: str
    can_submit: bool = False


def _validate(bar: OpeningVolumeBar, symbol: str, basis: str):
    if not isinstance(bar, OpeningVolumeBar):
        raise ValueError("typed native opening-volume evidence required")
    if not symbol or bar.symbol != symbol:
        raise ValueError("mixed or missing equity symbol")
    if (not basis or basis == "UNKNOWN" or bar.volume_basis != basis):
        raise ValueError("historical and current volume basis not reconciled")
    if (not isinstance(bar.end_time, datetime)
            or bar.end_time.tzinfo is None
            or bar.end_time.utcoffset() is None):
        raise ValueError("unverified M5 timezone")
    end = bar.end_time.astimezone(_ET)
    if end.time() != _OPEN_END:
        raise ValueError("not a real completed 09:35 ET opening M5 candle")
    try:
        shares = float(bar.shares)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("non-numeric native M5 volume") from None
    if not isfinite(shares) or shares <= 0:
        raise ValueError("missing or zero-volume native opening M5")
    if bar.is_fill_forward:
        raise ValueError("forward-filled M5 cannot prove opening activity")
    return end.date(), shares


def review_opening_relative_volume(
    *, observed_at: datetime, current: OpeningVolumeBar,
    previous_openings: tuple[OpeningVolumeBar, ...],
) -> OpeningVolumeEvidence:
    """QuantConnect ORB comparator, NOT an independent reason to trade.

    After 09:35 ET on session T, take the actual M5 [09:30,09:35]
    traded volume for T and divide by the average corresponding M5
    traded volume for exactly the latest 14 *different prior sessions*.
    No missing data is filled; historical session continuity must be
    verified separately with native exchange-hours data. A mixed price
    normalization regime is explicit UNKNOWN, not a fake adjustment.
    """
    symbol = getattr(current, "symbol", "")
    unknown = lambda reason, n=0: OpeningVolumeEvidence(
        symbol, None, None, None, n, reason)
    try:
        if (not isinstance(observed_at, datetime)
                or observed_at.tzinfo is None
                or observed_at.utcoffset() is None):
            raise ValueError("unknown observation clock")
        observed = observed_at.astimezone(_ET)
        if observed.time() != _OPEN_END:
            raise ValueError("can only observe at 09:35 ET, not retroactively")
        if not isinstance(previous_openings, tuple):
            raise ValueError("prior opening evidence must be an explicit tuple")
        basis = current.volume_basis
        today, current_volume = _validate(current, symbol, basis)
        if today != observed.date():
            raise ValueError("observed current opening is not today's session")
        history = []
        seen = set()
        for item in previous_openings:
            d, shares = _validate(item, symbol, basis)
            if d >= today or d in seen:
                raise ValueError("prior opening is future, current, or duplicated")
            seen.add(d)
            history.append((d, shares))
        if len(history) < _WINDOW:
            return unknown("MISSING_14_ACTUAL_HISTORICAL_OPENINGS",
                           len(history))
        history.sort(reverse=True)
        latest = history[:_WINDOW]
        baseline = sum(shares for _, shares in latest) / _WINDOW
        if not isfinite(baseline) or baseline <= 0:
            raise ValueError("invalid native opening-volume baseline")
        ratio = current_volume / baseline
        if not isfinite(ratio):
            raise ValueError("unbounded relative opening volume")
        return OpeningVolumeEvidence(
            symbol, ratio, current_volume, baseline,
            len(latest), "RESEARCH_ONLY_NOT_GERCHIK_APPROVAL")
    except ValueError as exc:
        return unknown(str(exc))
