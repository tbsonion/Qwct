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
