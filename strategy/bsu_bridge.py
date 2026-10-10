"""Native D1 swing-origin -> read-only Gerchik BPU research bridge.

Inputs ONLY: an as-of morning D1 DataFrame fed by actual LEAN TradeBars,
its observed native per-bar end times, a confirmed swing-cluster Level
and a native LEAN Security.symbol_properties.minimum_price_variation.

A swing is an ALGORITHMIC BSU PROXY, not proof that a discretionary
trader would identify the same BSU. Closed M5 BPU2 also cannot
establish the original :30-before-close TVX limit entry.
"""
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

import pandas as pd

from .config import StrategyConfig
from .patterns_bsu import BsuDetector
from .scenarios import ScenarioDecision


@dataclass(frozen=True)
class BsuResearchLink:
    detector: BsuDetector
    origin_time: datetime
    tick_size: float
    provenance: str = "D1_CONFIRMED_SWING_PROXY_NOT_CANONICAL_BSU"


def create_bsu_research_observer(
    decision: ScenarioDecision,
    d1_asof: pd.DataFrame,
    native_tick_size: float | None,
    cfg: StrategyConfig,
) -> tuple[BsuResearchLink | None, str]:
    """Fail-closed creation for the bounce-only closed-M5 research observer.

    Returns (observer, reason). It does not add subscriptions, place an
    order, emit a trade intent, or access external data.
    """
    if decision is None or not decision.accepted or decision.model != "bounce":
        return None, "not an accepted D1 bounce scenario"
    lvl = decision.level
    if lvl is None or (
        (lvl.kind, decision.side) not in (("support", "long"),
                                          ("resistance", "short"))
    ):
        return None, "D1 bounce level kind/side mismatch (mirror not assumed)"
    if lvl.source != "swing_cluster":
        return None, "no traced D1 swing_cluster origin"
    if (lvl.valid_from is None or lvl.valid_from > decision.session
            or lvl.formed_at is None
            or lvl.touches < cfg.min_touches
            or lvl.strength < cfg.min_level_strength):
        return None, "D1 level not confirmed as of the session"

    try:
        tick = float(native_tick_size)
        if not isfinite(tick) or tick <= 0:
            return None, "native LEAN minimum tick size missing"
    except (TypeError, ValueError, OverflowError):
        return None, "native LEAN minimum tick size missing"

    if (d1_asof is None or d1_asof.empty or
            not isinstance(d1_asof.index, pd.DatetimeIndex) or
            d1_asof.index.tz is None or
            not d1_asof.index.is_monotonic_increasing or
            not d1_asof.index.is_unique):
        return None, "invalid native closed D1 chronology"
    if any(day.date() >= decision.session for day in d1_asof.index):
        return None, "D1 source includes unclosed/current session"
    if "bar_end" not in d1_asof.columns:
        return None, "missing native D1 bar_end timestamps"
    if (lvl.first_idx < 0 or lvl.last_idx <= lvl.first_idx or
            lvl.last_idx >= len(d1_asof)):
        return None, "invalid D1 swing indices"
    if d1_asof.index[lvl.last_idx].date() != lvl.formed_at:
        return None, "D1 swing formation does not match original source"

    # Preserve actual native D1 bar end (not guessed exchange-close time).
    try:
        origin_end = pd.Timestamp(d1_asof.iloc[lvl.first_idx]["bar_end"])
        newest_end = pd.Timestamp(d1_asof.iloc[-1]["bar_end"])
        decided_at = pd.Timestamp(decision.decided_at)
        if (origin_end.tzinfo is None or newest_end.tzinfo is None
                or decided_at.tzinfo is None
                or pd.isna(origin_end) or pd.isna(newest_end)):
            return None, "native D1 bar_end has no valid timezone"
        if not (origin_end < newest_end < decided_at):
            return None, "native D1 source originates after morning decision"
        if d1_asof.index[lvl.first_idx].date() >= decision.session:
            return None, "historical origin not closed before session"
        origin_price = float(d1_asof.iloc[lvl.first_idx][
            "low" if lvl.kind == "support" else "high"])
        if (not isfinite(origin_price) or origin_price <= 0
                or not isfinite(lvl.price) or lvl.price <= 0
                or abs(origin_price - lvl.price) > tick * 0.500001):
            return None, "swing origin price is not an exact native-tick level"
        atr_value = float(d1_asof.iloc[-1][f"atr{cfg.atr_period}"])
        if not isfinite(atr_value) or atr_value <= 0:
            return None, "native D1 ATR is not ready"
        detector = BsuDetector(
            cfg, float(lvl.price), decision.side,
            atr_value=atr_value, tick_size=tick,
            bsu_ts=origin_end.to_pydatetime())
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        return None, f"invalid native D1 BSU proxy evidence: {exc}"

    return BsuResearchLink(
        detector=detector,
        origin_time=origin_end.to_pydatetime(),
        tick_size=tick,
    ), "research-only D1 swing origin linked; NOT a canonical BSU or TVX"
