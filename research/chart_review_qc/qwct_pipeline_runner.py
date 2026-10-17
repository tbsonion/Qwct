"""QWCT 5.12 read-only Cloud D1 rejection diagnostic.

Run only from research.ipynb, in the existing Cloud project.
Four fixed 2024-06-03 symbols. No M5 requests, trades, signals or orders.
Uses installed Cloud strategy modules: never downloads/recreates the strategy.
"""
from collections import Counter
from datetime import datetime, timedelta
from importlib import import_module
import json
import math

REQUIRED_MODULES = (
    "strategy.config",
    "strategy.features",
    "strategy.levels",
    "strategy.scenarios",
)
SYMBOLS = ("AMAT", "NFLX", "SRPT", "MSFT")


def summarize_rejections(reasons, limit=16):
    """Preserve exact rejection text and disclose any omitted rows."""
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("REJECTION_LIMIT_INVALID")
    values = [str(reason) for reason in reasons]
    return {
        "total": len(values),
        "reasons": values[:limit],
        "omitted": max(0, len(values) - limit),
    }


def _emit(label, **fields):
    print("QWCT 5.12 " + label + " " +
          json.dumps(fields, sort_keys=True, ensure_ascii=False,
                     allow_nan=False, default=str))


def _et(value):
    import pandas as pd
    timestamp = pd.Timestamp(value)
    return (timestamp.tz_localize("America/New_York") if timestamp.tzinfo is None
            else timestamp.tz_convert("America/New_York"))


def _load_daily(qb, symbol, day, cfg, ai):
    """Keep the 5.10 native RAW history and indicator recipe unchanged."""
    import pandas as pd
    freeze = _et(day.replace(hour=9, minute=29))
    bars = list(qb.history[ai.TradeBar](
        symbol, day - timedelta(days=335),
        freeze.to_pydatetime().replace(tzinfo=None), ai.Resolution.DAILY,
        fill_forward=False, data_normalization_mode=ai.DataNormalizationMode.RAW,
    ))
    previous = None
    closed = []
    for bar in bars:
        if bar.symbol != symbol or getattr(bar, "is_fill_forward", False):
            raise ValueError("D1_WRONG_SYMBOL_OR_FILL_FORWARD")
        started, ended = _et(bar.time), _et(bar.end_time)
        values = tuple(float(x) for x in (
            bar.open, bar.high, bar.low, bar.close, bar.volume))
        o, h, l, c, v = values
        if (not all(math.isfinite(x) for x in values) or
                min(o, h, l, c) <= 0 or v <= 0 or
                h < max(o, l, c) or l > min(o, h, c) or ended <= started):
            raise ValueError("D1_NATIVE_OHLCV_INVALID")
        if started.date() >= day.date() or ended >= freeze:
            continue
        if previous is not None and started <= previous:
            raise ValueError("D1_DUPLICATE_OR_UNORDERED")
        previous = started
        closed.append(bar)
    if len(closed) < 180:
        raise ValueError("D1_FEWER_THAN_180_NATIVE_BARS")
    atr = ai.AverageTrueRange(cfg.atr_period, ai.MovingAverageType.WILDERS)
    sma = ai.SimpleMovingAverage(cfg.trend_sma)
    rows = []
    for bar in closed[-180:]:
        started, ended = _et(bar.time), _et(bar.end_time)
        if ended >= freeze or ended <= started:
            raise ValueError("D1_NOT_CLOSED_AT_PREMARKET_FREEZE")
        atr.update(bar)
        sma.update(bar.end_time, bar.close)
        rows.append({
            "date": started, "bar_end": ended,
            "open": float(bar.open), "high": float(bar.high),
            "low": float(bar.low), "close": float(bar.close),
            "volume": float(bar.volume),
            "atr" + str(cfg.atr_period):
                float(atr.current.value) if atr.is_ready else float("nan"),
            "sma" + str(cfg.trend_sma):
                float(sma.current.value) if sma.is_ready else float("nan"),
        })
    frame = pd.DataFrame(rows).set_index("date")
    if (not frame.index.is_unique or not frame.index.is_monotonic_increasing or
            frame.index.tz is None or
            any(x.date() >= day.date() for x in frame.index) or
            not frame.bar_end.is_monotonic_increasing):
        raise ValueError("D1_BAD_FROZEN_CHRONOLOGY")
    return frame, freeze


def _diagnose_symbol(qb, ticker, day, cfg, ai):
    from strategy.features import evaluate_all
    from strategy.levels import levels_for_session, nearest_levels
    from strategy.scenarios import (
        ScenarioEvaluator, _score_breakout, _score_bounce,
        _score_false_breakout,
    )

    symbol = qb.add_equity(
        ticker, ai.Resolution.MINUTE, fill_forward=False,
        data_normalization_mode=ai.DataNormalizationMode.RAW,
    ).symbol
    d1, freeze = _load_daily(qb, symbol, day, cfg, ai)
    levels = levels_for_session(d1, day.date(), cfg)
    decision = ScenarioEvaluator(cfg).evaluate(
        ticker, day.date(), freeze.to_pydatetime(), d1, None, list(levels))
    close = float(d1.close.iloc[-1])
    d1atr = float(d1["atr" + str(cfg.atr_period)].iloc[-1])
    if not math.isfinite(d1atr) or d1atr <= 0:
        raise ValueError("D1_NATIVE_ATR_NOT_READY")
    near = nearest_levels(list(levels), close, cfg.level_proximity_atr, d1atr)
    _emit(
        "D1", symbol=ticker, accepted=bool(decision.accepted),
        model=decision.model, side=decision.side, score=float(decision.score),
        level=float(decision.level.price) if decision.level else None,
        freeze=freeze.isoformat(), last_d1_end=_et(d1.bar_end.iloc[-1]).isoformat(),
        last_close=close, native_atr=d1atr, levels_total=len(levels),
        nearby=len(near), rejection_details=summarize_rejections(
            decision.rejected_reasons),
        author_verified=False, can_trade=False,
    )

    # Scoring is the canonical evaluator's existing code, not a new model.
    # Print at most four nearby levels so Cloud notebook outputs remain small.
    # Any omitted candidates are explicit, never treated as PASS.
    examined = sorted(near, key=lambda level: abs(level.price - close))[:4]
    for level in examined:
        feats = evaluate_all(
            d1, None, freeze.to_pydatetime(), level, list(levels), cfg)
        feature_errors = [
            {"id": key, "reason": fr.reason} for key, fr in feats.items()
            if fr.reason.startswith("ошибка:") or fr.value is None
        ]
        eligible_bsu = bool(
            level.kind in ("support", "resistance") and
            level.source == "swing_cluster" and
            level.valid_from is not None and level.valid_from <= day.date() and
            level.formed_at is not None and
            level.touches >= cfg.min_touches and
            level.strength >= cfg.min_level_strength
        )
        scores = {
            "breakout": _score_breakout(feats, cfg)[0],
            "bounce": _score_bounce(feats, cfg)[0],
            "false_breakout": _score_false_breakout(feats, cfg)[0],
        }
        _emit(
            "D1_LEVEL", symbol=ticker, level=float(level.price),
            kind=level.kind, source=level.source,
            touches=int(level.touches), strength=float(level.strength),
            bsu_origin_eligible=eligible_bsu,
            scores=scores,
            min_model_score=float(cfg.min_model_score),
            below_threshold=[k for k, v in scores.items()
                             if v < cfg.min_model_score],
            true_features=[key for key, fr in feats.items()
                           if fr.value is True],
            unknown_or_error=feature_errors[:14],
            author_verified=False, can_trade=False,
        )
    _emit("D1_LEVEL_SUMMARY", symbol=ticker, evaluated=len(examined),
          omitted=max(0, len(near)-len(examined)), can_trade=False)
    return bool(decision.accepted)


def run():
    print("QWCT 5.12 RUNNER: PLAIN_TEXT D1_DIAGNOSTIC NO_ORDERS")
    failures = []
    for name in REQUIRED_MODULES:
        try:
            import_module(name)
        except Exception as exc:
            failures.append({"module": name,
                             "error": f"{type(exc).__name__}: {exc}"})
    if failures:
        _emit("LOADER_ERROR", failures=failures, can_trade=False)
        return {"status": "LOADER_ERROR", "can_trade": False}

    _emit("MODULE_IMPORTS_OK", orders="DISABLED", can_trade=False)
    try:
        import AlgorithmImports as ai
        from QuantConnect.Research import QuantBook
        from strategy.config import StrategyConfig
        qb = QuantBook()
        qb.set_time_zone("America/New_York")
        qb.set_start_date(2024, 7, 1)
        qb.set_end_date(2024, 7, 2)
        cfg = StrategyConfig()
        day = datetime(2024, 6, 3)
        _emit("START", symbols=list(SYMBOLS), session=day.date().isoformat(),
              scope="FROZEN_D1_ONLY", orders="DISABLED",
              m5="NOT_RUN", gates_8="NOT_EVALUATED", tvx="NOT_TESTED")
    except Exception as exc:
        _emit("CLOUD_RUNTIME_BLOCKED",
              reason=f"{type(exc).__name__}: {exc}", can_trade=False)
        return {"status": "CLOUD_RUNTIME_BLOCKED", "can_trade": False}
    summary = Counter()
    for ticker in SYMBOLS:
        try:
            accepted = _diagnose_symbol(qb, ticker, day, cfg, ai)
            summary["accepted" if accepted else "rejected"] += 1
        except Exception as exc:
            summary["blocked"] += 1
            _emit("BLOCKED", symbol=ticker,
                  reason=f"{type(exc).__name__}: {exc}",
                  can_trade=False)
    _emit("END", summary=dict(summary), orders="DISABLED", can_trade=False,
          m5="NOT_RUN", gates_8="NOT_EVALUATED", tvx="NOT_TESTED",
          author_accuracy="UNKNOWN", module_version_parity="UNVERIFIED")
    return {"status": "D1_DIAGNOSTIC_COMPLETE", "summary": dict(summary),
            "can_trade": False}
