"""Research-only D1 bridge for native PPHL BPU2 episodes; never trades."""
from datetime import datetime, timedelta
from math import isfinite

import pandas as pd

from strategy.indicators import global_trend, trend_direction
from strategy.levels import levels_for_session, next_level, native_cluster_tolerance


def _status(condition):
    return "UNKNOWN" if condition is None else ("PASS" if condition else "FAIL")


def evaluate_d1(d1, proof, cfg, et):
    """Apply original Qwct point-in-time D1 gates, no invented Gerchik score.

    Current PPHL one-pivot branch is deliberately NOT an accepted
    two-touch Qwct cluster. The trend and risk-room checks are separate
    diagnostics; they cannot override that original eligibility gate.
    """
    (ticker, event_at, side, pivot, born, confirmed, tick, first,
     second, stop, luft) = proof
    day = datetime.strptime(event_at[:10], "%Y-%m-%d").date()
    source_at, confirmed_at = et(born), et(confirmed)
    past = d1["bar_end"]
    if (d1.empty or len(d1) < 60 or
            any(et(t).date() >= day for t in past) or
            not d1.index.is_monotonic_increasing or not d1.index.is_unique):
        raise ValueError("bad or non-as-of D1 daily history")
    matching = [i for i, bar_end in enumerate(past)
                if et(bar_end) == source_at]
    if len(matching) != 1:
        origin = None
    else:
        original = d1.iloc[matching[0]]
        original_price = float(original["low" if side == "long" else "high"])
        origin = (abs(original_price-pivot) <= tick*1e-5
                  and source_at < confirmed_at
                  and confirmed_at.date() < day)
    atr = float(d1[f"atr{cfg.atr_period}"].iloc[-1])
    if not isfinite(atr) or atr <= 0:
        raise ValueError("no as-of native D1 ATR")
    levels = levels_for_session(d1, day, cfg)
    tol = native_cluster_tolerance(d1, cfg)
    kind = "support" if side == "long" else "resistance"
    baseline = any(
        l.source == "swing_cluster" and l.kind == kind
        and l.valid_from is not None and l.valid_from <= day
        and l.touches >= cfg.min_touches
        and l.strength >= cfg.min_level_strength
        and tol is not None and abs(l.price-pivot) <= tol + 1e-8
        and 0 <= l.first_idx < len(d1)
        and et(d1.iloc[l.first_idx]["bar_end"]) == source_at
        and abs(float(d1.iloc[l.first_idx]["low" if side == "long" else "high"])
                -pivot) <= tick*1e-5
        for l in levels)
    prev_close = float(d1["close"].iloc[-1])
    proximity = abs(prev_close-pivot) <= cfg.level_proximity_atr*atr
    # Qwct's native SMA50-based trend definitions (not newly fitted rules).
    required_history = cfg.trend_sma + max(
        cfg.trend_sma//2, cfg.local_trend_bars)
    if (len(d1) < required_history
            or f"sma{cfg.trend_sma}" not in d1
            or not isfinite(float(d1[f"sma{cfg.trend_sma}"].iloc[-1]))):
        gt, lt, trend = 0, 0, None
    else:
        gt = global_trend(d1, len(d1)-1, cfg)
        lt = trend_direction(d1, len(d1)-1, cfg)
        target = 1 if side == "long" else -1
        trend = gt == lt == target
    entry = round((pivot + luft if side == "long" else pivot-luft)/tick)*tick
    risk = abs(entry-stop)
    if not isfinite(risk) or risk <= 0:
        raise ValueError("invalid native detector stop/risk")
    direction = 1 if side == "long" else -1
    other = next_level(levels, entry, direction)
    room = abs(other.price-entry) if other is not None else None
    # Missing next D1 level is UNKNOWN, not automatically infinite room.
    room_r = room/risk if room is not None else None
    four_r = None if room_r is None else room_r >= cfg.min_room_r
    three_r = None if room_r is None else room_r >= cfg.min_rr
    # A research-only PPHL source is not sufficient to certify original
    # 14-group model score, intraday plan, bid/ask or executable entry.
    return {
        "symbol": ticker, "bpu2": event_at,
        "origin": _status(origin), "cluster": _status(baseline),
        "proximity": _status(proximity), "trend": _status(trend),
        "global": gt, "local": lt, "room4r": _status(four_r),
        "room3r": _status(three_r), "model": "UNKNOWN",
        "atr": atr, "d1_prev_close": prev_close, "entry": entry,
        "stop": stop, "risk": risk, "next_d1": (
            None if other is None else other.price),
        "room_r": room_r,
    }


def premarket_audit(algo, proof, et):
    """Read historical DAILY TradeBars ending before BPU date; no future."""
    from AlgorithmImports import (
        TradeBar, Resolution, DataNormalizationMode,
        AverageTrueRange, SimpleMovingAverage, MovingAverageType,
    )

    symbol = next((s for s in algo.symbols_to_scan
                   if s.value == proof[0]), None)
    if symbol is None:
        return "NO_SYMBOL"
    day = datetime.strptime(proof[1][:10], "%Y-%m-%d")
    raw = [bar for packet in algo.history[TradeBar](
        [symbol], day-timedelta(days=400), day, Resolution.DAILY,
        fill_forward=False,
        data_normalization_mode=DataNormalizationMode.RAW)
        for key, bar in packet.items() if key == symbol]
    if len(raw) < 60:
        return "D1=UNKNOWN:insufficient_history"
    raw = raw[-180:]
    atr = AverageTrueRange(algo.cfg.atr_period, MovingAverageType.WILDERS)
    sma = SimpleMovingAverage(algo.cfg.trend_sma)
    rows, dates = [], []
    for bar in raw:
        st, end = et(bar.time), et(bar.end_time)
        if (st.date() >= day.date() or end >= et(day)
                or end <= st):
            return "D1=UNKNOWN:future_or_invalid_bar"
        atr.update(bar)
        sma.update(bar.end_time, bar.close)
        rows.append({
            "open": float(bar.open), "high": float(bar.high),
            "low": float(bar.low), "close": float(bar.close),
            "volume": float(bar.volume), "bar_end": end,
            f"atr{algo.cfg.atr_period}": (
                float(atr.current.value) if atr.is_ready else float("nan")),
            f"sma{algo.cfg.trend_sma}": (
                float(sma.current.value) if sma.is_ready else float("nan")),
        })
        dates.append(st.normalize())
    d1 = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))
    outcome = evaluate_d1(d1, proof, algo.cfg, et)
    room = ("UNKNOWN" if outcome["room_r"] is None
            else f'{outcome["room_r"]:.2f}')
    future = ("NONE" if outcome["next_d1"] is None
              else f'{outcome["next_d1"]:.4f}')
    return (
        f'origin={outcome["origin"]} cluster2touch={outcome["cluster"]} '
        f'proximity={outcome["proximity"]} '
        f'trend={outcome["trend"]} G={outcome["global"]} L={outcome["local"]} '
        f'room4R={outcome["room4r"]} room3R={outcome["room3r"]} '
        f'R={room} nextD1={future} entry={outcome["entry"]:.4f} '
        f'stop={outcome["stop"]:.4f} ATR={outcome["atr"]:.4f} '
        f'prevD1={outcome["d1_prev_close"]:.4f} '
        'model=UNKNOWN; NOT TRADE ELIGIBLE')
