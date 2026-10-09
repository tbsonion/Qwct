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


def detect_levels(d1_asof: pd.DataFrame, cfg: StrategyConfig) -> list[Level]:
    """Уровни по закрытым дневкам. У каждого — valid_from (as-of)."""
    n = len(d1_asof)
    if n < 2 * cfg.swing_k + 5:
        return []
    a = atr(d1_asof, cfg.atr_period)
    tol = float((a * cfg.level_tolerance_atr).median())
    if not np.isfinite(tol) or tol <= 0:
        tol = float(d1_asof["close"].iloc[-1] * 0.005)

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
        av = _aval(a, lvl.first_idx, rng)
        if rng <= cfg.accumulation_range_atr * av:
            score += 2.0
            lvl.formed_by_consolidation = True
            notes.append("сформирован проторговкой")
    for idx in (lvl.first_idx, lvl.last_idx):
        if idx + 1 < len(d1):
            nxt = d1.iloc[idx + 1]
            av = _aval(a, idx + 1, nxt["high"] - nxt["low"])
            if (nxt["high"] - nxt["low"]) >= cfg.big_bar_atr * av:
                score += 1.0
                notes.append("резкий разворот")
                break
    lvl.strength = round(score, 2)
    lvl.notes = notes


def _aval(a: pd.Series, idx: int, fallback: float) -> float:
    v = a.iloc[idx]
    return float(v) if pd.notna(v) and v > 0 else max(float(fallback), 1e-9)


def _mark_mirror(levels: list[Level], d1: pd.DataFrame, cfg: StrategyConfig) -> None:
    for lvl in levels:
        seg = d1.iloc[max(0, lvl.first_idx - cfg.mirror_lookback):lvl.last_idx + 1]
        if len(seg) < 10:
            continue
        crossed = ((seg["high"] > lvl.price) & (seg["low"] < lvl.price)).sum() >= 2
        if crossed:
            lvl.kind = "mirror"


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
