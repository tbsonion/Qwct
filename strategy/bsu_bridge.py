"""Native D1 swing-origin -> read-only Gerchik BPU research bridge.

Inputs ONLY: an as-of morning D1 DataFrame fed by actual LEAN TradeBars,
its observed native per-bar end times, a confirmed swing-cluster Level
and a native LEAN Security.symbol_properties.minimum_price_variation.

A swing is an ALGORITHMIC BSU PROXY, not proof that a discretionary
trader would identify the same BSU. Closed M5 BPU2 also cannot
establish the original :30-before-close TVX limit entry.
"""
from dataclasses import dataclass
from datetime import date, datetime
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



@dataclass(frozen=True)
class RawBsuEvidence:
    """As-of observed RAW D1 pivot, verified against SCALED_RAW provenance."""
    pivot_date: date
    pivot_end: datetime
    latest_date: date
    origin_price: float
    scaled_origin: float
    cluster_price: float
    raw_close: float
    scaled_close: float
    tick: float
    bar_count: int


def resolve_raw_bsu_evidence(
    decision, d1_asof, native_tick_size, raw_bars, time_index
) -> RawBsuEvidence:
    """Reconcile the SAME native daily swing and last closed day as of 09:29.

    Never round historical levels, infer a split factor or mix price bases.
    No M5 history is accessed; RAW minute subscription is required upstream.
    """
    lvl = decision.level
    tick = float(native_tick_size)
    if (lvl is None or lvl.source != "swing_cluster"
            or not isfinite(tick) or tick <= 0
            or d1_asof is None or d1_asof.empty
            or not isinstance(d1_asof.index, pd.DatetimeIndex)
            or d1_asof.index.tz is None
            or not d1_asof.index.is_unique
            or not d1_asof.index.is_monotonic_increasing
            or "bar_end" not in d1_asof.columns
            or lvl.first_idx < 0 or lvl.first_idx >= len(d1_asof)):
        raise ValueError("RAW basis: missing confirmed D1 pivot, timestamps or tick")
    idx = lvl.first_idx
    pivot_date = d1_asof.index[idx].date()
    latest_date = d1_asof.index[-1].date()
    field = "low" if lvl.kind == "support" else "high"
    if lvl.kind not in ("support", "resistance"):
        raise ValueError("RAW basis: unsupported pivot direction")
    decision_at = pd.Timestamp(decision.decided_at)
    pivot_end = pd.Timestamp(d1_asof.iloc[idx]["bar_end"])
    scaled_origin = float(d1_asof.iloc[idx][field])
    scaled_close = float(d1_asof.iloc[-1]["close"])
    if (decision_at.tzinfo is None or pivot_end.tzinfo is None
            or pd.isna(pivot_end) or not pivot_end < decision_at
            or pivot_date >= decision.session or latest_date >= decision.session):
        raise ValueError("RAW basis: future or unclosed SCALED_RAW D1")

    observed_pivot, observed_last = [], []
    prev_date = None
    count = 0
    for bar in raw_bars:
        raw_start = pd.Timestamp(time_index(bar.time))
        raw_end = pd.Timestamp(time_index(bar.end_time))
        if (raw_start.tzinfo is None or raw_end.tzinfo is None
                or pd.isna(raw_start) or pd.isna(raw_end)
                or raw_end <= raw_start or raw_end >= decision_at
                or raw_start.date() >= decision.session):
            raise ValueError("RAW History contains unclosed/future D1 data")
        day = raw_start.date()
        if prev_date is not None and day <= prev_date:
            raise ValueError("RAW basis: duplicate or unordered D1 dates")
        prev_date = day
        if getattr(bar, "symbol", None) is not None and (
                str(bar.symbol) != str(decision.symbol)):
            raise ValueError("RAW basis: symbol mismatch")
        if day == pivot_date:
            if raw_end != pivot_end:
                raise ValueError("RAW and SCALED_RAW origin EndTime mismatch")
            observed_pivot.append(float(getattr(bar, field)))
        if day == latest_date:
            scaled_last_end = pd.Timestamp(d1_asof.iloc[-1]["bar_end"])
            if raw_end != scaled_last_end:
                raise ValueError("RAW and SCALED_RAW latest EndTime mismatch")
            observed_last.append(float(bar.close))
        count += 1

    if len(observed_pivot) != 1 or len(observed_last) != 1:
        raise ValueError("RAW origin/latest D1 missing or duplicated")
    origin, raw_close = observed_pivot[0], observed_last[0]
    if not all(isfinite(x) and x > 0 for x in (
            origin, raw_close, scaled_origin, scaled_close)):
        raise ValueError("RAW basis: invalid observed historical OHLC")
    if abs(origin - round(origin / tick) * tick) > tick * 1e-5:
        raise ValueError("RAW origin off native tick grid")
    # The newest completed daily candle must be on the same price basis
    # as live RAW M5. A large residual implies unverified normalization.
    if abs(raw_close - scaled_close) > tick * 0.5 + tick * 1e-7:
        raise ValueError("RAW/SCALED_RAW latest close price bases disagree")
    # A historical corporate-action split can shift a pivot far away from
    # the screened D1 cluster. Never silently use it as an exact BSU.
    if not isfinite(float(lvl.price)) or float(lvl.price) <= 0:
        raise ValueError("RAW basis: invalid screened cluster")
    return RawBsuEvidence(
        pivot_date, pivot_end.to_pydatetime(), latest_date, origin,
        scaled_origin, float(lvl.price), raw_close, scaled_close, tick, count)


def create_bsu_research_observer(
    decision: ScenarioDecision,
    d1_asof: pd.DataFrame,
    native_tick_size: float | None,
    cfg: StrategyConfig,
    *, raw_evidence: RawBsuEvidence | None = None,
    require_raw: bool = False,
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
        scaled_origin = float(d1_asof.iloc[lvl.first_idx][
            "low" if lvl.kind == "support" else "high"])
        if require_raw and raw_evidence is None:
            return None, "native RAW D1 pivot evidence missing; fail closed"
        if raw_evidence is not None:
            if (raw_evidence.pivot_date != d1_asof.index[lvl.first_idx].date()
                    or pd.Timestamp(raw_evidence.pivot_end) != origin_end
                    or raw_evidence.latest_date != d1_asof.index[-1].date()
                    or abs(raw_evidence.scaled_origin - scaled_origin) > tick * 1e-7
                    or abs(raw_evidence.tick - tick) > tick * 1e-7):
                return None, "native RAW D1 pivot provenance mismatch"
            origin_price = raw_evidence.origin_price
        else:
            origin_price = scaled_origin
        atr_value = float(d1_asof.iloc[-1][f"atr{cfg.atr_period}"])
        if not isfinite(atr_value) or atr_value <= 0:
            return None, "native D1 ATR is not ready"
        if (not isfinite(origin_price) or origin_price <= 0
                or not isfinite(lvl.price) or lvl.price <= 0):
            return None, "swing origin price/cluster level is invalid"
        # All exact-touch BSU comparisons must use a native tick-grid pivot.
        # With RAW evidence, origin_price is the actual original D1 extreme;
        # without it, preserve the original conservative research behavior.
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
    ), (("native RAW D1 origin confirmed; " if raw_evidence is not None
         else "research-only D1 native pivot linked; ")
        + "cluster median distinct from pivot; NOT a canonical BSU or TVX")


def audit_bsu_price_basis(decision, d1_asof, native_tick_size,
                          raw_bars, time_index):
    """Print the reconciled true pivot and cluster WITHOUT changing orders."""
    e = resolve_raw_bsu_evidence(
        decision, d1_asof, native_tick_size, raw_bars, time_index)
    side_field = "low" if decision.level.kind == "support" else "high"
    def offset(price):
        return abs(price - round(price / e.tick) * e.tick)
    return (
        f"QWCT BSU BASIS {decision.symbol} {decision.session} "
        f"pivot_date={e.pivot_date} pivot_end={e.pivot_end.isoformat()} "
        f"field={side_field} raw={e.origin_price:.8f} "
        f"scaled={e.scaled_origin:.8f} cluster={e.cluster_price:.8f} "
        f"tick={e.tick:.6f} raw_off={offset(e.origin_price):.8f} "
        f"scaled_off={offset(e.scaled_origin):.8f} "
        f"factor_scaled/raw={e.scaled_origin/e.origin_price:.9f} "
        f"last={e.latest_date} raw_close={e.raw_close:.6f} "
        f"scaled_close={e.scaled_close:.6f} bars={e.bar_count}; "
        "OBSERVATION ONLY / NO ORDERS"
    )
