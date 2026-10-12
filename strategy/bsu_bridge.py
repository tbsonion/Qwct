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
from .levels import native_cluster_tolerance
from .patterns_bsu import BsuDetector
from .scenarios import ScenarioDecision


@dataclass(frozen=True)
class BsuResearchLink:
    detector: BsuDetector
    origin_time: datetime
    tick_size: float
    # The median of a D1 swing cluster is a screening/scenario level, not
    # automatically the native origin swing's exact high/low.
    cluster_price: float
    origin_price: float
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
        atr_value = float(d1_asof.iloc[-1][f"atr{cfg.atr_period}"])
        if not isfinite(atr_value) or atr_value <= 0:
            return None, "native D1 ATR is not ready"
        if (not isfinite(origin_price) or origin_price <= 0
                or not isfinite(lvl.price) or lvl.price <= 0):
            return None, "swing origin price/cluster level is invalid"
        # SPLIT_ADJUSTED may rescale historical raw cents to fractions
        # of a current tick. Such an origin is not evidence of a
        # directly tradable native BSU price: fail closed.
        if abs(round(origin_price / tick) * tick - origin_price) > tick * 1e-5:
            return None, "BSU historical origin off native tick grid; normalization unsafe"
        # Swing clustering is allowed to group nearby, but distinct,
        # native daily highs/lows. The *first actual pivot extreme* is a
        # traceable research origin; the cluster median cannot be called
        # the exact price that originated BSU. Ensure both belong to the
        # same as-of ATR-tolerance cluster; don't fabricate an origin.
        cluster_tol = native_cluster_tolerance(d1_asof, cfg)
        if (cluster_tol is None or
                abs(origin_price - lvl.price) > cluster_tol + tick * 1e-7):
            return None, "native pivot lies outside the D1 cluster tolerance"
        detector = BsuDetector(
            cfg, origin_price, decision.side,
            atr_value=atr_value, tick_size=tick,
            bsu_ts=origin_end.to_pydatetime())
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        return None, f"invalid native D1 BSU proxy evidence: {exc}"

    return BsuResearchLink(
        detector=detector,
        origin_time=origin_end.to_pydatetime(),
        tick_size=tick,
        cluster_price=float(lvl.price),
        origin_price=origin_price,
    ), ("research-only D1 native pivot linked; cluster median distinct "
        "from pivot; NOT a canonical BSU or TVX")


def audit_bsu_price_basis(decision, d1_asof, native_tick_size,
                          raw_bars, time_index):
    """Read-only comparison of the SAME pivot date in native RAW vs D1.

    Never round/repair an input level, alter a detector, or fetch future data.
    The caller explicitly supplies LEAN RAW daily history as-of the decision.
    """
    lvl = decision.level
    tick = float(native_tick_size)
    if (lvl is None or lvl.source != "swing_cluster" or
            not isfinite(tick) or tick <= 0 or
            lvl.first_idx < 0 or lvl.first_idx >= len(d1_asof)):
        raise ValueError("no confirmed native pivot/tick to audit")
    idx = lvl.first_idx
    pivot_day = d1_asof.index[idx].date()
    latest_day = d1_asof.index[-1].date()
    side_field = "low" if lvl.kind == "support" else "high"
    scaled_origin = float(d1_asof.iloc[idx][side_field])
    scaled_latest = float(d1_asof.iloc[-1]["close"])
    decision_at = pd.Timestamp(decision.decided_at)
    scaled_end = pd.Timestamp(d1_asof.iloc[idx]["bar_end"])
    if (decision_at.tzinfo is None or scaled_end.tzinfo is None or
            not scaled_end < decision_at or
            pivot_day >= decision.session or latest_day >= decision.session):
        raise ValueError("D1/decision chronology cannot be proven")

    native_pivot, native_latest, raw_count = [], [], 0
    for bar in raw_bars:
        day = pd.Timestamp(time_index(bar.time)).date()
        end = pd.Timestamp(time_index(bar.end_time))
        if end.tzinfo is None or not end < decision_at or day >= decision.session:
            raise ValueError("RAW History contains unclosed/future D1 data")
        if day == pivot_day:
            if end != scaled_end:
                raise ValueError("RAW and SCALED_RAW origin EndTime mismatch")
            native_pivot.append(float(getattr(bar, side_field)))
        if day == latest_day:
            native_latest.append(float(bar.close))
        raw_count += 1

    if len(native_pivot) != 1 or len(native_latest) != 1:
        raise ValueError("RAW origin/latest D1 missing or duplicated")
    raw_origin, raw_close = native_pivot[0], native_latest[0]
    if not all(isfinite(v) and v > 0 for v in
               (raw_origin, raw_close, scaled_origin, scaled_latest)):
        raise ValueError("nonpositive/nonfinite RAW or SCALED_RAW price")
    def offset(price):
        return abs(price - round(price / tick) * tick)
    return (
        f"QWCT BSU BASIS {decision.symbol} {decision.session} "
        f"pivot_date={pivot_day} pivot_end={scaled_end.isoformat()} "
        f"field={side_field} raw={raw_origin:.8f} "
        f"scaled={scaled_origin:.8f} cluster={lvl.price:.8f} "
        f"tick={tick:.6f} raw_off={offset(raw_origin):.8f} "
        f"scaled_off={offset(scaled_origin):.8f} "
        f"factor_scaled/raw={scaled_origin/raw_origin:.9f} "
        f"last={latest_day} raw_close={raw_close:.6f} "
        f"scaled_close={scaled_latest:.6f} bars={raw_count}; "
        "OBSERVATION ONLY / NO ORDERS"
    )
