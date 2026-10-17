"""Построение уровней на D1 без заглядывания в будущее.

Семантика as-of (разбор замечания #11 из AGENTS.md):
- свинг-экстремум на баре i подтверждается только закрытием бара i+k;
- уровень становится торгуемым (valid_from) утром следующего торгового дня;
- утренний срез levels_for_session() возвращает только уровни с
  valid_from <= день сессии.

В курсе уровни строятся вручную слева направо; здесь аппроксимация —
кластеризация подтверждённых свингов с допуском в долях ATR.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import isfinite

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .indicators import atr


@dataclass
class Level:
    price: float
    kind: str                      # "resistance" | "support" | "mirror"
    touches: int = 0
    strength: float = 0.0
    valid_from: date | None = None  # с какого дня уровень торгуем
    first_idx: int = 0
    last_idx: int = 0
    formed_by_consolidation: bool = False
    notes: list = field(default_factory=list)
    # --- происхождение (PR #3, исследование) ---
    source: str = "swing_cluster"  # swing_cluster|mirror|gap|round_number|
                                   # high_5d|low_5d|prev_close|open_today
    formed_at: date | None = None   # когда сформировался источник
    intraday: bool = False          # True: ориентир только текущей сессии
    original_kind: str | None = None  # mirror only: role before D1 break/retest


def _confirmed_swings(d1: pd.DataFrame, k: int):
    """Свинги, подтверждённые закрытыми барами.

    Возвращает (highs, lows): списки (idx, price, confirm_date),
    где confirm_date — дата закрытия бара i+k.
    """
    n = len(d1)
    highs, lows = [], []
    # свинг на i подтверждается баром i+k -> i <= n-1-k
    for i in range(k, n - k):
        h, l = d1["high"].iloc[i], d1["low"].iloc[i]
        win_h = d1["high"].iloc[i - k:i + k + 1]
        win_l = d1["low"].iloc[i - k:i + k + 1]
        confirm_date = d1.index[i + k].date()
        # максимум окна, при равенстве — первое вхождение (устойчиво к дублям)
        if h >= win_h.max() and (win_h.iloc[:k] < h).all():
            highs.append((i, float(h), confirm_date))
        if l <= win_l.min() and (win_l.iloc[:k] > l).all():
            lows.append((i, float(l), confirm_date))
    return highs, lows


def _cluster(points: list[tuple], tol: float):
    """Жадная кластеризация по цене слева направо. Точка: (idx, price, confirm_date)."""
    clusters = []
    for idx, price, cdate in sorted(points, key=lambda p: p[0]):
        placed = False
        for cl in clusters:
            center = sum(p[1] for p in cl) / len(cl)
            if abs(price - center) <= tol:
                cl.append((idx, price, cdate))
                placed = True
                break
        if not placed:
            clusters.append([(idx, price, cdate)])
    return clusters


def native_cluster_tolerance(d1_asof: pd.DataFrame,
                             cfg: StrategyConfig,
                             atr_samples: pd.Series | None = None) -> float | None:
    """Same historical native D1 ATR tolerance for detector and BSU bridge.

    A cluster's price grouping uses the MEDIAN of ready ATRs, whereas
    stop distance for a new session uses its most recent ready ATR.
    Mixing the two makes valid historical clusters fail to arm BPU.
    """
    values = (atr_samples if atr_samples is not None
              else atr(d1_asof, cfg.atr_period))
    ready = values.loc[np.isfinite(values) & (values > 0)]
    if ready.empty:
        return None
    tolerance = float(ready.median() * cfg.level_tolerance_atr)
    return tolerance if np.isfinite(tolerance) and tolerance > 0 else None


def detect_levels(d1_asof: pd.DataFrame, cfg: StrategyConfig) -> list[Level]:
    """Уровни по закрытым дневкам. У каждого — valid_from (as-of)."""
    n = len(d1_asof)
    if n < 2 * cfg.swing_k + 5:
        return []
    a = atr(d1_asof, cfg.atr_period)
    # The bridge and level detector MUST agree on the exact historical
    # tolerance that created each D1 cluster. Never use last day's ATR
    # as an accidental substitute for the clustering threshold.
    tol = native_cluster_tolerance(d1_asof, cfg, a)
    if tol is None:
        return []

    highs, lows = _confirmed_swings(d1_asof, cfg.swing_k)
    levels: list[Level] = []
    for points, kind in ((highs, "resistance"), (lows, "support")):
        for cl in _cluster(points, tol):
            if len(cl) < cfg.min_touches:
                continue
            idxs = [p[0] for p in cl]
            price = float(np.median([p[1] for p in cl]))
            # торгуем со следующего дня после самого позднего подтверждения
            latest_confirm = max(p[2] for p in cl)
            lvl = Level(price=price, kind=kind, touches=len(cl),
                        first_idx=min(idxs), last_idx=max(idxs),
                        valid_from=latest_confirm + timedelta(days=1),
                        source="swing_cluster",
                        formed_at=d1_asof.index[max(idxs)].date())
            _score_level(lvl, d1_asof, cfg, a)
            levels.append(lvl)

    _mark_mirror(levels, d1_asof, cfg)
    levels.sort(key=lambda l: l.price)
    return levels


def _score_level(lvl: Level, d1: pd.DataFrame, cfg: StrategyConfig, a: pd.Series) -> None:
    score, notes = 0.0, []
    score += min(lvl.touches, 5) * 1.0
    start = max(0, lvl.first_idx - cfg.accumulation_bars)
    window = d1.iloc[start:lvl.first_idx]
    if len(window) >= cfg.accumulation_bars // 2:
        rng = window["high"].max() - window["low"].min()
        av = _native_atr(a, lvl.first_idx)
        if av is not None and rng <= cfg.accumulation_range_atr * av:
            score += 2.0
            lvl.formed_by_consolidation = True
            notes.append("сформирован проторговкой")
    for idx in (lvl.first_idx, lvl.last_idx):
        if idx + 1 < len(d1):
            nxt = d1.iloc[idx + 1]
            av = _native_atr(a, idx + 1)
            if av is not None and (nxt["high"] - nxt["low"]) >= cfg.big_bar_atr * av:
                score += 1.0
                notes.append("резкий разворот")
                break
    lvl.strength = round(score, 2)
    lvl.notes = notes


def _native_atr(a: pd.Series, idx: int) -> float | None:
    """Only native LEAN ATR snapshots can validate a level strength bonus.

    An OHLC bar range is not interchangeable with ATR(14). If the native
    indicator was still warming, the bonus stays UNKNOWN, not approved.
    """
    if idx < 0 or idx >= len(a):
        return None
    v = a.iloc[idx]
    return float(v) if pd.notna(v) and np.isfinite(v) and v > 0 else None


def _mark_mirror(levels: list[Level], d1: pd.DataFrame,
                 cfg: StrategyConfig) -> None:
    """Label only an observed AFTER-FORMATION role reversal on closed D1.

    Two candle wicks crossing a level is not evidence of a mirror. A prior
    support must CLOSE below, then be retested/rejected as resistance;
    resistance requires the opposite. This is a conservative approximation
    of the manual Gerchik mirror, not a certified BPU detector.
    """
    for lvl in levels:
        if lvl.kind not in ("support", "resistance"):
            continue
        # A k-right-bar pivot is not a confirmed level on its swing date.
        # A breach/retest that happened BEFORE valid_from cannot validate a
        # role reversal of a level the strategy did not know existed yet.
        # Actual detect_levels() always provides valid_from. When callers
        # construct a stand-alone Level without it, require at least the
        # post-swing sequence (never infer an earlier confirmation date).
        confirmed_idx = next(
            (i for i, ts in enumerate(d1.index)
             if ts.date() >= lvl.valid_from), len(d1)
        ) if lvl.valid_from is not None else lvl.last_idx + 1
        start = max(lvl.last_idx + 1, confirmed_idx,
                    len(d1) - cfg.mirror_lookback, 1)
        if start >= len(d1) - 1:
            continue
        breached = False
        for i in range(start, len(d1)):
            b = d1.iloc[i]
            if lvl.kind == "support":
                # Breach down, then separate later candle retests underside
                # of the support level and closes underneath it.
                confirmed = (breached and b["high"] >= lvl.price
                             and b["close"] < lvl.price)
                if not confirmed and b["close"] < lvl.price:
                    breached = True
            else:
                confirmed = (breached and b["low"] <= lvl.price
                             and b["close"] > lvl.price)
                if not confirmed and b["close"] > lvl.price:
                    breached = True
            if confirmed:
                lvl.original_kind = lvl.kind
                lvl.kind = "mirror"
                # Mirror is a NEW observed role reversal. Its valid_from
                # is after the completed confirming retest, never the
                # original support/resistance confirmation date.
                mirror_from = d1.index[i].date() + timedelta(days=1)
                lvl.valid_from = max(lvl.valid_from, mirror_from) if (
                    lvl.valid_from is not None) else mirror_from
                lvl.notes.append("mirror confirmed after D1 breach and retest")
                break


def levels_for_session(d1_asof: pd.DataFrame, day: date,
                       cfg: StrategyConfig) -> list[Level]:
    """Уровни, замороженные до открытия сессии дня `day` (утренний срез)."""
    return [l for l in detect_levels(d1_asof, cfg)
            if l.valid_from is not None and l.valid_from <= day]


def nearest_levels(levels: list[Level], price: float,
                   max_dist_atr: float, atr_value: float) -> list[Level]:
    return [l for l in levels
            if abs(l.price - price) <= max_dist_atr * max(atr_value, 1e-9)]


def next_level(levels: list[Level], price: float,
               direction: int) -> Level | None:
    """Следующий уровень по ходу движения; None если «пустота»."""
    cands = [l for l in levels
             if (l.price > price and direction > 0)
             or (l.price < price and direction < 0)]
    if not cands:
        return None
    if direction > 0:
        return min(cands, key=lambda l: l.price)
    return max(cands, key=lambda l: l.price)


# QWCT 3.5–3.7: read-only diagnostics on already available native D1.
# Not called by live trading, screener, or the original level detector.
@dataclass(frozen=True)
class D1WickReaction:
    """Closed D1 interaction geometry, NOT a source-confirmed Gerchik setup.

    TAIL_ONLY_RECLAIM requires the entire real BODY to stay on the defended
    side. BODY_CROSS_RECLAIM means the body spans the line, despite a
    defended-side close. Numeric fractions are descriptive, not trade scores.
    """

    at: date
    role: str
    event: str
    upper_wick: float
    lower_wick: float
    body: float
    defended_wick: float
    wick_to_body: float | None
    wick_to_range: float | None
    wick_to_atr: float | None
    penetration_to_atr: float | None
    close_defended_to_atr: float | None
    atr_status: str


def _d1_wick_reaction(candle, level, tick, role, at, atr_value, atr_requested):
    """Inspect a single as-of D1 bar that actually spans the level price."""
    if not float(candle.low) <= level <= float(candle.high):
        return None
    if role not in ("support", "resistance"):
        raise ValueError("INVALID_WICK_REACTION_ROLE")
    o, h, l, c = (float(candle[name]) for name in ("open", "high", "low", "close"))
    upper = h - max(o, c)
    lower = min(o, c) - l
    body = abs(c - o)
    span = h - l
    wick = lower if role == "support" else upper
    tol = tick * (0.5 + 1e-7)
    if role == "support":
        crossed = l < level - tol
        recovered = c > level + tol
        body_defended = min(o, c) >= level - tol
        closed_wrong = c < level - tol
        penetration = max(0.0, level - l)
        close_defended = c - level
    else:
        crossed = h > level + tol
        recovered = c < level - tol
        body_defended = max(o, c) <= level + tol
        closed_wrong = c > level + tol
        penetration = max(0.0, h - level)
        close_defended = level - c
    if crossed and recovered:
        event = "TAIL_ONLY_RECLAIM" if body_defended else "BODY_CROSS_RECLAIM"
    elif closed_wrong:
        event = "CLOSED_WRONG_SIDE"
    else:
        event = "TOUCH_OR_STRADDLE"

    if not atr_requested:
        atr_status, atr = "NOT_REQUESTED", None
    elif atr_value is None or pd.isna(atr_value):
        atr_status, atr = "NATIVE_ATR_NOT_READY", None
    else:
        try:
            atr = float(atr_value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("INVALID_NATIVE_D1_ATR") from exc
        if not isfinite(atr) or atr <= 0:
            raise ValueError("INVALID_NATIVE_D1_ATR")
        atr_status = "OK"
    return D1WickReaction(
        at=at, role=role, event=event, upper_wick=upper,
        lower_wick=lower, body=body, defended_wick=wick,
        wick_to_body=wick / body if body > 0 else None,
        wick_to_range=wick / span if span > 0 else None,
        wick_to_atr=wick / atr if atr is not None else None,
        penetration_to_atr=penetration / atr if atr is not None else None,
        close_defended_to_atr=close_defended / atr if atr is not None else None,
        atr_status=atr_status)


@dataclass(frozen=True)
class BsuSourceEvidence:
    label: str
    source_date: date
    confirmed_date: date
    price: float
    current_grid: str
    original_same_wick_dates: tuple
    mirror_exact_wick_dates: tuple
    mirror_pierce_dates: tuple
    # One D1 candle briefly crossing an old resistance/support and closing
    # back on the original side; objective OHLC event, not author-certified.
    original_wick_reclaim_dates: tuple = ()
    # As-of new mirror role: price crossed the line intraday but closed back
    # on the mirror's defended side. Not necessarily BSU/BPU1.
    mirror_wick_reclaim_dates: tuple = ()
    # A close on the wrong side (different from a wick that reclaims).
    mirror_close_through_dates: tuple = ()
    # Range crosses the source price; never counts as an exact BPU1 touch.
    mirror_range_cross_dates: tuple = ()
    # The SECOND candle's date: prior D1 close beyond line, next D1 close
    # back on defended side. An observation, not certified fake-out setup.
    original_two_bar_reclaim_dates: tuple = ()
    mirror_two_bar_reclaim_dates: tuple = ()
    # Chronological D1 interaction geometry on the original / mirror role.
    # Includes tail/body/ATR fractions, no extra data or signal approval.
    wick_reactions: tuple = ()
    status: str = "AUTHOR_UNVERIFIED"

    @property
    def can_trade(self):
        return False


def _close_enough(a, b, tick):
    # Same floating-point guard as BsuDetector; NOT an adjustable ATR tolerance.
    return abs(a - b) <= tick * (0.5 + 1e-7)


def _on_current_grid(price, tick):
    # Current grid is diagnostic, not authoritative for historic rebased prices.
    return abs(price / tick - round(price / tick)) <= 1e-5


def frozen_mirror_source_evidence(d1_asof, level, trace, *, session, tick_size, swing_k, atr_column=None):
    """Inspect confirmed FIRST/LAST RAW swing prices, no future M5.

    Inputs must be existing native closed RAW D1 bars, a native-created Level,
    and a 3.3 trace with PROXY_VERIFIED. Exact D1 wicks are observations,
    never a Gerchik-approved fixed BSU, BPU1 or executable signal.
    """
    if not isinstance(session, date) or isinstance(session, pd.Timestamp):
        raise ValueError("SESSION_DATE_REQUIRED")
    if not isinstance(swing_k, int) or isinstance(swing_k, bool) or swing_k < 1:
        raise ValueError("INVALID_SWING_K")
    try:
        tick = float(tick_size)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("INVALID_NATIVE_TICK") from exc
    if not isfinite(tick) or tick <= 0:
        raise ValueError("INVALID_NATIVE_TICK")
    if not isinstance(d1_asof, pd.DataFrame) or not isinstance(d1_asof.index, pd.DatetimeIndex):
        raise ValueError("INVALID_RAW_D1_FRAME")
    if (d1_asof.index.tz is None or d1_asof.empty or
            not d1_asof.index.is_unique or not d1_asof.index.is_monotonic_increasing):
        raise ValueError("INVALID_NATIVE_D1_INDEX")
    dates = [stamp.date() for stamp in d1_asof.index]
    if any(d >= session for d in dates) or any(x >= y for x, y in zip(dates, dates[1:])):
        raise ValueError("NONCAUSAL_OR_DUPLICATE_D1_DATE")
    for field in ("open", "high", "low", "close"):
        if field not in d1_asof:
            raise ValueError("MISSING_RAW_D1_OHLC")
        if not pd.to_numeric(d1_asof[field], errors="coerce").map(isfinite).all():
            raise ValueError("INVALID_RAW_D1_OHLC")
    bars = d1_asof[["open", "high", "low", "close"]].astype(float)
    if atr_column is not None and (not isinstance(atr_column, str)
                                   or atr_column not in d1_asof.columns):
        raise ValueError("NATIVE_D1_ATR_COLUMN_REQUIRED")
    if ((bars.min(axis=1) <= 0).any()
            or (bars.high < bars[["open", "close", "low"]].max(axis=1)).any()
            or (bars.low > bars[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("INVALID_RAW_D1_OHLC_SHAPE")
    if (not isinstance(trace, dict) or trace.get("status") != "PROXY_VERIFIED"
            or trace.get("original_kind") not in ("resistance", "support")):
        raise ValueError("MIRROR_CHRONOLOGY_NOT_VERIFIED")
    if getattr(level, "kind", None) != "mirror" or getattr(level, "source", None) != "swing_cluster":
        raise ValueError("NOT_EXISTING_SWING_MIRROR")
    if (not isinstance(level.valid_from, date) or level.valid_from > session or
            str(level.valid_from) != trace.get("valid_from")):
        raise ValueError("MIRROR_NOT_FROZEN_AS_OF_SESSION")
    first, last = level.first_idx, level.last_idx
    if (not all(isinstance(n, int) and not isinstance(n, bool) for n in (first, last))
            or not swing_k <= first < last or last + swing_k >= len(bars)):
        raise ValueError("SWING_SOURCE_NOT_CONFIRMED")
    if not isfinite(float(level.price)) or float(level.price) <= 0:
        raise ValueError("BAD_SOFTWARE_LEVEL_PRICE")

    original = trace["original_kind"]
    original_field, mirror_field = (("high", "low") if original == "resistance"
                                    else ("low", "high"))
    confirmed = _confirmed_swings(d1_asof, swing_k)[0 if original == "resistance" else 1]
    valid_swings = {i: (float(price), confirmed_on) for i, price, confirmed_on in confirmed}
    evidence = []
    for label, idx in (("FIRST_SWING", first), ("LAST_SWING", last)):
        if idx not in valid_swings:
            raise ValueError("SOURCE_IS_NOT_CONFIRMED_SWING")
        p = float(bars.iloc[idx][original_field])
        verified_price, confirmed_on = valid_swings[idx]
        if abs(p - verified_price) > max(abs(p), 1.0) * 1e-12:
            raise ValueError("SOURCE_PRICE_MISMATCH")
        if confirmed_on >= session or confirmed_on >= level.valid_from:
            raise ValueError("SOURCE_CONFIRMED_AFTER_LEVEL_IS_VALID")
        # A historical pivot must be confirmed BEFORE it can be reinforced.
        # We do not count its own bar as a second touch.
        from_idx = idx + swing_k + 1
        same, mirror_exact, mirror_pierced = [], [], []
        original_reclaim, mirror_reclaim, mirror_closed_through, mirror_range_cross = [], [], [], []
        original_two_bar, mirror_two_bar = [], []
        wick_reactions = []
        on_grid = _on_current_grid(p, tick)
        # A native tick is used solely for price classification; not for
        # widening an author's level or excusing missing exact BPU1.
        tol = tick * (0.5 + 1e-7)
        for j in range(from_idx, len(bars)):
            v = float(bars.iloc[j][original_field])
            candle = bars.iloc[j]
            role = (original if dates[j] < level.valid_from else
                    ("support" if original == "resistance" else "resistance"))
            raw_atr = d1_asof.iloc[j][atr_column] if atr_column is not None else None
            reaction = _d1_wick_reaction(
                candle, p, tick, role, dates[j], raw_atr, atr_column is not None)
            if reaction is not None:
                wick_reactions.append(reaction)
            # A TWO-CLOSED-D1 reentry is established only after the second
            # bar closes. Keep both bars within the SAME chronological role:
            # old resistance/support or new mirror support/resistance.
            if j > from_idx:
                prev = bars.iloc[j - 1]
                same_old_role = dates[j] < level.valid_from and dates[j - 1] < level.valid_from
                same_mirror_role = dates[j] >= level.valid_from and dates[j - 1] >= level.valid_from
                if original == "resistance":
                    old_reentry = prev.close > p + tol and candle.close < p - tol
                    mirror_reentry = prev.close < p - tol and candle.close > p + tol
                else:
                    old_reentry = prev.close < p - tol and candle.close > p + tol
                    mirror_reentry = prev.close > p + tol and candle.close < p - tol
                if same_old_role and old_reentry:
                    original_two_bar.append(dates[j])
                if same_mirror_role and mirror_reentry:
                    mirror_two_bar.append(dates[j])
            if on_grid and _close_enough(v, p, tick):
                same.append(dates[j])
            if dates[j] < level.valid_from:
                # One-bar rejection of the OLD original support/resistance:
                # wick crosses the old line, close comes back to original side.
                if (original == "resistance"
                        and candle.high > p + tol and candle.close < p - tol
                        or original == "support"
                        and candle.low < p - tol and candle.close > p + tol):
                    original_reclaim.append(dates[j])
                continue
            new_wick = float(candle[mirror_field])
            if on_grid and _close_enough(new_wick, p, tick):
                mirror_exact.append(dates[j])
            if (new_wick < p - tol if original == "resistance"
                    else new_wick > p + tol):
                # This only means the far-side wick price passed the line;
                # *not* that the line failed or that there was a bounce.
                mirror_pierced.append(dates[j])
            if candle.low <= p <= candle.high:
                mirror_range_cross.append(dates[j])
            if original == "resistance":  # new role: support
                if candle.low < p - tol and candle.close > p + tol:
                    mirror_reclaim.append(dates[j])
                if candle.close < p - tol:
                    mirror_closed_through.append(dates[j])
            else:  # old support -> new resistance
                if candle.high > p + tol and candle.close < p - tol:
                    mirror_reclaim.append(dates[j])
                if candle.close > p + tol:
                    mirror_closed_through.append(dates[j])
        evidence.append(BsuSourceEvidence(
            label=label, source_date=dates[idx], confirmed_date=confirmed_on,
            price=p, current_grid="ON_GRID" if on_grid else "OFF_GRID",
            original_same_wick_dates=tuple(same),
            mirror_exact_wick_dates=tuple(mirror_exact),
            mirror_pierce_dates=tuple(mirror_pierced),
            original_wick_reclaim_dates=tuple(original_reclaim),
            mirror_wick_reclaim_dates=tuple(mirror_reclaim),
            mirror_close_through_dates=tuple(mirror_closed_through),
            mirror_range_cross_dates=tuple(mirror_range_cross),
            original_two_bar_reclaim_dates=tuple(original_two_bar),
            mirror_two_bar_reclaim_dates=tuple(mirror_two_bar),
            wick_reactions=tuple(wick_reactions)))
    return tuple(evidence)
