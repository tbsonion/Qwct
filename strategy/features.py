"""14 групп признаков (предпосылок) из курса — типизированные результаты.

Контракт каждой группы:
    fXX_name(d1, m5, ts, level, levels, cfg) -> FeatureResult

- d1: дневки as-of (только закрытые дни, без заглядывания);
- m5: пятиминутки as-of (может быть пустым);
- ts: момент принятия решения;
- level: оцениваемый уровень; levels: все уровни сессии.

value: True / False / None (None = данных нет, явно указано в reason).
Никаких «молчаливых» допущений: отсутствие данных — это None, а не False.
"""
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .config import StrategyConfig
from .indicators import atr
from .levels import Level


@dataclass
class FeatureResult:
    name: str
    value: bool | None
    detail: dict = field(default_factory=dict)
    reason: str = ""

    def bool_or(self, default: bool = False) -> bool:
        return self.value if self.value is not None else default


def _a(d1: pd.DataFrame, cfg: StrategyConfig) -> float:
    v = atr(d1, cfg.atr_period).iloc[-1]
    if pd.isna(v) or v <= 0:
        raise ValueError("Native LEAN ATR is not ready; do not approximate it")
    return float(v)


def _dist(price: float, lvl: float, a: float) -> float:
    return abs(price - lvl) / max(a, 1e-9)


def _dir_to_level(close: float, level_price: float) -> int:
    return 1 if level_price >= close else -1


# ---------- 1. Поджатие ----------
def g01_squeeze(d1, m5, ts, level: Level, levels, cfg: StrategyConfig) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 6:
        return FeatureResult("g01_squeeze", None, reason="мало баров")
    win = d1.iloc[-6:]
    ranges = win["high"] - win["low"]
    contracting = ranges.iloc[-1] <= ranges.iloc[0] * 0.8
    near = _dist(win["close"].iloc[-1], level.price, a) <= 0.5
    d = _dir_to_level(win["close"].iloc[-1], level.price)
    if d > 0:
        struct = all(win["low"].iloc[i] <= win["low"].iloc[i + 1] for i in range(5))
    else:
        struct = all(win["high"].iloc[i] >= win["high"].iloc[i + 1] for i in range(5))
    v = contracting and near and struct
    return FeatureResult("g01_squeeze", v,
                         {"contracting": contracting, "near": near, "structure": struct,
                          "last_range_atr": round(ranges.iloc[-1] / a, 2)},
                         "поджатие к уровню" if v else "")


# ---------- 2. Узкая проторговка после сильного движения ----------
def g02_tight_consolidation(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    n = cfg.tight_bars
    if len(d1) < n + 3:
        return FeatureResult("g02_tight_consolidation", None, reason="мало баров")
    win = d1.iloc[-n:]
    rng = win["high"].max() - win["low"].min()
    tight = rng <= cfg.tight_range_atr * a
    near = _dist(win["close"].mean(), level.price, a) <= 0.75
    prev = d1.iloc[-n - 3:-n]
    strong = (prev["high"].max() - prev["low"].min()) >= cfg.big_bar_atr * a
    pullbacks = sum(1 for i in range(1, len(win))
                    if abs(win["close"].iloc[i] - win["close"].iloc[i - 1])
                    > cfg.max_pullback_atr * a)
    no_deep_pullback = pullbacks == 0
    v = tight and near and strong and no_deep_pullback
    return FeatureResult("g02_tight_consolidation", v,
                         {"tight": tight, "near": near, "strong_move": strong,
                          "no_deep_pullback": no_deep_pullback,
                          "range_atr": round(rng / a, 2)})


# ---------- 3. Ближний ретест ----------
def g03_near_retest(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    w = cfg.retest_window
    if len(d1) < w + 1:
        return FeatureResult("g03_near_retest", None, reason="мало баров")
    win = d1.iloc[-w - 1:-1]  # без текущего бара
    touched_idx = [i for i in range(len(win))
                   if win["low"].iloc[i] <= level.price <= win["high"].iloc[i]]
    touched = len(touched_idx) > 0
    pullback = (win["high"].max() - win["low"].min()) if touched else None
    shallow = pullback is not None and pullback <= 2.0 * a
    # самый сильный ретест: из 3 баров (касание в последние 3 бара окна)
    three_bar = touched and max(touched_idx) >= len(win) - 3
    # ретест с гэпом: бар открылся с гэпом к уровню
    gap = False
    if touched:
        for i in touched_idx:
            gi = i + 1  # индекс в d1
            prev_close = d1["close"].iloc[-w - 1 + i - 1] if i > 0 else None
            if prev_close is not None:
                if abs(win["open"].iloc[i] - prev_close) >= 0.5 * a:
                    gap = True
                    break
    v = touched and shallow
    return FeatureResult("g03_near_retest", v,
                         {"touched_in_window": touched, "shallow_pullback": shallow,
                          "three_bar_retest": three_bar, "gap_retest": gap,
                          "pullback_atr": round(pullback / a, 2) if pullback else None})


# ---------- 4. Долгое накопление ----------
def g04_accumulation(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    n = cfg.accumulation_bars
    if len(d1) < n:
        return FeatureResult("g04_accumulation", None, reason="мало баров")
    win = d1.iloc[-n:]
    rng = win["high"].max() - win["low"].min()
    v = rng <= cfg.accumulation_range_atr * a and \
        _dist(win["close"].mean(), level.price, a) <= 1.0
    return FeatureResult("g04_accumulation", v,
                         {"range_atr": round(rng / a, 2),
                          "bars": n})


# ---------- 5. После ЛП нет отката ----------
def _simple_false_breakout(d1, level: Level) -> bool:
    for j in range(max(0, len(d1) - 3), len(d1)):
        b = d1.iloc[j]
        if (b["high"] > level.price >= b["close"] and b["open"] < level.price) or \
           (b["low"] < level.price <= b["close"] and b["open"] > level.price):
            return True
    return False


def g05_no_pullback_after_fp(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 5:
        return FeatureResult("g05_no_pullback_after_fp", None, reason="мало баров")
    had_fp = _simple_false_breakout(d1.iloc[:-1], level)
    if not had_fp:
        return FeatureResult("g05_no_pullback_after_fp", False,
                             {"had_false_breakout": False})
    win = d1.iloc[-3:]
    rng = win["high"].max() - win["low"].min()
    v = rng <= 2 * cfg.max_pullback_atr * a
    return FeatureResult("g05_no_pullback_after_fp", v,
                         {"had_false_breakout": True,
                          "post_range_atr": round(rng / a, 2)})


# ---------- 6. После импульса нет отката ----------
def g06_no_pullback_after_impulse(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 7:
        return FeatureResult("g06_no_pullback_after_impulse", None, reason="мало баров")
    pb = d1.iloc[-6]
    is_pb = (pb["high"] - pb["low"]) >= cfg.paranormal_bar_atr * a
    win = d1.iloc[-5:]
    rng = win["high"].max() - win["low"].min()
    consolidating = rng <= 2 * cfg.tight_range_atr * a
    # M5-лесенка внутри большого дневного бара — только при наличии M5
    if m5 is None or len(m5) == 0:
        staircase = None
        sc_reason = "нет M5 — лесенка недоступна"
    else:
        staircase, sc_reason = None, "M5-лесенка: эвристика не реализована (TODO)"
    v = is_pb and consolidating
    return FeatureResult("g06_no_pullback_after_impulse", v,
                         {"paranormal_bar": is_pb,
                          "consolidating": consolidating,
                          "m5_staircase": staircase,
                          "m5_note": sc_reason})


# ---------- 7. Закрытие у экстремума на уровне ----------
def g07_close_at_extreme(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 2:
        return FeatureResult("g07_close_at_extreme", None, reason="мало баров")
    b = d1.iloc[-1]
    rng = b["high"] - b["low"]
    if rng <= 0:
        return FeatureResult("g07_close_at_extreme", False, {})
    near = _dist(b["close"], level.price, a) <= 0.5
    up_tail = b["high"] - max(b["open"], b["close"])
    dn_tail = min(b["open"], b["close"]) - b["low"]
    closed_high = b["close"] >= b["high"] - 0.15 * rng and up_tail <= cfg.tail_atr * a
    closed_low = b["close"] <= b["low"] + 0.15 * rng and dn_tail <= cfg.tail_atr * a
    impulse = rng >= cfg.big_bar_atr * a
    v = near and (closed_high or closed_low)
    return FeatureResult("g07_close_at_extreme", v,
                         {"near_level": near,
                          "closed_at_high": closed_high,
                          "closed_at_low": closed_low,
                          "impulse": impulse,
                          "tail_atr": round(min(up_tail, dn_tail) / a, 2)})


# ---------- 8. Подход на маленьких барах ----------
def g08_small_bars_approach(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 6:
        return FeatureResult("g08_small_bars_approach", None, reason="мало баров")
    win = d1.iloc[-5:]
    avg_range = (win["high"] - win["low"]).mean()
    small = avg_range <= cfg.small_bar_atr * a
    near = _dist(win["close"].iloc[-1], level.price, a) <= 1.0
    trending = abs(win["close"].iloc[-1] - win["close"].iloc[0]) > 0.5 * a
    v = small and near and trending
    return FeatureResult("g08_small_bars_approach", v,
                         {"small_bars": small, "near": near, "trending": trending,
                          "avg_range_atr": round(avg_range / a, 2)})


# ---------- 9. Контекст ----------
def g09_context(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    from .indicators import global_trend, trend_direction
    a = _a(d1, cfg)
    if len(d1) < cfg.pullback_free_bars + 2:
        return FeatureResult("g09_context", None, reason="мало баров")
    win5 = d1.iloc[-5:]
    rng5 = win5["high"].max() - win5["low"].min()
    no_along_level_trading = rng5 > cfg.tight_range_atr * a  # не «прилип» вдоль уровня
    # быстрый подход: дистанция до уровня сократилась > 1 ATR за 3 бара
    d3 = _dist(d1["close"].iloc[-4], level.price, a) - _dist(d1["close"].iloc[-1], level.price, a)
    fast_local_approach = d3 > 1.0
    # длинное безоткатное движение
    w = d1.iloc[-cfg.pullback_free_bars:]
    diffs = w["close"].diff().dropna()
    direction = 1 if diffs.sum() > 0 else -1
    pullbacks = sum(1 for x in diffs if x * direction < -cfg.max_pullback_atr * a)
    long_pullback_free = pullbacks == 0 and \
        _dist(w["close"].iloc[-1], level.price, a) <= 1.0
    # подход на больших барах (для отбоя)
    big = sum(1 for _, b in d1.iloc[-3:].iterrows()
              if (b["high"] - b["low"]) >= cfg.big_bar_atr * a)
    big_bars_approach = big >= 3 and _dist(d1["close"].iloc[-1], level.price, a) <= 1.0
    # пустота за уровнем
    from .levels import next_level as _next
    d = _dir_to_level(d1["close"].iloc[-1], level.price)
    nl = _next(levels, d1["close"].iloc[-1], d)
    clean_zone = True
    if nl is not None:
        clean_zone = abs(nl.price - level.price) > 2.0 * a
    room_atr = abs(nl.price - level.price) / a if nl else None  # None = пустота
    # тренды — значения как подпункты (гейт trend_aligned использует их же)
    gt = global_trend(d1, len(d1) - 1, cfg)
    lt = trend_direction(d1, len(d1) - 1, cfg)
    v = no_along_level_trading or fast_local_approach or long_pullback_free
    return FeatureResult("g09_context", v,
                         {"no_along_level_trading": no_along_level_trading,
                          "fast_local_approach": fast_local_approach,
                          "long_pullback_free": long_pullback_free,
                          "big_bars_approach": big_bars_approach,
                          "clean_zone": clean_zone,
                          "room_atr": round(room_atr, 2) if room_atr else None,
                          "global_trend": gt,
                          "local_trend": lt,
                          "trend_aligned": gt == lt != 0,
                          "market_aligned": None,
                          "market_note": "нет данных индекса — недоступно"})


# ---------- 10. Дистрибуция на старшем ТФ ----------
def g10_htf_distribution(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 15:
        return FeatureResult("g10_htf_distribution", None, reason="мало баров")
    win = d1.iloc[-10:]
    big = sum(1 for _, b in win.iterrows()
              if (b["high"] - b["low"]) >= cfg.big_bar_atr * a)
    directed = abs(win["close"].iloc[-1] - win["close"].iloc[0]) >= 2.0 * a
    near = _dist(win["close"].iloc[-1], level.price, a) <= 1.5
    v = big >= 3 and directed and near
    return FeatureResult("g10_htf_distribution", v,
                         {"big_bars": big, "directed": directed, "near_level": near,
                          "m5_exception": None,
                          "m5_note": "исключение по M5-лесенке недоступно без M5"})


# ---------- 11. Импульса нет там, где должен быть -> признак ЛП ----------
def g11_missing_impulse(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 4:
        return FeatureResult("g11_missing_impulse", None, reason="мало баров")
    attempted = False
    impulsive = False
    for j in range(len(d1) - 3, len(d1)):
        b = d1.iloc[j]
        crossed = (b["high"] > level.price >= d1["close"].iloc[j - 1]) or \
                  (b["low"] < level.price <= d1["close"].iloc[j - 1])
        if crossed:
            attempted = True
            if (b["high"] - b["low"]) >= cfg.big_bar_atr * a:
                impulsive = True
    v = attempted and not impulsive
    return FeatureResult("g11_missing_impulse", v,
                         {"attempted_breakout": attempted,
                          "had_impulse": impulsive})


# ---------- 12. Зона заражённости ----------
def g12_contaminated_zone(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 10:
        return FeatureResult("g12_contaminated_zone", None, reason="мало баров")
    win = d1.iloc[-10:]
    tails = 0
    for _, b in win.iterrows():
        rng = b["high"] - b["low"]
        if rng <= 0:
            continue
        tail = max(b["high"] - max(b["open"], b["close"]),
                   min(b["open"], b["close"]) - b["low"])
        if tail >= 0.4 * rng and abs(b["close"] - level.price) <= 1.5 * a:
            tails += 1
    contaminated = tails >= 4
    # исключение: если было накопление — КИ готовится пробить
    acc = g04_accumulation(d1, m5, ts, level, levels, cfg).bool_or(False)
    v = contaminated and not acc
    return FeatureResult("g12_contaminated_zone", v,
                         {"contaminated": contaminated,
                          "accumulation_exception": acc,
                          "wick_bars": tails})


# ---------- 13. Экстремум ----------
def g13_extremum(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 60:
        return FeatureResult("g13_extremum", None, reason="мало баров")
    hist = d1.iloc[-250:]
    hi, lo = hist["high"].max(), hist["low"].min()
    at_extreme = abs(level.price - hi) <= 0.5 * a or abs(level.price - lo) <= 0.5 * a
    # для пробоя экстремума нужна «энергия» — накопление
    acc = g04_accumulation(d1, m5, ts, level, levels, cfg).bool_or(False)
    v = at_extreme  # сам факт экстремума усиливает разворотный сценарий
    return FeatureResult("g13_extremum", v,
                         {"at_extreme": at_extreme,
                          "has_accumulation": acc,
                          "needs_energy_note": "для пробоя экстремума нужно накопление"})


# ---------- 14. Задёрг против тренда (ликвидность) ----------
def g14_liquidity_sweep(d1, m5, ts, level: Level, levels, cfg) -> FeatureResult:
    a = _a(d1, cfg)
    if len(d1) < 5:
        return FeatureResult("g14_liquidity_sweep", None, reason="мало баров")
    v = False
    detail: dict = {"poke_detected": False, "returned": False,
                    "poke_atr": None, "big_bar_against": None}
    for j in range(len(d1) - 2, len(d1)):
        b = d1.iloc[j]
        poke = max(b["high"] - level.price, level.price - b["low"])
        if 0 < poke <= 0.5 * a:
            detail["poke_detected"] = True
            detail["poke_atr"] = round(poke / a, 2)
            # возврат: следующее закрытие обратно за уровень
            if j + 1 < len(d1):
                nb = d1.iloc[j + 1]
                back = (nb["close"] <= level.price <= b["high"]) or \
                       (nb["close"] >= level.price >= b["low"])
                big_against = (b["high"] - b["low"]) >= cfg.big_bar_atr * a
                detail["returned"] = bool(back)
                detail["big_bar_against"] = bool(big_against)
                if back:
                    v = True
                    break
    return FeatureResult("g14_liquidity_sweep", v, detail)


FEATURES = [
    ("g01", g01_squeeze),
    ("g02", g02_tight_consolidation),
    ("g03", g03_near_retest),
    ("g04", g04_accumulation),
    ("g05", g05_no_pullback_after_fp),
    ("g06", g06_no_pullback_after_impulse),
    ("g07", g07_close_at_extreme),
    ("g08", g08_small_bars_approach),
    ("g09", g09_context),
    ("g10", g10_htf_distribution),
    ("g11", g11_missing_impulse),
    ("g12", g12_contaminated_zone),
    ("g13", g13_extremum),
    ("g14", g14_liquidity_sweep),
]


def _coerce(value) -> bool | None:
    """Строго Python bool / None — контракт hybrid проверяет isinstance(bool)."""
    if value is None:
        return None
    return bool(value)


def evaluate_all(d1: pd.DataFrame, m5: pd.DataFrame | None, ts: datetime,
                 level: Level, levels: list[Level],
                 cfg: StrategyConfig) -> dict[str, FeatureResult]:
    """Все 14 групп для уровня. d1/m5 — as-of срезы (без заглядывания)."""
    out: dict[str, FeatureResult] = {}
    for name, fn in FEATURES:
        try:
            fr = fn(d1, m5, ts, level, levels, cfg)
            fr.value = _coerce(fr.value)
            out[name] = fr
        except Exception as e:  # признак не должен ронять пайплайн
            out[name] = FeatureResult(name, None, reason=f"ошибка: {e}")
    return out
