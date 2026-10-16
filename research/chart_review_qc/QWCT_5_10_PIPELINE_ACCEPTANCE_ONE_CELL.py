# QWCT 5.10 — paste WHOLE file into ONE NEW CODE CELL, then Run.
# Existing Qwct-M5-Cohort-Research/research.ipynb. Do not replace main.py.
# Fixed four-stock native history sample; no orders, fills or CVD.
# Generated from canonical pure rules by tools/build_qwct_pipeline_cell.py.
from __future__ import annotations
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from QuantConnect.Data.Consolidators import TradeBarConsolidator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time
from collections import Counter
from math import isfinite
from zoneinfo import ZoneInfo
import json
import pandas as pd
import numpy as np
from strategy.config import StrategyConfig
from strategy.levels import Level, levels_for_session, nearest_levels, next_level, native_cluster_tolerance
from strategy.patterns_bsu import Bar, BsuDetector

ET = ZoneInfo("America/New_York")


# Canonical read-only subset: strategy/indicators.py
def atr(df: pd.DataFrame, period: int=14) -> pd.Series:
    col = f'atr{period}'
    if col not in df.columns:
        return pd.Series(float('nan'), index=df.index, dtype=float)
    return df[col].astype(float)

def trend_direction(df: pd.DataFrame, idx: int, cfg: StrategyConfig, bars: int | None=None) -> int:
    bars = bars or cfg.local_trend_bars
    col = f'sma{cfg.trend_sma}'
    if col not in df or idx >= len(df) or idx - bars < 0:
        return 0
    try:
        now = float(df[col].iloc[idx])
        prior = float(df[col].iloc[idx - bars])
        close = float(df['close'].iloc[idx])
    except (TypeError, ValueError, IndexError, KeyError):
        return 0
    if not all((isfinite(v) for v in (now, prior, close))):
        return 0
    if now > prior and close > now:
        return 1
    if now < prior and close < now:
        return -1
    return 0

def global_trend(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> int:
    return trend_direction(df, idx, cfg, bars=cfg.trend_sma // 2)


# Canonical read-only subset: strategy/data.py
def _et(ts: datetime) -> pd.Timestamp:
    value = pd.Timestamp(ts)
    if value.tzinfo is None:
        raise ValueError('as-of timestamp must include a real timezone')
    return value.tz_convert(ET)

@dataclass
class MarketData:
    symbol: str
    d1: pd.DataFrame
    m5: pd.DataFrame | None = None
    session_levels: tuple['Level', ...] | None = None
    breakout_retest: 'BreakoutRetestEvidence | None' = None
    bpu_tvx: 'BpuTvxEvidence | None' = None

    def d1_asof(self, ts: datetime) -> pd.DataFrame:
        current_day = _et(ts).normalize()
        return self.d1.loc[self.d1.index < current_day]

    def m5_asof(self, ts: datetime) -> pd.DataFrame:
        asof = _et(ts)
        if self.m5 is None:
            return pd.DataFrame()
        return self.m5.loc[self.m5.index <= asof]


# Canonical read-only subset: strategy/features.py
@dataclass
class FeatureResult:
    name: str
    value: bool | None
    detail: dict = field(default_factory=dict)
    reason: str = ''

    def bool_or(self, default: bool=False) -> bool:
        return self.value if self.value is not None else default

def _a(d1: pd.DataFrame, cfg: StrategyConfig) -> float:
    v = atr(d1, cfg.atr_period).iloc[-1]
    if pd.isna(v) or not isfinite(float(v)) or v <= 0:
        raise ValueError('Native LEAN ATR is not ready; do not approximate it')
    return float(v)

def _dist(price: float, lvl: float, a: float) -> float:
    return abs(price - lvl) / max(a, 1e-09)

def _dir_to_level(close: float, level_price: float) -> int:
    return 1 if level_price >= close else -1

def g01_squeeze(d1, m5, ts, level: Level, levels, cfg: StrategyConfig) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 6:
        return FeatureResult('g01_squeeze', None, reason='мало баров')
    win = d1.iloc[-6:]
    ranges = win['high'] - win['low']
    contracting = ranges.iloc[-1] <= ranges.iloc[0] * 0.8
    near = _dist(win['close'].iloc[-1], level.price, a) <= 0.5
    d = _dir_to_level(win['close'].iloc[-1], level.price)
    if d > 0:
        struct = all((win['low'].iloc[i] <= win['low'].iloc[i + 1] for i in range(5)))
    else:
        struct = all((win['high'].iloc[i] >= win['high'].iloc[i + 1] for i in range(5)))
    v = contracting and near and struct
    return FeatureResult('g01_squeeze', v, {'contracting': contracting, 'near': near, 'structure': struct, 'last_range_atr': round(ranges.iloc[-1] / a, 2)}, 'поджатие к уровню' if v else '')

def g02_tight_consolidation(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    n = cfg.tight_bars
    if len(d1) < n + 3:
        return FeatureResult('g02_tight_consolidation', None, reason='мало баров')
    win = d1.iloc[-n:]
    rng = win['high'].max() - win['low'].min()
    tight = rng <= cfg.tight_range_atr * a
    near = _dist(win['close'].mean(), level.price, a) <= 0.75
    prev = d1.iloc[-n - 3:-n]
    strong = prev['high'].max() - prev['low'].min() >= cfg.big_bar_atr * a
    pullbacks = sum((1 for i in range(1, len(win)) if abs(win['close'].iloc[i] - win['close'].iloc[i - 1]) > cfg.max_pullback_atr * a))
    no_deep_pullback = pullbacks == 0
    v = tight and near and strong and no_deep_pullback
    return FeatureResult('g02_tight_consolidation', v, {'tight': tight, 'near': near, 'strong_move': strong, 'no_deep_pullback': no_deep_pullback, 'range_atr': round(rng / a, 2)})

def g03_near_retest(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    w = cfg.retest_window
    if len(d1) < w + 1:
        return FeatureResult('g03_near_retest', None, reason='мало баров')
    win = d1.iloc[-w:]
    touched_idx = [i for i in range(len(win)) if win['low'].iloc[i] <= level.price <= win['high'].iloc[i]]
    touched = len(touched_idx) > 0
    pullback = win['high'].max() - win['low'].min() if touched else None
    shallow = pullback is not None and pullback <= 2.0 * a
    three_bar = touched and max(touched_idx) >= len(win) - 3
    gap = False
    if touched:
        for i in touched_idx:
            prev_close = float(d1['close'].iloc[-w + i - 1])
            opening = float(win['open'].iloc[i])
            if abs(opening - prev_close) >= 0.5 * a and abs(opening - level.price) < abs(prev_close - level.price):
                gap = True
                break
    v = bool(touched and shallow)
    return FeatureResult('g03_near_retest', v, {'touched_in_window': touched, 'shallow_pullback': shallow, 'three_bar_retest': three_bar, 'gap_retest': gap, 'pullback_atr': round(pullback / a, 2) if pullback else None})

def g04_accumulation(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    n = cfg.accumulation_bars
    if len(d1) < n:
        return FeatureResult('g04_accumulation', None, reason='мало баров')
    win = d1.iloc[-n:]
    rng = win['high'].max() - win['low'].min()
    v = rng <= cfg.accumulation_range_atr * a and _dist(win['close'].mean(), level.price, a) <= 1.0
    return FeatureResult('g04_accumulation', v, {'range_atr': round(rng / a, 2), 'bars': n})

def g05_no_pullback_after_fp(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 5:
        return FeatureResult('g05_no_pullback_after_fp', None, reason='мало баров')
    had_fp = _simple_false_breakout(d1.iloc[:-1], level)
    if not had_fp:
        return FeatureResult('g05_no_pullback_after_fp', False, {'had_false_breakout': False})
    win = d1.iloc[-3:]
    rng = win['high'].max() - win['low'].min()
    v = rng <= 2 * cfg.max_pullback_atr * a
    return FeatureResult('g05_no_pullback_after_fp', v, {'had_false_breakout': True, 'post_range_atr': round(rng / a, 2)})

def g06_no_pullback_after_impulse(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 7:
        return FeatureResult('g06_no_pullback_after_impulse', None, reason='мало баров')
    pb = d1.iloc[-6]
    is_pb = pb['high'] - pb['low'] >= cfg.paranormal_bar_atr * a
    win = d1.iloc[-5:]
    rng = win['high'].max() - win['low'].min()
    consolidating = rng <= 2 * cfg.tight_range_atr * a
    if m5 is None or len(m5) == 0:
        staircase = None
        sc_reason = 'нет M5 — лесенка недоступна'
    else:
        staircase, sc_reason = (None, 'M5-лесенка: эвристика не реализована (TODO)')
    v = is_pb and consolidating
    return FeatureResult('g06_no_pullback_after_impulse', v, {'paranormal_bar': is_pb, 'consolidating': consolidating, 'm5_staircase': staircase, 'm5_note': sc_reason})

def g07_close_at_extreme(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 2:
        return FeatureResult('g07_close_at_extreme', None, reason='мало баров')
    b = d1.iloc[-1]
    rng = b['high'] - b['low']
    if rng <= 0:
        return FeatureResult('g07_close_at_extreme', False, {})
    near = _dist(b['close'], level.price, a) <= 0.5
    up_tail = b['high'] - max(b['open'], b['close'])
    dn_tail = min(b['open'], b['close']) - b['low']
    closed_high = b['close'] >= b['high'] - 0.15 * rng and up_tail <= cfg.tail_atr * a
    closed_low = b['close'] <= b['low'] + 0.15 * rng and dn_tail <= cfg.tail_atr * a
    impulse = rng >= cfg.big_bar_atr * a
    approach_side = _dir_to_level(float(d1['close'].iloc[-2]), level.price)
    v = near and (approach_side > 0 and closed_high or (approach_side < 0 and closed_low))
    return FeatureResult('g07_close_at_extreme', v, {'near_level': near, 'closed_at_high': closed_high, 'closed_at_low': closed_low, 'impulse': impulse, 'tail_atr': round(min(up_tail, dn_tail) / a, 2)})

def g08_small_bars_approach(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 6:
        return FeatureResult('g08_small_bars_approach', None, reason='мало баров')
    win = d1.iloc[-5:]
    avg_range = (win['high'] - win['low']).mean()
    small = avg_range <= cfg.small_bar_atr * a
    near = _dist(win['close'].iloc[-1], level.price, a) <= 1.0
    trending = abs(win['close'].iloc[-1] - win['close'].iloc[0]) > 0.5 * a
    approaching = _dist(float(win['close'].iloc[-1]), level.price, a) < _dist(float(win['close'].iloc[0]), level.price, a)
    v = small and near and trending and approaching
    return FeatureResult('g08_small_bars_approach', v, {'small_bars': small, 'near': near, 'trending': trending, 'approaching_level': approaching, 'avg_range_atr': round(avg_range / a, 2)})

def g09_context(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < cfg.pullback_free_bars + 2:
        return FeatureResult('g09_context', None, reason='мало баров')
    win5 = d1.iloc[-5:]
    rng5 = win5['high'].max() - win5['low'].min()
    no_along_level_trading = rng5 > cfg.tight_range_atr * a
    d3 = _dist(d1['close'].iloc[-4], level.price, a) - _dist(d1['close'].iloc[-1], level.price, a)
    fast_local_approach = d3 > 1.0
    w = d1.iloc[-cfg.pullback_free_bars:]
    diffs = w['close'].diff().dropna()
    direction = 1 if diffs.sum() > 0 else -1
    pullbacks = sum((1 for x in diffs if x * direction < -cfg.max_pullback_atr * a))
    approaching_level = direction == _dir_to_level(float(w['close'].iloc[0]), level.price) and _dist(float(w['close'].iloc[-1]), level.price, a) < _dist(float(w['close'].iloc[0]), level.price, a)
    long_pullback_free = pullbacks == 0 and approaching_level and (_dist(w['close'].iloc[-1], level.price, a) <= 1.0)
    big = sum((1 for _, b in d1.iloc[-3:].iterrows() if b['high'] - b['low'] >= cfg.big_bar_atr * a))
    big_bars_approach = big >= 3 and _dist(d1['close'].iloc[-1], level.price, a) <= 1.0 and (_dist(d1['close'].iloc[-1], level.price, a) < _dist(d1['close'].iloc[-3], level.price, a))
    _next = next_level
    d = _dir_to_level(d1['close'].iloc[-1], level.price)
    nl = _next(levels, level.price, d)
    clean_zone = abs(nl.price - level.price) > 2.0 * a if nl is not None else None
    room_atr = abs(nl.price - level.price) / a if nl else None
    gt = global_trend(d1, len(d1) - 1, cfg)
    lt = trend_direction(d1, len(d1) - 1, cfg)
    v = no_along_level_trading or fast_local_approach or long_pullback_free
    return FeatureResult('g09_context', v, {'no_along_level_trading': no_along_level_trading, 'fast_local_approach': fast_local_approach, 'long_pullback_free': long_pullback_free, 'approaching_level': approaching_level, 'big_bars_approach': big_bars_approach, 'clean_zone': clean_zone, 'room_atr': round(room_atr, 2) if room_atr else None, 'global_trend': gt, 'local_trend': lt, 'trend_aligned': gt == lt != 0, 'market_aligned': None, 'market_note': 'нет данных индекса — недоступно'})

def g10_htf_distribution(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 15:
        return FeatureResult('g10_htf_distribution', None, reason='мало баров')
    win = d1.iloc[-10:]
    big = sum((1 for _, b in win.iterrows() if b['high'] - b['low'] >= cfg.big_bar_atr * a))
    directed = abs(win['close'].iloc[-1] - win['close'].iloc[0]) >= 2.0 * a
    near = _dist(win['close'].iloc[-1], level.price, a) <= 1.5
    v = big >= 3 and directed and near
    return FeatureResult('g10_htf_distribution', v, {'big_bars': big, 'directed': directed, 'near_level': near, 'm5_exception': None, 'm5_note': 'исключение по M5-лесенке недоступно без M5'})

def g11_missing_impulse(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 4:
        return FeatureResult('g11_missing_impulse', None, reason='мало баров')
    attempted = False
    impulsive = False
    for j in range(len(d1) - 3, len(d1)):
        b = d1.iloc[j]
        crossed = b['high'] > level.price >= d1['close'].iloc[j - 1] or b['low'] < level.price <= d1['close'].iloc[j - 1]
        if crossed:
            attempted = True
            if b['high'] - b['low'] >= cfg.big_bar_atr * a:
                impulsive = True
    v = attempted and (not impulsive)
    return FeatureResult('g11_missing_impulse', v, {'attempted_breakout': attempted, 'had_impulse': impulsive})

def g12_contaminated_zone(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 10:
        return FeatureResult('g12_contaminated_zone', None, reason='мало баров')
    win = d1.iloc[-10:]
    tails = 0
    for _, b in win.iterrows():
        rng = b['high'] - b['low']
        if rng <= 0:
            continue
        tail = max(b['high'] - max(b['open'], b['close']), min(b['open'], b['close']) - b['low'])
        if tail >= 0.4 * rng and abs(b['close'] - level.price) <= 1.5 * a:
            tails += 1
    contaminated = tails >= 4
    acc = g04_accumulation(d1, m5, ts, level, levels, cfg).value
    v = _without_exception(contaminated, acc)
    return FeatureResult('g12_contaminated_zone', v, {'contaminated': contaminated, 'accumulation_exception': acc, 'wick_bars': tails}, 'накопление неизвестно — исключение не проверено' if v is None else '')

def g13_extremum(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 60:
        return FeatureResult('g13_extremum', None, reason='мало баров')
    hist = d1.iloc[-250:]
    hi, lo = (hist['high'].max(), hist['low'].min())
    at_extreme = abs(level.price - hi) <= 0.5 * a or abs(level.price - lo) <= 0.5 * a
    acc = g04_accumulation(d1, m5, ts, level, levels, cfg).value
    v = at_extreme
    return FeatureResult('g13_extremum', v, {'at_extreme': at_extreme, 'has_accumulation': acc, 'needs_energy_note': 'для пробоя экстремума нужно накопление'})

def g14_liquidity_sweep(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 5:
        return FeatureResult('g14_liquidity_sweep', None, reason='мало баров')
    v = False
    detail: dict = {'poke_detected': False, 'returned': False, 'poke_atr': None, 'big_bar_against': None}
    for j in range(max(1, len(d1) - 2), len(d1) - 1):
        prev_close = float(d1['close'].iloc[j - 1])
        b = d1.iloc[j]
        nb = d1.iloc[j + 1]
        up_poke = float(b['high'] - level.price)
        down_poke = float(level.price - b['low'])
        up_sweep = prev_close <= level.price and 0 < up_poke <= 0.5 * a and (float(nb['close']) < level.price)
        down_sweep = prev_close >= level.price and 0 < down_poke <= 0.5 * a and (float(nb['close']) > level.price)
        if up_sweep or down_sweep:
            poke = up_poke if up_sweep else down_poke
            detail['poke_detected'] = True
            detail['poke_atr'] = round(poke / a, 2)
            detail['returned'] = True
            detail['big_bar_against'] = bool(b['high'] - b['low'] >= cfg.big_bar_atr * a)
            v = True
            break
    return FeatureResult('g14_liquidity_sweep', v, detail)

def _simple_false_breakout(d1, level: Level) -> bool:
    for j in range(max(0, len(d1) - 3), len(d1)):
        b = d1.iloc[j]
        if b['high'] > level.price >= b['close'] and b['open'] < level.price or (b['low'] < level.price <= b['close'] and b['open'] > level.price):
            return True
    return False

def _without_exception(observed, exception):
    observed, exception = (_coerce(observed), _coerce(exception))
    if observed is False or exception is True:
        return False
    if observed is None or exception is None:
        return None
    return True
FEATURES = [('g01', g01_squeeze), ('g02', g02_tight_consolidation), ('g03', g03_near_retest), ('g04', g04_accumulation), ('g05', g05_no_pullback_after_fp), ('g06', g06_no_pullback_after_impulse), ('g07', g07_close_at_extreme), ('g08', g08_small_bars_approach), ('g09', g09_context), ('g10', g10_htf_distribution), ('g11', g11_missing_impulse), ('g12', g12_contaminated_zone), ('g13', g13_extremum), ('g14', g14_liquidity_sweep)]

def _coerce(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    raise ValueError('FEATURE_BOOLEAN_OR_NONE_REQUIRED')

def evaluate_all(d1: pd.DataFrame, m5: pd.DataFrame | None, ts: datetime, level: Level, levels: list[Level], cfg: StrategyConfig) -> dict[str, FeatureResult]:
    out: dict[str, FeatureResult] = {}
    for name, fn in FEATURES:
        try:
            fr = fn(d1, m5, ts, level, levels, cfg)
            fr.value = _coerce(fr.value)
            out[name] = fr
        except Exception as e:
            out[name] = FeatureResult(name, None, reason=f'ошибка: {e}')
    return out


# Canonical read-only subset: strategy/scenarios.py
@dataclass
class ModelScore:
    model: str
    side: str
    score: float
    positives: list[str] = field(default_factory=list)

@dataclass
class ScenarioDecision:
    symbol: str
    session: date
    decided_at: datetime
    level: Level | None
    model: str | None
    side: str | None
    score: float = 0.0
    positives: list[str] = field(default_factory=list)
    features: dict[str, FeatureResult] = field(default_factory=dict)
    rejected_reasons: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.model is not None

    def feature_map(self) -> dict[str, bool | None]:
        return {gid: fr.value for gid, fr in self.features.items()}

def _score_breakout(feats: dict[str, FeatureResult], cfg: StrategyConfig) -> tuple[float, list[str]]:
    total, prov = (0.0, [])
    for gid, w in cfg.breakout_weights.items():
        fr = feats.get(gid)
        if fr is not None and fr.value is True:
            total += w
            prov.append(gid)
    g03 = feats.get('g03')
    if g03 is not None and g03.value is True:
        if g03.detail.get('three_bar_retest'):
            total += 0.5
            prov.append('g03.three_bar_retest')
        if g03.detail.get('gap_retest'):
            total += 0.5
            prov.append('g03.gap_retest')
    return (round(total, 2), prov)

def _score_bounce(feats: dict[str, FeatureResult], cfg: StrategyConfig) -> tuple[float, list[str]]:
    total, prov = (0.0, [])
    g09 = feats.get('g09')
    if g09 is not None and g09.detail.get('long_pullback_free'):
        total += cfg.bounce_weights['g09.long_pullback_free']
        prov.append('g09.long_pullback_free')
    if g09 is not None and g09.detail.get('big_bars_approach'):
        total += cfg.bounce_weights['g09.big_bars_approach']
        prov.append('g09.big_bars_approach')
    g12 = feats.get('g12')
    if g12 is not None and g12.value is True:
        total += cfg.bounce_weights['g12']
        prov.append('g12')
    g13 = feats.get('g13')
    if g13 is not None and g13.value is True:
        total += cfg.bounce_weights['g13']
        prov.append('g13')
    return (round(total, 2), prov)

def _score_false_breakout(feats: dict[str, FeatureResult], cfg: StrategyConfig) -> tuple[float, list[str]]:
    total, prov = (0.0, [])
    for gid, w in cfg.false_breakout_weights.items():
        fr = feats.get(gid)
        if fr is not None and fr.value is True:
            total += w
            prov.append(gid)
    return (round(total, 2), prov)

class ScenarioEvaluator:

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self.scan_model_audit = Counter()

    def evaluate(self, symbol: str, session: date, decided_at: datetime, d1_asof: pd.DataFrame, m5_asof: pd.DataFrame | None, levels: list[Level]) -> ScenarioDecision:
        cfg = self.cfg
        if d1_asof.empty:
            return ScenarioDecision(symbol, session, decided_at, None, None, None, rejected_reasons=['нет данных D1'])
        price = float(d1_asof['close'].iloc[-1])
        a = _atr_value(d1_asof, cfg)
        cands = nearest_levels(levels, price, cfg.level_proximity_atr, a)
        if not cands:
            self.scan_model_audit['no_nearby'] += 1
            return ScenarioDecision(symbol, session, decided_at, None, None, None, rejected_reasons=['нет уровней рядом с ценой'])
        best_bounce = None
        has_eligible_bsu_level = False
        best: ModelScore | None = None
        best_level: Level | None = None
        best_feats: dict[str, FeatureResult] = {}
        rejected: list[str] = []
        for lvl in cands:
            feats = evaluate_all(d1_asof, m5_asof, decided_at, lvl, levels, cfg)
            feature_errors = [f'{gid}: {fr.reason}' for gid, fr in feats.items() if fr.reason.startswith('ошибка:')]
            if feature_errors:
                rejected.append(f'feature calculation failed @{lvl.price:.2f}: ' + '; '.join(feature_errors)[:500])
                continue
            s_br, p_br = _score_breakout(feats, cfg)
            side_br = 'long' if lvl.price >= price else 'short'
            s_bo, p_bo = _score_bounce(feats, cfg)
            side_bo = 'short' if lvl.price >= price else 'long'
            if lvl.kind in ('support', 'resistance') and lvl.source == 'swing_cluster' and (lvl.valid_from is not None) and (lvl.valid_from <= session) and (lvl.formed_at is not None) and (lvl.touches >= cfg.min_touches) and (lvl.strength >= cfg.min_level_strength):
                has_eligible_bsu_level = True
                best_bounce = s_bo if best_bounce is None else max(best_bounce, s_bo)
            s_fp, p_fp = _score_false_breakout(feats, cfg)
            g14 = feats.get('g14')
            side_fp = 'short' if lvl.price >= price else 'long'
            for model, side, score, prov in (('breakout', side_br, s_br, p_br), ('bounce', side_bo, s_bo, p_bo), ('false_breakout', side_fp, s_fp, p_fp)):
                if score < cfg.min_model_score:
                    rejected.append(f'{model}@{lvl.price:.2f}: скор {score} < {cfg.min_model_score}')
                    continue
                if best is None or score > best.score:
                    best = ModelScore(model, side, score, prov)
                    best_level = lvl
                    best_feats = feats
        audit = self.scan_model_audit
        audit['nearby_evaluated'] += 1
        if has_eligible_bsu_level:
            audit['bsu_level_present'] += 1
            if best_bounce is not None and best_bounce >= cfg.min_model_score:
                audit['bounce_scored_eligible'] += 1
                if best is not None and best.model != 'bounce':
                    audit['bounce_outscored'] += 1
                    if abs(best.score - best_bounce) < 1e-08:
                        audit['bounce_tie_lost'] += 1
            else:
                audit['bounce_below_threshold'] += 1
        else:
            audit['no_bsu_eligible_level'] += 1
        if best is not None and best.model == 'bounce':
            audit['selected_bounce'] += 1
        if best is None or best_level is None:
            return ScenarioDecision(symbol, session, decided_at, None, None, None, features=best_feats, rejected_reasons=rejected)
        return ScenarioDecision(symbol, session, decided_at, best_level, best.model, best.side, best.score, best.positives, best_feats, rejected)

def _atr_value(d1: pd.DataFrame, cfg: StrategyConfig) -> float:
    v = atr(d1, cfg.atr_period).iloc[-1]
    if pd.isna(v) or not isfinite(float(v)) or v <= 0:
        raise ValueError('Native LEAN ATR is not ready')
    return float(v)


# Canonical read-only subset: strategy/breakout_retest.py
M5 = timedelta(minutes=5)
TERMINAL = ('CONFIRMED', 'EXPIRED', 'INVALIDATED')

@dataclass(frozen=True)
class BreakoutRetestEvidence:
    symbol: str
    session: date
    side: str
    level_price: float
    phase: str
    breakout_at: datetime | None
    retest_at: datetime | None
    confirmed_at: datetime | None
    reason: str
    can_submit: bool = False

    def matches(self, *, symbol, session, side, level_price, observed_at):
        return self.can_submit is False and self.phase == 'CONFIRMED' and (self.symbol == symbol) and (self.session == session) and (self.side == side) and isfinite(float(level_price)) and (abs(self.level_price - float(level_price)) < 1e-08) and (self.breakout_at is not None) and (self.retest_at is not None) and (self.confirmed_at is not None) and (self.breakout_at < self.retest_at < self.confirmed_at) and (self.confirmed_at == observed_at) and (observed_at.date() == session)

class BreakoutRetestObserver:

    def __init__(self, *, symbol: str, session: date, side: str, level_price: float, atr_value: float, max_confirm_chase_atr: float, max_retest_bars: int=8, retest_tolerance_atr: float=0.2, invalidation_atr: float=0.5):
        if not symbol or not isinstance(session, date) or side not in ('long', 'short'):
            raise ValueError('confirmed symbol/session/side required')
        for name, value in (('level', level_price), ('native D1 ATR', atr_value), ('no-chase ATR', max_confirm_chase_atr)):
            if isinstance(value, bool) or not isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f'{name} must be positive and finite')
        if type(max_retest_bars) is not int or not 1 <= max_retest_bars <= 80:
            raise ValueError('native M5 retest limit must be 1..80 bars')
        for name, value in (('retest tolerance', retest_tolerance_atr), ('invalidation buffer', invalidation_atr)):
            if isinstance(value, bool) or not isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f'{name} must be positive and finite')
        self.retest_bars = max_retest_bars
        self.retest_tolerance = float(retest_tolerance_atr)
        self.invalidation = float(invalidation_atr)
        self.symbol = symbol
        self.session = session
        self.side = side
        self.level = float(level_price)
        self.atr = float(atr_value)
        self.chase = float(max_confirm_chase_atr)
        self.phase = 'WATCH_BREAKOUT'
        self.reason = 'awaiting native M5 close crossing preselected D1 level'
        self.breakout_at = None
        self.retest_at = None
        self.confirmed_at = None
        self._last_time = None
        self._last_close = None
        self._after_breakout = 0
        self._retest_extreme = None

    @property
    def evidence(self) -> BreakoutRetestEvidence:
        return BreakoutRetestEvidence(self.symbol, self.session, self.side, self.level, self.phase, self.breakout_at, self.retest_at, self.confirmed_at, self.reason)

    def _stop(self, phase, reason):
        self.phase, self.reason = (phase, reason)
        return self.evidence

    def on_m5(self, *, at: datetime, open_price: float, high: float, low: float, close: float, volume: float) -> BreakoutRetestEvidence:
        if self.phase in TERMINAL:
            return self.evidence
        if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None or (at.date() != self.session) or at.second or at.microsecond or at.minute % 5:
            return self._stop('INVALIDATED', 'M5_SESSION_OR_CLOCK_INVALID')
        vals = (open_price, high, low, close, volume)
        try:
            o, h, l, c, v = tuple((float(x) for x in vals))
        except (TypeError, ValueError, OverflowError):
            return self._stop('INVALIDATED', 'M5_NUMERIC_INVALID')
        if not all((isfinite(x) for x in (o, h, l, c, v))) or min(o, h, l, c) <= 0 or v <= 0 or (h < max(o, c, l)) or (l > min(o, c, h)):
            return self._stop('INVALIDATED', 'M5_OHLCV_INVALID')
        if self._last_time is not None and (at <= self._last_time or at - self._last_time != M5):
            return self._stop('INVALIDATED', 'M5_GAP_DUPLICATE_OR_LATE')
        previous = self._last_close
        self._last_time, self._last_close = (at, c)
        bullish = self.side == 'long'
        level = self.level
        if self.phase == 'WATCH_BREAKOUT':
            if previous is not None and (bullish and previous <= level < c or (not bullish and previous >= level > c)):
                self.breakout_at = at
                self._after_breakout = 0
                return self._stop('WAIT_RETEST', 'M5_BREAKOUT_CLOSED_WAIT_RETEST')
            return self.evidence
        if self.phase == 'WAIT_RETEST':
            self._after_breakout += 1
            if self._after_breakout > self.retest_bars:
                return self._stop('EXPIRED', 'RETEST_NOT_SEEN_WITHIN_M5_WINDOW')
            if bullish and c < level - self.invalidation * self.atr or (not bullish and c > level + self.invalidation * self.atr):
                return self._stop('INVALIDATED', 'CLOSED_BEYOND_LOSS_SIDE')
            close_holds = c >= level if bullish else c <= level
            near = l <= level + self.retest_tolerance * self.atr if bullish else h >= level - self.retest_tolerance * self.atr
            if near and close_holds:
                self.retest_at = at
                self._retest_extreme = h if bullish else l
                return self._stop('WAIT_CONFIRMATION', 'M5_RETEST_HELD_WAIT_NEXT_BAR')
            return self.evidence
        if self.phase == 'WAIT_CONFIRMATION':
            if bullish and c < level - self.invalidation * self.atr or (not bullish and c > level + self.invalidation * self.atr):
                return self._stop('INVALIDATED', 'CONFIRM_LOST_LEVEL')
            confirmed = bullish and c > self._retest_extreme and (c > o) or (not bullish and c < self._retest_extreme and (c < o))
            if not confirmed:
                return self._stop('INVALIDATED', 'NEXT_M5_DID_NOT_CONFIRM')
            if abs(c - level) > self.chase * self.atr:
                return self._stop('INVALIDATED', 'CONFIRM_OVEREXTENDED_NO_CHASE')
            self.confirmed_at = at
            return self._stop('CONFIRMED', 'BREAKOUT_RETEST_CONFIRMATION_M5_RESEARCH_ONLY')
        return self._stop('INVALIDATED', 'UNKNOWN_RESEARCH_PHASE')


# Canonical read-only subset: strategy/bpu_tvx_evidence.py
@dataclass(frozen=True)
class BpuTvxEvidence:
    symbol: str
    session: date
    side: str
    d1_level_price: float
    native_origin_price: float
    native_tick_size: float
    entry_price: float
    stop_price: float
    preclose_last_price: float
    bpu1_end: datetime
    preclose_at: datetime
    bpu2_end: datetime
    origin_provenance: str
    can_submit: bool = False

    def matches(self, *, symbol, session, side, level_price, observed_at):
        dates = (self.bpu1_end, self.preclose_at, self.bpu2_end, observed_at)
        try:
            return self.can_submit is False and self.symbol == symbol and (self.session == session) and (self.side == side) and (self.origin_provenance == 'D1_CONFIRMED_SWING_PROXY_NOT_CANONICAL_BSU') and all((isinstance(t, datetime) and t.tzinfo is not None and (t.utcoffset() is not None) for t in dates)) and all((isfinite(float(p)) and float(p) > 0 for p in (level_price, self.d1_level_price, self.native_origin_price, self.native_tick_size, self.entry_price, self.stop_price, self.preclose_last_price))) and (self.stop_price < self.native_origin_price < self.entry_price if self.side == 'long' else self.entry_price < self.native_origin_price < self.stop_price) and (abs(abs(self.entry_price - self.native_origin_price) - 0.2 * abs(self.native_origin_price - self.stop_price)) <= self.native_tick_size * 0.5 + 1e-08) and (abs(self.d1_level_price - float(level_price)) < 1e-08) and (abs(self.native_origin_price - self.d1_level_price) <= self.native_tick_size * 0.5 + 1e-08) and (abs(round(self.native_origin_price / self.native_tick_size) * self.native_tick_size - self.native_origin_price) <= self.native_tick_size * 1e-05) and all((abs(round(p / self.native_tick_size) * self.native_tick_size - p) <= self.native_tick_size * 1e-05 for p in (self.entry_price, self.stop_price))) and (self.bpu1_end + timedelta(minutes=5) == self.bpu2_end) and (self.preclose_at == self.bpu2_end - timedelta(seconds=30)) and (observed_at == self.bpu2_end) and (self.bpu2_end.date() == session)
        except (ValueError, TypeError, OverflowError):
            return False


# Canonical read-only subset: strategy/signals.py
GATE_IDS = ('trend_aligned', 'daily_level_valid', 'm5_confirmed', 'stop_behind_d1_level', 'room_at_least_4r', 'target_at_least_3r', 'risk_approved', 'matching_trade_model')

@dataclass
class GateResult:
    id: str
    passed: bool | None
    reason: str = ''

@dataclass
class TradeIntent:
    symbol: str
    session: date
    signal_at: datetime
    side: str
    model: str
    level_price: float
    limit_price: float
    stop_price: float
    risk_per_share: float
    shares: int
    tp_r: float
    room_r: float | None
    atr: float | None = None
    gates: dict[str, GateResult] = field(default_factory=dict)
    features: dict[str, bool | None] = field(default_factory=dict)
    positives: list[str] = field(default_factory=list)

    @property
    def all_gates_passed(self) -> bool:
        return set(self.gates) == set(GATE_IDS) and all((self.gates[key].passed is True for key in GATE_IDS))

    def gate_map(self) -> dict[str, bool | None]:
        return {gid: self.gates[gid].passed for gid in GATE_IDS}

def _direction(side: str) -> int:
    return 1 if side == 'long' else -1 if side == 'short' else 0

def _gate(id: str, passed, reason: str='') -> GateResult:
    if passed is None:
        return GateResult(id, None, reason)
    return GateResult(id, bool(passed), reason)

def evaluate_gates(intent: TradeIntent, decision: ScenarioDecision, market: MarketData, ts: datetime, cfg: StrategyConfig, equity: float=25000.0, risk_mgr=None) -> dict[str, GateResult]:
    gates: dict[str, GateResult] = {}
    d1 = market.d1_asof(ts)
    m5 = market.m5_asof(ts)
    lvl = decision.level
    side, model = (intent.side, intent.model)
    dirn = _direction(side) if side else 0
    native_bounce = model == 'bounce' and type(market.bpu_tvx) is BpuTvxEvidence and (lvl is not None) and market.bpu_tvx.matches(symbol=market.symbol, session=decision.session, side=side, level_price=lvl.price, observed_at=ts)
    if d1.empty or lvl is None or dirn == 0:
        gates['trend_aligned'] = _gate('trend_aligned', None, 'нет данных')
    elif cfg.allow_countertrend:
        g = global_trend(d1, len(d1) - 1, cfg)
        l = trend_direction(d1, len(d1) - 1, cfg)
        gates['trend_aligned'] = _gate('trend_aligned', None, f'UNVERIFIED countertrend experiment: global={g} local={l} side={side}; canonical mandatory trend alignment not met')
    else:
        g = global_trend(d1, len(d1) - 1, cfg)
        l = trend_direction(d1, len(d1) - 1, cfg)
        ok = g == l == dirn and g != 0
        gates['trend_aligned'] = _gate('trend_aligned', ok, f'global={g} local={l} side={side}')
    if lvl is None:
        gates['daily_level_valid'] = _gate('daily_level_valid', None, 'нет уровня')
    else:
        ok = lvl.strength >= cfg.min_level_strength and lvl.touches >= cfg.min_touches and (lvl.valid_from is not None) and (lvl.valid_from <= decision.session)
        gates['daily_level_valid'] = _gate('daily_level_valid', ok, f'strength={lvl.strength} touches={lvl.touches} valid_from={lvl.valid_from}')
    if model == 'breakout':
        evidence = market.breakout_retest
        verified = type(evidence) is BreakoutRetestEvidence and lvl is not None and evidence.matches(symbol=market.symbol, session=decision.session, side=side, level_price=lvl.price, observed_at=ts) and (m5 is not None) and (not m5.empty) and isinstance(m5.index, pd.DatetimeIndex) and (m5.index.tz is not None) and (pd.Timestamp(m5.index[-1]) == pd.Timestamp(ts))
        gates['m5_confirmed'] = _gate('m5_confirmed', verified, 'three distinct observed native closed M5 phases' if verified else 'no matching closed breakout/retest/confirmation evidence')
    elif model == 'bounce':
        evidence = market.bpu_tvx
        verified = native_bounce and m5 is not None and (len(m5) >= 2) and isinstance(m5.index, pd.DatetimeIndex) and (m5.index.tz is not None) and (pd.Timestamp(m5.index[-1]) == pd.Timestamp(ts)) and (pd.Timestamp(m5.index[-2]) == pd.Timestamp(evidence.bpu1_end))
        gates['m5_confirmed'] = _gate('m5_confirmed', verified, 'D1 swing proxy + exact BPU1 + native SEC -30s + closed BPU2' if verified else 'two-bar bounce proxy is insufficient: missing native BPU/TVX')
    else:
        gates['m5_confirmed'] = _check_m5(m5, lvl, side, model, cfg, ts)
    if gates['m5_confirmed'].passed is True and lvl is not None:
        native_a = _atr(d1, cfg)
        if native_a is None:
            gates['m5_confirmed'] = _gate('m5_confirmed', None, 'native D1 ATR missing')
        elif abs((market.bpu_tvx.preclose_last_price if native_bounce else float(m5['close'].iloc[-1])) - lvl.price) > cfg.max_entry_distance_atr * native_a:
            gates['m5_confirmed'] = _gate('m5_confirmed', False, 'M5 level proximity exceeded no-chase ATR limit')
    stop, limit = (None, None)
    if native_bounce:
        stop, limit = (market.bpu_tvx.stop_price, market.bpu_tvx.entry_price)
    elif lvl is not None and dirn != 0:
        a = _atr(d1, cfg)
        if a is None:
            pass
        else:
            buf = cfg.stop_buffer_atr * a
            stop = lvl.price - dirn * buf
            limit = _limit_price(model, side, lvl, m5)
    if stop is None or limit is None or lvl is None or (dirn == 0):
        gates['stop_behind_d1_level'] = _gate('stop_behind_d1_level', None, 'нет цен')
    else:
        level_ok = dirn * (lvl.price - stop) > 0
        entry_ok = dirn * (limit - stop) > 0
        valid = level_ok and entry_ok and all((isfinite(v) and v > 0 for v in (limit, stop)))
        gates['stop_behind_d1_level'] = _gate('stop_behind_d1_level', valid, f'stop={stop:.2f} level={lvl.price:.2f} entry={limit:.2f} loss_side={entry_ok}')
    risk_ps, room_r = (None, None)
    if stop is not None and limit is not None and (lvl is not None):
        risk_ps = dirn * (limit - stop)
        if risk_ps > 0:
            nl = next_level(_session_levels(market, ts, cfg, decision.session), limit, dirn)
            if nl is None:
                gates['room_at_least_4r'] = _gate('room_at_least_4r', False, 'нет следующего уровня — запас хода неизвестен')
            else:
                room_r = abs(nl.price - limit) / risk_ps
                gates['room_at_least_4r'] = _gate('room_at_least_4r', room_r >= cfg.min_room_r, f'room={room_r:.1f}R next={nl.price:.2f}')
        else:
            gates['room_at_least_4r'] = _gate('room_at_least_4r', False, 'риск=0')
    else:
        gates['room_at_least_4r'] = _gate('room_at_least_4r', None, 'нет цен')
    if limit is None or stop is None or dirn == 0 or (risk_ps is None) or (risk_ps <= 0):
        gates['target_at_least_3r'] = _gate('target_at_least_3r', False, 'нет допустимого входа/стопа')
    else:
        target = limit + dirn * cfg.tp_r * risk_ps
        valid_target = isfinite(target) and target > 0 and isfinite(cfg.tp_r) and (cfg.tp_r >= cfg.min_rr) and (dirn * (target - limit) >= cfg.min_rr * risk_ps)
        gates['target_at_least_3r'] = _gate('target_at_least_3r', valid_target, f'entry={limit:.2f} stop={stop:.2f} target={target:.2f} TP={cfg.tp_r}R')
    if risk_mgr is not None:
        gates['risk_approved'] = _gate('risk_approved', None, 'UNVERIFIED external risk manager; only native LEAN evidence accepted')
    elif risk_ps and risk_ps > 0 and limit:
        risk_money = equity * cfg.risk_per_trade_pct / 100
        shares = int(risk_money // risk_ps)
        affordable = shares > 0 and shares * limit <= equity
        gates['risk_approved'] = _gate('risk_approved', None, f'UNVERIFIED PRELIMINARY shares={shares}, planned risk USD={risk_money:.2f}, cash-fit={affordable}; no native risk approval')
    else:
        gates['risk_approved'] = _gate('risk_approved', None, 'нет данных')
    ok_model = model in ('breakout', 'bounce', 'false_breakout') and side in ('long', 'short')
    gates['matching_trade_model'] = _gate('matching_trade_model', ok_model, f'model={model} side={side}')
    return gates

def _check_m5(m5: pd.DataFrame, lvl: Level | None, side: str | None, model: str | None, cfg: StrategyConfig, ts: datetime) -> GateResult:
    if m5 is None or len(m5) < 2 or lvl is None or (side not in ('long', 'short')):
        return _gate('m5_confirmed', False, 'нужны две закрытые M5 свечи')
    if not isinstance(m5.index, pd.DatetimeIndex) or m5.index.tz is None:
        return _gate('m5_confirmed', False, 'время M5 не подтверждено')
    if m5.index[-1] - m5.index[-2] != pd.Timedelta(minutes=5):
        return _gate('m5_confirmed', False, 'пропущенный M5 бар')
    if pd.Timestamp(m5.index[-1]) != pd.Timestamp(ts):
        return _gate('m5_confirmed', False, 'несовпадение времени M5')
    prev, last = (m5.iloc[-2], m5.iloc[-1])
    try:
        for bar in (prev, last):
            o, h, l, cl = (float(bar[k]) for k in ('open', 'high', 'low', 'close'))
            if not all((isfinite(v) and v > 0 for v in (o, h, l, cl))) or h < max(o, cl, l) or l > min(o, cl, h):
                return _gate('m5_confirmed', False, 'некорректный OHLC M5')
    except (KeyError, ValueError, TypeError, OverflowError):
        return _gate('m5_confirmed', False, 'нет OHLC M5')
    price = lvl.price
    if model == 'breakout':
        ok = prev['close'] <= price < last['close'] if side == 'long' else prev['close'] >= price > last['close']
        return _gate('m5_confirmed', ok, 'M5 новый переход уровня' if ok else 'M5 закрытие по сторону уровня без нового пробоя')
    if model == 'bounce':
        touched = last['low'] <= price <= last['high']
        same_side = prev['close'] > price and last['close'] > price if side == 'long' else prev['close'] < price and last['close'] < price
        ok = touched and same_side
        return _gate('m5_confirmed', ok, f'two-bar touch={touched} return_side={same_side}; полная BSU/BPU модель не подтверждена')
    if model == 'false_breakout':
        ok = prev['close'] <= price and last['high'] > price >= last['close'] if side == 'short' else prev['close'] >= price and last['low'] < price <= last['close']
        return _gate('m5_confirmed', ok, 'M5 прокол и возврат' if ok else 'M5 простой ЛП не подтверждён')
    return _gate('m5_confirmed', None, f'неизвестная модель {model}')

def _limit_price(model: str | None, side: str, lvl: Level, m5: pd.DataFrame) -> float:
    if model == 'breakout' and m5 is not None and (not m5.empty):
        return float(m5['close'].iloc[-1])
    return float(lvl.price)

def _atr(d1: pd.DataFrame, cfg: StrategyConfig) -> float | None:
    if d1 is None or d1.empty or len(d1) < cfg.atr_period + 1:
        return None
    v = atr(d1, cfg.atr_period).iloc[-1]
    if pd.isna(v) or not isfinite(float(v)) or v <= 0:
        return None
    return float(v)

def _session_levels(market: MarketData, ts: datetime, cfg: StrategyConfig, session: date) -> tuple[Level, ...]:
    if market.session_levels is not None:
        return tuple((level for level in market.session_levels if level.valid_from is not None and level.valid_from <= session))
    return tuple(levels_for_session(market.d1_asof(ts), session, cfg))

def build_intent(decision: ScenarioDecision, market: MarketData, ts: datetime, cfg: StrategyConfig, equity: float=25000.0, risk_mgr=None) -> TradeIntent | None:
    if not decision.accepted:
        return None
    d1 = market.d1_asof(ts)
    a = _atr(d1, cfg)
    if a is None:
        return None
    lvl = decision.level
    dirn = _direction(decision.side)
    buf = cfg.stop_buffer_atr * a
    stop = lvl.price - dirn * buf
    m5 = market.m5_asof(ts)
    limit = _limit_price(decision.model, decision.side, lvl, m5)
    evidence = market.bpu_tvx
    if decision.model == 'bounce' and type(evidence) is BpuTvxEvidence and evidence.matches(symbol=market.symbol, session=decision.session, side=decision.side, level_price=lvl.price, observed_at=ts):
        limit, stop = (evidence.entry_price, evidence.stop_price)
    risk_ps = max(0.0, dirn * (limit - stop))
    risk_money = equity * cfg.risk_per_trade_pct / 100
    shares = int(risk_money // risk_ps) if risk_ps > 0 else 0
    intent = TradeIntent(symbol=decision.symbol, session=decision.session, signal_at=ts, side=decision.side, model=decision.model, level_price=lvl.price, limit_price=limit, stop_price=stop, risk_per_share=risk_ps, shares=shares, tp_r=cfg.tp_r, room_r=None, atr=a, gates={}, features=decision.feature_map(), positives=decision.positives)
    intent.gates = evaluate_gates(intent, decision, market, ts, cfg, equity, risk_mgr)
    rg = intent.gates['room_at_least_4r']
    if rg.passed and 'room=' in rg.reason:
        try:
            intent.room_r = float(rg.reason.split('room=')[1].split('R')[0])
        except (ValueError, IndexError):
            intent.room_r = None
    return intent


# Canonical read-only subset: strategy/patterns_bsu.py
def _positive(name: str, value: float) -> float:
    try:
        parsed = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f'{name} must be a positive finite number') from None
    if not isfinite(parsed) or parsed <= 0:
        raise ValueError(f'{name} must be a positive finite number')
    return parsed

@dataclass(frozen=True)
class FixedFloatingEvidence:
    status: str
    price: float
    side: str
    hits: int
    adverse_pierces: int
    source_end: datetime | None
    last_end: datetime | None
    reason: str

    @property
    def can_trade(self) -> bool:
        return False

class FixedFloatingLimitObserver:

    def __init__(self, price: float, side: str, tick_size: float, min_hits: int=3):
        self.price = _positive('level_price', price)
        self.tick = _positive('tick_size', tick_size)
        if side not in ('long', 'short'):
            raise ValueError('FIXED_LEVEL_SIDE_INVALID')
        if not isinstance(min_hits, int) or min_hits < 3:
            raise ValueError('FIXED_LEVEL_MIN_HITS_INVALID')
        if abs(self.price / self.tick - round(self.price / self.tick)) > 1e-06:
            raise ValueError('FIXED_LEVEL_OFF_NATIVE_TICK')
        self.side = side
        self.min_hits = min_hits
        self._last: datetime | None = None
        self._first_hit: datetime | None = None
        self._hits = 0
        self._pierces = 0

    def observe(self, bar: Bar) -> FixedFloatingEvidence:
        if not isinstance(bar, Bar) or bar.timeframe != 'M5':
            raise ValueError('FIXED_LEVEL_REQUIRES_NATIVE_M5')
        now = BsuDetector._validate_bar(bar)
        if self._last is not None and now <= self._last:
            raise ValueError('FIXED_LEVEL_OUT_OF_ORDER')
        gap = self._last is not None and now - self._last != timedelta(minutes=5)
        if gap:
            self._first_hit = None
            self._hits = 0
            self._pierces = 0
        extreme = float(bar.low if self.side == 'long' else bar.high)
        tol = self.tick * 1e-06
        if extreme < self.price - tol if self.side == 'long' else extreme > self.price + tol:
            if self._hits:
                self._pierces += 1
        elif abs(extreme - self.price) <= tol:
            if self._first_hit is None:
                self._first_hit = bar.ts
            self._hits += 1
        self._last = now
        if self._pierces:
            status, reason = ('FLOATING_ZONE', 'LIMIT_LEVEL_PIERCED')
        elif self._hits >= self.min_hits:
            status, reason = ('FIXED_LIMIT_CANDIDATE', 'EXACT_UNPIERCED_HITS')
        else:
            status, reason = ('INDETERMINATE', 'INSUFFICIENT_EXACT_HITS')
        if gap:
            reason += '_AFTER_M5_GAP_RESET'
        return FixedFloatingEvidence(status, self.price, self.side, self._hits, self._pierces, self._first_hit, bar.ts, reason)


# Canonical read-only subset: strategy/bsu_bridge.py
@dataclass(frozen=True)
class BsuResearchLink:
    detector: BsuDetector
    origin_time: datetime
    tick_size: float
    cluster_price: float
    origin_price: float
    provenance: str = 'D1_CONFIRMED_SWING_PROXY_NOT_CANONICAL_BSU'

@dataclass(frozen=True)
class RawBsuEvidence:
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

def create_bsu_research_observer(decision: ScenarioDecision, d1_asof: pd.DataFrame, native_tick_size: float | None, cfg: StrategyConfig, *, raw_evidence: RawBsuEvidence | None=None, require_raw: bool=False) -> tuple[BsuResearchLink | None, str]:
    if decision is None or not decision.accepted or decision.model != 'bounce':
        return (None, 'not an accepted D1 bounce scenario')
    lvl = decision.level
    if lvl is None or (lvl.kind, decision.side) not in (('support', 'long'), ('resistance', 'short')):
        return (None, 'D1 bounce level kind/side mismatch (mirror not assumed)')
    if lvl.source != 'swing_cluster':
        return (None, 'no traced D1 swing_cluster origin')
    if lvl.valid_from is None or lvl.valid_from > decision.session or lvl.formed_at is None or (lvl.touches < cfg.min_touches) or (lvl.strength < cfg.min_level_strength):
        return (None, 'D1 level not confirmed as of the session')
    try:
        tick = float(native_tick_size)
        if not isfinite(tick) or tick <= 0:
            return (None, 'native LEAN minimum tick size missing')
    except (TypeError, ValueError, OverflowError):
        return (None, 'native LEAN minimum tick size missing')
    if d1_asof is None or d1_asof.empty or (not isinstance(d1_asof.index, pd.DatetimeIndex)) or (d1_asof.index.tz is None) or (not d1_asof.index.is_monotonic_increasing) or (not d1_asof.index.is_unique):
        return (None, 'invalid native closed D1 chronology')
    if any((day.date() >= decision.session for day in d1_asof.index)):
        return (None, 'D1 source includes unclosed/current session')
    if 'bar_end' not in d1_asof.columns:
        return (None, 'missing native D1 bar_end timestamps')
    if lvl.first_idx < 0 or lvl.last_idx <= lvl.first_idx or lvl.last_idx >= len(d1_asof):
        return (None, 'invalid D1 swing indices')
    if d1_asof.index[lvl.last_idx].date() != lvl.formed_at:
        return (None, 'D1 swing formation does not match original source')
    try:
        origin_end = pd.Timestamp(d1_asof.iloc[lvl.first_idx]['bar_end'])
        newest_end = pd.Timestamp(d1_asof.iloc[-1]['bar_end'])
        decided_at = pd.Timestamp(decision.decided_at)
        if origin_end.tzinfo is None or newest_end.tzinfo is None or decided_at.tzinfo is None or pd.isna(origin_end) or pd.isna(newest_end):
            return (None, 'native D1 bar_end has no valid timezone')
        if not origin_end < newest_end < decided_at:
            return (None, 'native D1 source originates after morning decision')
        if d1_asof.index[lvl.first_idx].date() >= decision.session:
            return (None, 'historical origin not closed before session')
        scaled_origin = float(d1_asof.iloc[lvl.first_idx]['low' if lvl.kind == 'support' else 'high'])
        if require_raw and raw_evidence is None:
            return (None, 'native RAW D1 pivot evidence missing; fail closed')
        if raw_evidence is not None:
            if raw_evidence.pivot_date != d1_asof.index[lvl.first_idx].date() or pd.Timestamp(raw_evidence.pivot_end) != origin_end or raw_evidence.latest_date != d1_asof.index[-1].date() or (abs(raw_evidence.scaled_origin - scaled_origin) > tick * 1e-07) or (abs(raw_evidence.tick - tick) > tick * 1e-07):
                return (None, 'native RAW D1 pivot provenance mismatch')
            origin_price = raw_evidence.origin_price
        else:
            origin_price = scaled_origin
        atr_value = float(d1_asof.iloc[-1][f'atr{cfg.atr_period}'])
        if not isfinite(atr_value) or atr_value <= 0:
            return (None, 'native D1 ATR is not ready')
        if not isfinite(origin_price) or origin_price <= 0 or (not isfinite(lvl.price)) or (lvl.price <= 0):
            return (None, 'swing origin price/cluster level is invalid')
        if abs(round(origin_price / tick) * tick - origin_price) > tick * 1e-05:
            return (None, 'BSU historical origin off native tick grid; normalization unsafe')
        cluster_tol = native_cluster_tolerance(d1_asof, cfg)
        if cluster_tol is None or abs(origin_price - lvl.price) > cluster_tol + tick * 1e-07:
            return (None, 'native pivot lies outside the D1 cluster tolerance')
        detector = BsuDetector(cfg, origin_price, decision.side, atr_value=atr_value, tick_size=tick, bsu_ts=origin_end.to_pydatetime())
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        return (None, f'invalid native D1 BSU proxy evidence: {exc}')
    return (BsuResearchLink(detector=detector, origin_time=origin_end.to_pydatetime(), tick_size=tick, cluster_price=float(lvl.price), origin_price=origin_price), ('native RAW D1 origin confirmed; ' if raw_evidence is not None else 'research-only D1 native pivot linked; ') + 'cluster median distinct from pivot; NOT a canonical BSU or TVX')


# Canonical read-only subset: strategy/native_m5_validation.py
def _duration_seconds(value):
    if value is None:
        return None
    total = getattr(value, 'total_seconds', None)
    if total is None:
        total = getattr(value, 'TotalSeconds', None)
    if total is None:
        return None
    return float(total() if callable(total) else total)

def validate_m5_tradebar(bar, end_at: datetime) -> tuple[bool, str]:
    if not isinstance(end_at, datetime) or end_at.tzinfo is None or end_at.utcoffset() is None:
        return (False, 'M5_END_TIMESTAMP_UNVERIFIED')
    if end_at.second != 0 or end_at.microsecond != 0 or end_at.minute % 5 != 0:
        return (False, 'M5_PERIOD_BOUNDARY_INVALID')
    try:
        period = getattr(bar, 'period', None)
        if period is None:
            return (False, 'M5_SOURCE_PERIOD_MISSING')
        seconds = _duration_seconds(period)
        if seconds is None or not isfinite(seconds) or seconds != 300:
            return (False, 'M5_SOURCE_PERIOD_NOT_FIVE_MINUTES')
        source_start = getattr(bar, 'time')
        source_end = getattr(bar, 'end_time')
        actual_seconds = _duration_seconds(source_end - source_start)
        if actual_seconds is None or not isfinite(actual_seconds) or actual_seconds != 300:
            return (False, 'M5_SOURCE_START_END_INCONSISTENT')
    except (AttributeError, ValueError, TypeError, OverflowError):
        return (False, 'M5_SOURCE_PERIOD_OR_CHRONOLOGY_UNVERIFIED')
    try:
        o, h, lo, c, volume = (float(v) for v in (bar.open, bar.high, bar.low, bar.close, bar.volume))
    except (TypeError, ValueError, OverflowError, AttributeError):
        return (False, 'M5_OHLCV_NOT_NUMERIC')
    if not all((isfinite(v) for v in (o, h, lo, c, volume))):
        return (False, 'M5_OHLCV_NOT_FINITE')
    if min(o, h, lo, c) <= 0 or h < max(o, c, lo) or lo > min(o, c, h):
        return (False, 'M5_OHLC_INVALID')
    if volume <= 0:
        return (False, 'M5_NO_OBSERVED_TRADES')
    if getattr(bar, 'is_fill_forward', False):
        return (False, 'M5_FILL_FORWARD_UNVERIFIED')
    return (True, 'M5_NATIVE_VALIDATED_SHAPE')


# Canonical read-only subset: strategy/native_second_tvx.py
SECOND = timedelta(seconds=1)
BPU2_LENGTH = timedelta(minutes=5)
PRECLOSE_GAP = timedelta(seconds=30)
MAX_SECONDS = 270
MAX_UNOBSERVED_GAP = timedelta(seconds=10)

@dataclass(frozen=True)
class NativePrecloseSample:
    observed_at: datetime
    observed_since: datetime
    bpu2_end: datetime
    observed_low: float
    observed_high: float
    last_price: float
    observed_bars: int = 0
    unobserved_seconds: int = 0
    source: str = 'SEC'
    can_submit: bool = False

class NativeSecondTvxWindow:

    def __init__(self, bpu1_end: datetime):
        if not isinstance(bpu1_end, datetime) or bpu1_end.tzinfo is None or bpu1_end.utcoffset() is None or bpu1_end.second or bpu1_end.microsecond or bpu1_end.minute % 5:
            raise ValueError('native BPU1 end must be aligned, timezone-aware M5')
        self.bpu1_end = bpu1_end
        self.bpu2_end = bpu1_end + BPU2_LENGTH
        self.cutoff = self.bpu2_end - PRECLOSE_GAP
        self.last_at = bpu1_end
        self.count = 0
        self.unobserved_seconds = 0
        self.low = None
        self.high = None
        self.last_price = None
        self.blocked_reason = ''
        self.complete = False

    def accept(self, bar, *, symbol=None, end_at=None) -> NativePrecloseSample | None:
        if self.complete or self.blocked_reason:
            return None
        try:
            start, native_end = (bar.time, bar.end_time)
            end = native_end if end_at is None else end_at
            if not isinstance(end, datetime) or end.tzinfo is None or end.utcoffset() is None:
                raise ValueError('SEC_END_UNVERIFIED')
            if symbol is not None and bar.symbol != symbol:
                raise ValueError('SEC_SYMBOL_MISMATCH')
            if isinstance(native_end, datetime) and native_end.tzinfo is not None and (native_end.utcoffset() is not None) and (native_end != end):
                raise ValueError('SEC_ADAPTER_END_MISMATCH')
            if end.microsecond:
                raise ValueError('SEC_END_NOT_ALIGNED_TO_SECOND')
            if _duration_seconds(bar.period) != 1 or _duration_seconds(native_end - start) != 1:
                raise ValueError('SEC_NATIVE_PERIOD_INVALID')
            if end <= self.bpu1_end or end > self.cutoff:
                raise ValueError('SEC_OUTSIDE_BPU2_PRECLOSE_WINDOW')
            gap = end - self.last_at
            if gap <= timedelta(0):
                raise ValueError('SEC_DUPLICATE_OR_LATE_SECOND')
            if gap > MAX_UNOBSERVED_GAP:
                raise ValueError('SEC_UNOBSERVED_GAP_OVER_10S')
            if getattr(bar, 'is_fill_forward', False):
                raise ValueError('SEC_FILL_FORWARD')
            o, hi, lo, close, vol = (float(bar.open), float(bar.high), float(bar.low), float(bar.close), float(bar.volume))
            if not all((isfinite(x) for x in (o, hi, lo, close, vol))) or min(o, hi, lo, close) <= 0 or hi < max(o, lo, close) or (lo > min(o, hi, close)) or (vol <= 0):
                raise ValueError('SEC_OHLCV_UNVERIFIED')
        except (TypeError, ValueError, AttributeError, OverflowError) as exc:
            self.blocked_reason = str(exc)[:140] or 'SEC_UNKNOWN_DATA_ERROR'
            return None
        self.last_at = end
        self.unobserved_seconds += int(gap.total_seconds()) - 1
        self.count += 1
        self.low = lo if self.low is None else min(self.low, lo)
        self.high = hi if self.high is None else max(self.high, hi)
        self.last_price = close
        if end != self.cutoff:
            return None
        if self.count + self.unobserved_seconds != MAX_SECONDS:
            self.blocked_reason = 'SEC_PRECLOSE_CHRONOLOGY_MISMATCH'
            return None
        self.complete = True
        return NativePrecloseSample(observed_at=end, observed_since=self.bpu1_end, bpu2_end=self.bpu2_end, observed_low=self.low, observed_high=self.high, last_price=self.last_price, observed_bars=self.count, unobserved_seconds=self.unobserved_seconds)


# Canonical read-only subset: strategy/sessions.py
_ET = ZoneInfo('America/New_York')

@dataclass(frozen=True)
class ModelWindow:
    model: str
    start: time
    end: time

def _parse_windows(raw: tuple, model: str) -> list[ModelWindow]:
    out = []
    for s, e in raw:
        sh, sm = map(int, s.split(':'))
        eh, em = map(int, e.split(':'))
        out.append(ModelWindow(model, time(sh, sm), time(eh, em)))
    return out

class SessionPolicy:

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self._windows = {'breakout': _parse_windows(cfg.session_windows_breakout, 'breakout'), 'bounce': _parse_windows(cfg.session_windows_bounce, 'bounce'), 'false_breakout': _parse_windows(cfg.session_windows_false_breakout, 'false_breakout')}

    def is_entry_allowed(self, model: str, ts: datetime) -> tuple[bool, str]:
        if ts.tzinfo is None or ts.utcoffset() is None:
            return (False, 'нет достоверного биржевого часового пояса')
        t = ts.astimezone(_ET).time()
        wins = self._windows.get(model, [])
        for w in wins:
            if w.start <= t < w.end:
                return (True, f'{model}: окно {w.start:%H:%M}-{w.end:%H:%M}')
        if wins:
            spans = ', '.join((f'{w.start:%H:%M}-{w.end:%H:%M}' for w in wins))
            return (False, f'{model}: вне окон ({spans})')
        return (False, f'{model}: окна не заданы')

    def describe(self) -> dict[str, list[str]]:
        return {m: [f'{w.start:%H:%M}-{w.end:%H:%M}' for w in ws] for m, ws in self._windows.items()}


# Canonical read-only subset: strategy/pipeline_audit.py
def _aware(value):
    at = pd.Timestamp(value)
    if pd.isna(at) or at.tzinfo is None:
        raise ValueError('AUDIT_TIMEZONE_REQUIRED')
    return at.tz_convert(ET)

def _chronology(frame, *, daily, at):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError('D1_MISSING' if daily else 'M5_MISSING')
    idx = frame.index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None or idx.hasnans or (not idx.is_unique) or (not idx.is_monotonic_increasing):
        raise ValueError('D1_CHRONOLOGY' if daily else 'M5_CHRONOLOGY')
    if daily:
        if any((x.tz_convert(ET).date() >= at.date() for x in idx)):
            raise ValueError('D1_CURRENT_OR_FUTURE_SESSION')
        if 'bar_end' not in frame:
            raise ValueError('D1_NATIVE_ENDTIME_MISSING')
        ends = [_aware(x) for x in frame.bar_end]
        if any((end <= start or end > at for start, end in zip(idx, ends))) or any((a >= b for a, b in zip(ends, ends[1:]))):
            raise ValueError('D1_NOT_CLOSED_AT_FREEZE')
    elif idx[-1] != at or any((x.tz_convert(ET).date() != at.date() for x in idx)) or any((x.second or x.microsecond or x.minute % 5 for x in idx)) or any((b - a != pd.Timedelta(minutes=5) for a, b in zip(idx, idx[1:]))):
        raise ValueError('M5_STALE_GAPPED_OR_UNALIGNED')

def feature_snapshot(features):
    expected = {name for name, _ in FEATURES}
    rows, blockers = ({}, [])
    if set(features) != expected:
        blockers.append('FEATURE_IDENTITIES_INCOMPLETE_OR_EXTRA')
    for name in sorted(expected):
        feature = features.get(name)
        if feature is None:
            rows[name] = {'value': None, 'reason': 'FEATURE_MISSING', 'detail': {}}
            continue
        try:
            value = _coerce(feature.value)
        except ValueError:
            value = None
            blockers.append(name + ':INVALID_BOOLEAN')
        reason = str(feature.reason)
        if reason.startswith('ошибка:'):
            blockers.append(name + ':CALCULATION_ERROR')
        rows[name] = {'value': value, 'reason': reason, 'detail': dict(feature.detail)}
    return (rows, blockers)

def gate_snapshot(gates):
    rows, blockers = ({}, [])
    if set(gates) != set(GATE_IDS):
        blockers.append('GATE_IDENTITIES_INCOMPLETE_OR_EXTRA')
    for name in GATE_IDS:
        gate = gates.get(name)
        if gate is None:
            rows[name] = {'passed': None, 'reason': 'GATE_MISSING'}
            continue
        value = gate.passed
        if gate.id != name or (value is not None and type(value) is not bool):
            blockers.append(name + ':INVALID_GATE_RECORD')
            value = None
        rows[name] = {'passed': value, 'reason': str(gate.reason)}
        if value is not True:
            blockers.append(name + (':UNKNOWN' if value is None else ':FALSE'))
    return (rows, blockers)

def audit_pipeline(decision, market, observed_at, cfg, *, equity=25000.0):
    feature_rows, blockers = feature_snapshot(decision.features)
    gate_rows, _ = gate_snapshot({})
    report = {'symbol': str(market.symbol), 'can_trade': False, 'availability': 'EVENT_TIME_ONLY_RECEIVE_TIME_UNVERIFIED', 'author_accuracy': 'UNKNOWN', 'status': 'BLOCKED', 'features': feature_rows, 'gates': gate_rows, 'blockers': blockers, 'stage': 'INPUT_VALIDATION', 'bpu_tvx_evidence': 'UNVERIFIED', 'intent': None}
    try:
        at, freeze = (_aware(observed_at), _aware(decision.decided_at))
        if decision.symbol != market.symbol or decision.session != at.date() or freeze.date() != decision.session or (freeze >= at) or (not decision.accepted) or (decision.level is None):
            raise ValueError('FROZEN_DECISION_IDENTITY_OR_TIME_INVALID')
        if market.session_levels is None or decision.level not in market.session_levels or any((l.valid_from is None or l.valid_from > decision.session for l in market.session_levels)):
            raise ValueError('SESSION_LEVEL_SNAPSHOT_UNVERIFIED')
        for frame in (market.d1, market.m5):
            if frame is None or not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None or frame.index.hasnans or (not frame.index.is_unique) or (not frame.index.is_monotonic_increasing):
                raise ValueError('INPUT_CHRONOLOGY_UNVERIFIED')
        d1, m5 = (market.d1_asof(freeze), market.m5_asof(at))
        _chronology(d1, daily=True, at=freeze)
        _chronology(m5, daily=False, at=at)
        report['observed_at'] = at.isoformat()
        report['frozen_at'] = freeze.isoformat()
        report['level_price'] = float(decision.level.price)
        report['level_source'] = str(decision.level.source)
        report['d1_bars'] = len(d1)
        report['m5_bars'] = len(m5)
        entry_at = at - timedelta(seconds=30) if decision.model == 'bounce' else at
        allowed, why = SessionPolicy(cfg).is_entry_allowed(decision.model, entry_at.to_pydatetime())
        report['entry_window'] = {'passed': allowed, 'at': entry_at.isoformat(), 'reason': why}
        if not allowed:
            blockers.append('SESSION_ENTRY_WINDOW_FALSE')
        if any((x != 'SESSION_ENTRY_WINDOW_FALSE' for x in blockers)):
            return report
        frozen_market = MarketData(market.symbol, d1, m5, session_levels=market.session_levels, breakout_retest=market.breakout_retest, bpu_tvx=market.bpu_tvx)
        report['stage'] = 'CANONICAL_GATES'
        intent = build_intent(decision, frozen_market, at.to_pydatetime(), cfg, equity=equity)
        if intent is None:
            blockers.append('CANONICAL_INTENT_UNAVAILABLE')
            return report
        gate_rows, gate_blockers = gate_snapshot(intent.gates)
        report['gates'] = gate_rows
        blockers.extend(gate_blockers)
        report['intent'] = {'model': intent.model, 'side': intent.side, 'entry': intent.limit_price, 'stop': intent.stop_price, 'risk_per_share': intent.risk_per_share}
        if decision.model == 'bounce':
            report['bpu_tvx_evidence'] = 'MATCHED_CANONICAL_MECHANICS_NOT_AUTHOR_OR_DELIVERY_PROOF' if gate_rows['m5_confirmed']['passed'] is True else 'MISSING_OR_REJECTED'
        blockers.extend(('AUTHOR_BSU_NOT_CERTIFIED', 'RECEIVE_TIME_NOT_CERTIFIED', 'ORDERS_DISABLED'))
    except (ValueError, TypeError, AttributeError, KeyError, IndexError, OverflowError) as exc:
        blockers.append(str(exc)[:180] or type(exc).__name__)
    return report


# Canonical read-only subset: strategy/m5_reaction_taxonomy.py
KINDS = ('BOUNCE', 'WICK_BOUNCE', 'WICK_RECLAIM', 'FALSE_BREAK_1BAR', 'FALSE_BREAK_2BAR', 'BREAK_FOLLOWTHROUGH', 'MIRROR_RETEST', 'COMPRESSION', 'CONSOLIDATION', 'CHOP')

@dataclass(frozen=True)
class M5ReactionEvent:
    kind: str
    level_price: float
    side: str
    bar_end: datetime
    anchor_end: datetime
    reason: str
    can_trade: bool = False

@dataclass(frozen=True)
class M5ReactionHeuristics:
    wick_fraction_of_range: float = 0.4
    compression_bars: int = 4
    compression_range_fraction: float = 0.8
    consolidation_bars: int = 5
    consolidation_min_intersections: int = 3
    chop_bars: int = 6
    chop_min_flips: int = 3
    proximity_m5_atr: float = 0.8
    consolidation_width_m5_atr: float = 1.6
    chop_width_m5_atr: float = 2.0
    chop_net_m5_atr: float = 0.6

class M5TenReactionObserver:

    def __init__(self, level_price: float, side: str, tick_size: float, heuristics: M5ReactionHeuristics | None=None):
        self.level = float(level_price)
        self.tick = float(tick_size)
        if not all((isfinite(x) and x > 0 for x in (self.level, self.tick))):
            raise ValueError('M5_REACTION_INVALID_LEVEL_OR_TICK')
        if side not in ('long', 'short'):
            raise ValueError('M5_REACTION_SIDE_REQUIRED')
        self.side = side
        self.h = heuristics or M5ReactionHeuristics()
        h = self.h
        if not isinstance(h, M5ReactionHeuristics):
            raise ValueError('M5_REACTION_HEURISTICS_REQUIRED')
        for key in h.__dataclass_fields__:
            value = getattr(h, key)
            if not isfinite(float(value)) or value <= 0:
                raise ValueError('M5_REACTION_INVALID_HEURISTIC')
        for key in ('compression_bars', 'consolidation_bars', 'consolidation_min_intersections', 'chop_bars', 'chop_min_flips'):
            if type(getattr(h, key)) is not int:
                raise ValueError('M5_REACTION_WINDOW_NOT_INTEGER')
        if h.compression_bars < 3 or h.consolidation_bars < 3 or h.chop_bars < 4 or (h.chop_min_flips >= h.chop_bars) or (h.consolidation_min_intersections > h.consolidation_bars) or (h.compression_range_fraction >= 1) or (h.wick_fraction_of_range >= 1):
            raise ValueError('M5_REACTION_INVALID_WINDOW')
        self._history = []
        self._last = None
        self._mirror_ready = False
        self.gap_resets = 0

    def _signed(self, price):
        return float(price) - self.level if self.side == 'long' else self.level - float(price)

    def observe(self, bar, atr_m5: float | None=None) -> tuple[M5ReactionEvent, ...]:
        now = getattr(bar, 'ts', None)
        if getattr(bar, 'timeframe', None) != 'M5' or not isinstance(now, datetime) or now.tzinfo is None or (now.utcoffset() is None) or (now.astimezone(ET).second != 0) or (now.astimezone(ET).microsecond != 0) or now.astimezone(ET).minute % 5:
            raise ValueError('M5_REACTION_CLOSED_NATIVE_TIME_REQUIRED')
        x = [float(getattr(bar, key)) for key in ('open', 'high', 'low', 'close', 'volume')]
        o, hi, lo, c, volume = x
        if not all((isfinite(v) for v in x)) or min(o, hi, lo, c) <= 0 or volume <= 0 or (hi < max(o, c, lo)) or (lo > min(o, c, hi)):
            raise ValueError('M5_REACTION_INVALID_OHLCV')
        if atr_m5 is not None:
            atr_m5 = float(atr_m5)
            if not isfinite(atr_m5) or atr_m5 <= 0:
                raise ValueError('M5_REACTION_INVALID_M5_ATR')
        if self._last is not None and now <= self._last:
            raise ValueError('M5_REACTION_DUPLICATE_OR_OUT_OF_ORDER')
        if self._last is not None and now - self._last != timedelta(minutes=5):
            self._history.clear()
            self._mirror_ready = False
            self.gap_resets += 1
        self._last = now
        h = self.h
        tol = self.tick * (0.5 + 1e-07)
        signed = self._signed

        def defended(p):
            return signed(p) > tol

        def broken(p):
            return signed(p) < -tol

        def intersects(b):
            return float(b.low) <= self.level + tol and float(b.high) >= self.level - tol

        def pierced(b):
            return float(b.low) < self.level - tol if self.side == 'long' else float(b.high) > self.level + tol

        def tail_fraction(b):
            body_edge = min(float(b.open), float(b.close)) if self.side == 'long' else max(float(b.open), float(b.close))
            t = body_edge - float(b.low) if self.side == 'long' else float(b.high) - body_edge
            width = float(b.high) - float(b.low)
            return t / width if width > tol else 0.0

        def distance(p):
            return signed(p)
        events = []
        seen = set()

        def add(kind, anchor, reason):
            if kind not in KINDS or kind in seen or anchor > now:
                raise ValueError('M5_REACTION_NONCAUSAL_TAG')
            seen.add(kind)
            events.append(M5ReactionEvent(kind, self.level, self.side, now, anchor, reason))
        history = self._history
        prev = history[-1] if history else None
        prev2 = history[-2] if len(history) >= 2 else None
        if prev is not None and intersects(prev) and defended(prev.close) and defended(c) and (distance(c) > distance(prev.close) + tol):
            add('BOUNCE', prev.ts, 'NEXT_M5_CLOSE_AWAY_FROM_FROZEN_LEVEL')
            if defended(prev.open) and tail_fraction(prev) >= h.wick_fraction_of_range:
                add('WICK_BOUNCE', prev.ts, 'DEFENDED_OPEN_CLOSE_LONG_WICK_NEXT_BAR_BOUNCE_PROXY')
        if pierced(bar) and defended(c):
            add('WICK_RECLAIM', now, 'TAIL_ONLY_RECLAIM' if defended(o) else 'BODY_CROSS_RECLAIM')
            if defended(o):
                add('FALSE_BREAK_1BAR', now, 'SAME_M5_OPEN_AND_CLOSE_DEFENDED_WITH_ADVERSE_WICK')
        if prev2 is not None and defended(prev2.close) and broken(prev.close) and defended(c):
            add('FALSE_BREAK_2BAR', prev.ts, 'PREVIOUS_M5_CLOSE_BEYOND_THEN_CURRENT_CLOSE_REENTRY')
        confirmed_break = bool(prev2 is not None and defended(prev2.close) and broken(prev.close) and broken(c) and (-signed(c) > -signed(prev.close) + tol))
        if confirmed_break:
            add('BREAK_FOLLOWTHROUGH', prev.ts, 'TWO_CLOSED_M5_BEYOND_LEVEL_INCREASING_DISTANCE_PROXY')
        if self._mirror_ready and prev is not None and broken(prev.close) and broken(c) and intersects(bar):
            add('MIRROR_RETEST', now, 'POST_CONFIRMED_BREAK_RETEST_FROM_OPPOSITE_SIDE')
        if not broken(c):
            self._mirror_ready = False
        elif confirmed_break:
            self._mirror_ready = True
        chunk = (history + [bar])[-max(h.compression_bars, h.consolidation_bars, h.chop_bars):]
        if atr_m5 is not None:
            n = h.compression_bars
            if len(chunk) >= n:
                w = chunk[-n:]
                ds = [distance(v.close) for v in w]
                widths = [float(v.high) - float(v.low) for v in w]
                if all((tol < d <= h.proximity_m5_atr * atr_m5 for d in ds)) and all((ds[i + 1] < ds[i] - tol for i in range(n - 1))) and (widths[0] > tol) and (widths[-1] < h.compression_range_fraction * widths[0]):
                    add('COMPRESSION', w[0].ts, 'M5_SHRINKING_CLOSE_DISTANCES_AND_BAR_RANGE_HEURISTIC')
            n = h.consolidation_bars
            if len(chunk) >= n:
                w = chunk[-n:]
                if sum((intersects(v) for v in w)) >= h.consolidation_min_intersections and all((abs(float(v.close) - self.level) <= h.proximity_m5_atr * atr_m5 for v in w)) and (max((float(v.high) for v in w)) - min((float(v.low) for v in w)) <= h.consolidation_width_m5_atr * atr_m5):
                    add('CONSOLIDATION', w[0].ts, 'M5_MANY_RANGE_INTERSECTIONS_WITHIN_ATR_WIDTH_HEURISTIC')
            n = h.chop_bars
            if len(chunk) >= n:
                w = chunk[-n:]
                sides = [1 if defended(v.close) else -1 if broken(v.close) else 0 for v in w]
                flips = sum((a * b == -1 for a, b in zip(sides, sides[1:])))
                if flips >= h.chop_min_flips and any((intersects(v) for v in w)) and (max((float(v.high) for v in w)) - min((float(v.low) for v in w)) <= h.chop_width_m5_atr * atr_m5) and (abs(float(w[-1].close) - float(w[0].close)) <= h.chop_net_m5_atr * atr_m5):
                    add('CHOP', w[0].ts, 'M5_MULTIPLE_CLOSE_THROUGH_NO_DIRECTION_HEURISTIC')
        self._history.append(bar)
        self._history = self._history[-max(h.compression_bars, h.consolidation_bars, h.chop_bars, 8):]
        return tuple(events)


def _native_et(value):
    value=pd.Timestamp(value)
    return value.tz_localize(ET) if value.tzinfo is None else value.tz_convert(ET)


def _json_value(value):
    if isinstance(value,(np.bool_,)): return bool(value)
    if isinstance(value,(np.integer,)): return int(value)
    if isinstance(value,(np.floating,)): return float(value) if isfinite(value) else None
    if isinstance(value,(datetime,date,pd.Timestamp)): return value.isoformat()
    if isinstance(value,float) and not isfinite(value): return None
    if isinstance(value,dict): return {str(k):_json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_json_value(v) for v in value]
    return value


def _emit(label,**values):
    print('QWCT 5.10 '+label+' '+json.dumps(_json_value(values),ensure_ascii=False,allow_nan=False,sort_keys=True))


def _frozen_level_role(previous_close,price,tick):
    gap=float(previous_close)-float(price)
    if abs(gap)<=float(tick)*(0.5+1e-7): return None
    return 'long' if gap>0 else 'short'


def _native_prices(bar,expected_symbol,seconds=None):
    if bar.symbol!=expected_symbol or getattr(bar,'is_fill_forward',False):
        raise ValueError('NATIVE_SYMBOL_OR_FILL_FORWARD')
    opened,closed=_native_et(bar.time),_native_et(bar.end_time)
    if seconds is not None and (_duration_seconds(bar.period)!=seconds or
                               _duration_seconds(bar.end_time-bar.time)!=seconds):
        raise ValueError('NATIVE_PERIOD_MISMATCH')
    o,h,l,c,v=map(float,(bar.open,bar.high,bar.low,bar.close,bar.volume))
    if (not all(isfinite(x) for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or
            v<=0 or h<max(o,l,c) or l>min(o,h,c) or closed<=opened):
        raise ValueError('NATIVE_OHLCV_INVALID')
    return opened,closed


def _load_daily(qb,symbol,day,cfg):
    freeze=_native_et(day.replace(hour=9,minute=29))
    raw=list(qb.history[TradeBar](symbol,day-timedelta(days=335),
             freeze.to_pydatetime().replace(tzinfo=None),Resolution.DAILY,
             fill_forward=False,data_normalization_mode=DataNormalizationMode.RAW))
    rows=[]; previous=None
    # Exclude only outside-asof rows; bad in-window observations fail closed.
    closed=[]
    for bar in raw:
        start,end=_native_prices(bar,symbol)
        if start.date()>=day.date() or end>=freeze: continue
        if previous is not None and start<=previous: raise ValueError('D1_DUPLICATE_OR_UNORDERED')
        previous=start; closed.append(bar)
    if len(closed)<180: raise ValueError('D1_FEWER_THAN_180_NATIVE_BARS')
    native_atr=AverageTrueRange(cfg.atr_period,MovingAverageType.WILDERS)
    native_sma=SimpleMovingAverage(cfg.trend_sma)
    for bar in closed[-180:]:
        start,end=_native_et(bar.time),_native_et(bar.end_time)
        native_atr.update(bar); native_sma.update(bar.end_time,bar.close)
        rows.append({'date':start,'bar_end':end,'open':float(bar.open),
                     'high':float(bar.high),'low':float(bar.low),'close':float(bar.close),
                     'volume':float(bar.volume),
                     'atr'+str(cfg.atr_period):float(native_atr.current.value) if native_atr.is_ready else float('nan'),
                     'sma'+str(cfg.trend_sma):float(native_sma.current.value) if native_sma.is_ready else float('nan')})
    frame=pd.DataFrame(rows).set_index('date')
    _chronology(frame,daily=True,at=freeze)
    return frame,freeze


def _load_m5(qb,symbol,day):
    minute=list(qb.history[TradeBar](symbol,day.replace(hour=9,minute=30),
                day.replace(hour=16,minute=0),Resolution.MINUTE,fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW))
    by_end={}; previous=None; accepted=[]; rejected=Counter()
    for bar in minute:
        start,end=_native_prices(bar,symbol,60)
        if start.date()!=day.date() or not time(9,30)<=start.time()<time(16): continue
        if end.second or end.microsecond or end in by_end or (previous is not None and end<=previous):
            raise ValueError('M1_DUPLICATE_UNORDERED_OR_UNALIGNED')
        previous=end; by_end[end]=bar
    consolidator=TradeBarConsolidator(timedelta(minutes=5))
    def completed(sender,bar):
        at=_native_et(bar.end_time)
        good,why=validate_m5_tradebar(bar,at.to_pydatetime())
        complete=all(at-timedelta(minutes=i) in by_end for i in range(5))
        if not good or not complete:
            rejected[why if not good else 'M5_MISSING_NATIVE_MINUTE']+=1; return
        if at.date()==day.date() and time(9,35)<=at.time()<=time(16): accepted.append(bar)
    consolidator.data_consolidated+=completed
    for bar in by_end.values(): consolidator.update(bar)
    consolidator.scan(day.replace(hour=16,minute=1))
    missing=[(day.replace(hour=9,minute=35)+timedelta(minutes=5*i)).isoformat() for i in range(78)
             if not any(_native_et(b.end_time).to_pydatetime().replace(tzinfo=None)==
                        day.replace(hour=9,minute=35)+timedelta(minutes=5*i) for b in accepted)]
    return accepted,rejected,missing


def _historical_second(qb,symbol,bpu1):
    win=NativeSecondTvxWindow(bpu1)
    rows=list(qb.history[TradeBar](symbol,bpu1.replace(tzinfo=None),
              (win.cutoff+timedelta(seconds=1)).replace(tzinfo=None),Resolution.SECOND,
              fill_forward=False,data_normalization_mode=DataNormalizationMode.RAW))
    sample=None
    for bar in rows:
        end=_native_et(bar.end_time).to_pydatetime()
        if not bpu1<end<=win.cutoff: continue
        sample=win.accept(bar,symbol=symbol,end_at=end)
        if win.blocked_reason or sample is not None: break
    _emit('HISTORICAL_SEC',symbol=symbol.value,bpu1_end=bpu1,cutoff=win.cutoff,
          sample_observed=sample is not None,
          reason=win.blocked_reason or ('EXACT_HISTORICAL_SAMPLE_ONLY' if sample else 'NO_EXACT_CUTOFF_SAMPLE'),
          accepted_seconds=win.count,unobserved_seconds=win.unobserved_seconds,
          availability='HISTORICAL_EVENT_TIME_ONLY_RECEIVE_TIME_UNKNOWN',can_trade=False)
    return sample


def run_qwct_pipeline_acceptance():
    day=datetime(2024,6,3); cfg=StrategyConfig(); session_policy=SessionPolicy(cfg)
    qb=QuantBook(); qb.set_time_zone('America/New_York')
    qb.set_start_date(2024,7,1); qb.set_end_date(2024,7,2)
    _emit('START',sample=['AMAT','NFLX','SRPT','MSFT'],session=day.date(),
          scope='FIXED_SAMPLE_NOT_FUNDAMENTAL_TOP10_OR_HOLDOUT',
          source='QC_NATIVE_RAW_D1_M1_NATIVE_M5',risk_gate='UNCHANGED',
          orders='DISABLED',tvx_delivery='NOT_TESTED',author_accuracy='UNKNOWN')
    summary=Counter()
    for ticker in ('AMAT','NFLX','SRPT','MSFT'):
        try:
            sym=qb.add_equity(ticker,Resolution.MINUTE,fill_forward=False,
                    data_normalization_mode=DataNormalizationMode.RAW).symbol
            tick=float(qb.securities[sym].symbol_properties.minimum_price_variation)
            if not isfinite(tick) or tick<=0: raise ValueError('NATIVE_TICK_MISSING')
            d1,freeze=_load_daily(qb,sym,day,cfg)
            levels=tuple(levels_for_session(d1,day.date(),cfg))
            decision=ScenarioEvaluator(cfg).evaluate(ticker,day.date(),freeze.to_pydatetime(),d1,None,list(levels))
            a=float(d1['atr'+str(cfg.atr_period)].iloc[-1])
            _emit('D1',symbol=ticker,accepted=decision.accepted,model=decision.model,side=decision.side,
                  score=decision.score,level=decision.level.price if decision.level else None,
                  last_d1_end=d1.bar_end.iloc[-1],frozen_at=freeze,levels=len(levels),
                  rejects=decision.rejected_reasons[:3],can_trade=False)
            # Keep a premarket-only feature probe even if no scenario is accepted.
            near=nearest_levels(list(levels),float(d1.close.iloc[-1]),cfg.level_proximity_atr,a)
            probe=decision.level or (near[0] if near else None)
            if probe is None:
                _emit('NO_NEARBY_LEVEL',symbol=ticker,can_trade=False); summary['no_nearby_level']+=1; continue
            feats=decision.features if decision.accepted else evaluate_all(d1,None,freeze.to_pydatetime(),probe,list(levels),cfg)
            feature_rows,feature_errors=feature_snapshot(feats)
            _emit('FEATURES_14',symbol=ticker,scope='ACCEPTED_FROZEN_DECISION' if decision.accepted else 'PREMARKET_PROBE_ONLY',
                  level=probe.price,features=feature_rows,errors=feature_errors)
            if feature_errors: raise ValueError('FEATURE_CONTRACT_OR_CALCULATION_ERROR')
            bars,rejected,missing=_load_m5(qb,sym,day)
            _emit('M5_COVERAGE',symbol=ticker,observed=len(bars),expected=78,missing=missing,rejects=dict(rejected))
            if not bars: raise ValueError('NO_NATIVE_M5')
            side=_frozen_level_role(float(d1.close.iloc[-1]),probe.price,tick)
            reactions=M5TenReactionObserver(probe.price,side,tick) if side else None
            m5_atr=AverageTrueRange(cfg.atr_period,MovingAverageType.WILDERS)
            link,link_reason=create_bsu_research_observer(decision,d1,tick,cfg)
            _emit('BSU',symbol=ticker,status='SOFTWARE_D1_PROXY' if link else 'UNAVAILABLE',
                  reason=link_reason,source=link.origin_time if link else None,
                  pivot=link.origin_price if link else None,cluster=link.cluster_price if link else None,
                  author_verified=False,can_trade=False)
            breakout=(BreakoutRetestObserver(symbol=ticker,session=day.date(),side=decision.side,
                level_price=decision.level.price,atr_value=a,max_confirm_chase_atr=cfg.max_entry_distance_atr,
                max_retest_bars=cfg.breakout_retest_max_bars,retest_tolerance_atr=cfg.breakout_retest_touch_atr,
                invalidation_atr=cfg.breakout_retest_invalid_atr) if decision.accepted and decision.model=='breakout' else None)
            fixed_price=link.origin_price if link else probe.price
            fixed=(FixedFloatingLimitObserver(fixed_price,side,tick)
                   if side and abs(fixed_price/tick-round(fixed_price/tick))<=1e-6 else None)
            fixed_counts=Counter(); fixed_last=None
            seen=[]; counts=Counter(); gate_counts={name:Counter() for name in GATE_IDS}
            best=None; best_rank=-1; sec_queries=0
            for native in bars:
                at=_native_et(native.end_time).to_pydatetime()
                b=Bar(at,float(native.open),float(native.high),float(native.low),float(native.close),'M5',float(native.volume))
                m5_atr.update(native)
                causal_atr=float(m5_atr.current.value) if m5_atr.is_ready else None
                if reactions is not None: counts.update(e.kind for e in reactions.observe(b,causal_atr))
                if fixed is not None:
                    fixed_last=fixed.observe(b); fixed_counts[fixed_last.status]+=1
                seen.append({'date':at,'open':b.open,'high':b.high,'low':b.low,'close':b.close,'volume':b.volume})
                if link is not None:
                    before=link.detector.state.phase
                    observed=link.detector.on_bar(b)
                    if before!=observed.phase and observed.phase in ('bpu1','bpu2_confirmed','invalidated'):
                        _emit('BPU',symbol=ticker,phase=observed.phase,at=at,reason=observed.reason,can_trade=False)
                    wants_sec=observed.phase=='bpu1' and before!='bpu1' and sec_queries<2
                    allowed_sec=session_policy.is_entry_allowed('bounce',at+timedelta(minutes=4,seconds=30))[0]
                    if wants_sec and not allowed_sec:
                        _emit('HISTORICAL_SEC_NOT_REQUESTED',symbol=ticker,reason='OUTSIDE_BOUNCE_TVX_ENTRY_WINDOW',can_trade=False)
                    if wants_sec and allowed_sec:
                        sec_queries+=1
                        try:
                            sample=_historical_second(qb,sym,at)
                            if sample is not None:
                                link.detector.observe_preclose(observed_at=sample.observed_at,bpu2_end=sample.bpu2_end,
                                  observed_low=sample.observed_low,observed_high=sample.observed_high,
                                  last_price=sample.last_price,source=sample.source,observed_since=sample.observed_since)
                        except Exception as exc:
                            _emit('HISTORICAL_SEC_BLOCKED',symbol=ticker,reason=str(exc)[:180],can_trade=False)
                if breakout is not None:
                    breakout.on_m5(at=at,open_price=b.open,high=b.high,low=b.low,close=b.close,volume=b.volume)
                if not decision.accepted: continue
                frame=pd.DataFrame(seen).set_index('date')
                market=MarketData(ticker,d1,frame,session_levels=levels,
                    breakout_retest=breakout.evidence if breakout else None,bpu_tvx=None)
                # History cannot create native OnData BpuTvxEvidence.
                report=audit_pipeline(decision,market,at,cfg,equity=cfg.starting_equity)
                for name,row in report['gates'].items():
                    value=row['passed']; gate_counts[name]['TRUE' if value is True else 'FALSE' if value is False else 'UNKNOWN']+=1
                rank=(100 if report['gates']['m5_confirmed']['passed'] is True else 0)+sum(row['passed'] is True for row in report['gates'].values())
                if rank>best_rank: best,best_rank=report,rank
            _emit('FIXED_FLOATING',symbol=ticker,scope='STRICT_LIMIT_PROXY_ONLY_NOT_UNIVERSAL_BSU',
                  price=fixed_price,side=side,status_counts=dict(fixed_counts),
                  last_status=fixed_last.status if fixed_last else ('UNAVAILABLE_OFF_GRID' if side else 'UNAVAILABLE_ROLE_AMBIGUOUS'),
                  hits=fixed_last.hits if fixed_last else None,author_verified=False,can_trade=False)
            _emit('REACTIONS_10',symbol=ticker,scope='FROZEN_LEVEL_SOFTWARE_TAGS_NOT_AUTHOR_ACCURACY',
                  counts={name:counts[name] if reactions else None for name in KINDS},
                  frozen_role=side,gap_resets=reactions.gap_resets if reactions else None,can_trade=False)
            _emit('GATES_8',symbol=ticker,conditional_sec_queries=sec_queries,counts={key:dict(value) for key,value in gate_counts.items()},
                  note='NO_CANONICAL_GATE_EVALUATION' if not decision.accepted else 'PER_BAR_COUNTS_NOT_TRADES')
            if best:
                best.pop('features',None)
                _emit('PIPELINE_EXAMPLE',**best)
            summary['symbols_completed']+=1
        except Exception as exc:
            summary['symbols_blocked']+=1
            _emit('BLOCKED',symbol=ticker,reason=type(exc).__name__+': '+str(exc)[:220],can_trade=False)
    _emit('END',summary=dict(summary),orders='DISABLED',cvd='DEFERRED_BY_OWNER',
          tvx_pass=False,author_accuracy='UNKNOWN',data_source_version='LOCAL_LEVELS_CONFIG_NOT_INDEPENDENTLY_CERTIFIED')
    return summary

run_qwct_pipeline_acceptance()
