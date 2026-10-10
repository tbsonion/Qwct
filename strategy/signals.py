"""Восемь обязательных фильтров («идеальная сделка») + торговое намерение.

ID гейтов — строго по контракту hybrid (orb_stocks_in_play/hybrid.py):
    trend_aligned, daily_level_valid, m5_confirmed, stop_behind_d1_level,
    room_at_least_4r, target_at_least_3r, risk_approved, matching_trade_model

Ключевое: m5_confirmed — fail-closed. Нет данных M5 -> гейт НЕ пройден.
Неизвестный запас хода (нет следующего уровня) -> гейт НЕ пройден
(больше никакого room=999).
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from math import isfinite

import pandas as pd

from .config import StrategyConfig
from .data import MarketData
from .indicators import global_trend, trend_direction
from .levels import Level, next_level
from .scenarios import ScenarioDecision

GATE_IDS = (
    "trend_aligned",
    "daily_level_valid",
    "m5_confirmed",
    "stop_behind_d1_level",
    "room_at_least_4r",
    "target_at_least_3r",
    "risk_approved",
    "matching_trade_model",
)


@dataclass
class GateResult:
    id: str
    passed: bool | None
    reason: str = ""


@dataclass
class TradeIntent:
    """Намерение на сделку. НЕ ордер и НЕ fill — только решение."""
    symbol: str
    session: date
    signal_at: datetime          # tz-aware; закрытие последней использованной свечи
    side: str                   # "long" | "short"
    model: str                  # breakout | bounce | false_breakout
    level_price: float
    limit_price: float
    stop_price: float
    risk_per_share: float
    shares: int                 # предварительно; финально — риск-менеджер (PR#2)
    tp_r: float
    room_r: float | None
    atr: float | None = None  # ATR для no-chase (P1: не risk_per_share!)
    gates: dict[str, GateResult] = field(default_factory=dict)
    features: dict[str, bool | None] = field(default_factory=dict)
    positives: list[str] = field(default_factory=list)

    @property
    def all_gates_passed(self) -> bool:
        return all(g.passed is True for g in self.gates.values())

    def gate_map(self) -> dict[str, bool | None]:
        return {gid: self.gates[gid].passed for gid in GATE_IDS}


def _direction(side: str) -> int:
    return 1 if side == "long" else -1 if side == "short" else 0


def _gate(id: str, passed, reason: str = "") -> GateResult:
    """Строго Python bool / None — контракт hybrid проверяет isinstance(bool)."""
    if passed is None:
        return GateResult(id, None, reason)
    return GateResult(id, bool(passed), reason)


def evaluate_gates(intent: TradeIntent, decision: ScenarioDecision,
                   market: MarketData, ts: datetime, cfg: StrategyConfig,
                   equity: float = 25_000.0,
                   risk_mgr=None) -> dict[str, GateResult]:
    """Все 8 гейтов as-of момента ts. ts — закрытие последней M5-свечи.

    risk_mgr: RiskManager или None. С менеджером — настоящая проверка
    лимитов (can_open + position_size); без него — предварительная.
    """
    gates: dict[str, GateResult] = {}
    d1 = market.d1_asof(ts)
    m5 = market.m5_asof(ts)
    lvl = decision.level
    side, model = intent.side, intent.model
    dirn = _direction(side) if side else 0

    # 1. trend_aligned — глобальный и локальный тренд совпадают с направлением.
    # allow_countertrend=False (по умолчанию): контртренд запрещён, LMS.
    # True: отдельный экспериментальный режим, требует решения владельца.
    if d1.empty or lvl is None or dirn == 0:
        gates["trend_aligned"] = _gate("trend_aligned", None, "нет данных")
    elif cfg.allow_countertrend:
        g = global_trend(d1, len(d1) - 1, cfg)
        l = trend_direction(d1, len(d1) - 1, cfg)
        gates["trend_aligned"] = _gate(
            "trend_aligned", True,
            f"контртренд-режим ВКЛЮЧЁН (эксперимент): global={g} local={l} "
            f"side={side} [требует решения владельца]")
    else:
        g = global_trend(d1, len(d1) - 1, cfg)
        l = trend_direction(d1, len(d1) - 1, cfg)
        ok = (g == l == dirn) and g != 0
        gates["trend_aligned"] = _gate(
            "trend_aligned", ok, f"global={g} local={l} side={side}")

    # 2. daily_level_valid
    if lvl is None:
        gates["daily_level_valid"] = _gate("daily_level_valid", None, "нет уровня")
    else:
        ok = (lvl.strength >= cfg.min_level_strength
              and lvl.touches >= cfg.min_touches
              and lvl.valid_from is not None and lvl.valid_from <= decision.session)
        gates["daily_level_valid"] = _gate(
            "daily_level_valid", ok,
            f"strength={lvl.strength} touches={lvl.touches} valid_from={lvl.valid_from}")

    # 3. m5_confirmed — FAIL CLOSED
    gates["m5_confirmed"] = _check_m5(m5, lvl, side, model, cfg, ts)

    # 4/5/6 зависят от цен — считаем стоп и лимит
    stop, limit = None, None
    if lvl is not None and dirn != 0:
        a = _atr(d1, cfg)
        if a is None:
            # нет ATR — стоп не из чего строить, дальше только None-гейты
            pass
        else:
            buf = cfg.stop_buffer_atr * a
            stop = lvl.price - dirn * buf
            limit = _limit_price(model, side, lvl, m5)

    # 4. Check D1 placement AND that the stop loses relative to entry.
    if stop is None or limit is None or lvl is None or dirn == 0:
        gates["stop_behind_d1_level"] = _gate("stop_behind_d1_level", None, "нет цен")
    else:
        level_ok = dirn * (lvl.price - stop) > 0
        entry_ok = dirn * (limit - stop) > 0
        valid = (level_ok and entry_ok and
                 all(isfinite(v) and v > 0 for v in (limit, stop)))
        gates["stop_behind_d1_level"] = _gate(
            "stop_behind_d1_level", valid,
            f"stop={stop:.2f} level={lvl.price:.2f} entry={limit:.2f} "
            f"loss_side={entry_ok}")

    # 5/6. room и target
    risk_ps, room_r = None, None
    if stop is not None and limit is not None and lvl is not None:
        risk_ps = dirn * (limit - stop)
        if risk_ps > 0:
            nl = next_level(_session_levels(market, ts, cfg, decision.session),
                            limit, dirn)
            if nl is None:
                gates["room_at_least_4r"] = _gate(
                    "room_at_least_4r", False,
                    "нет следующего уровня — запас хода неизвестен")
            else:
                room_r = abs(nl.price - limit) / risk_ps
                gates["room_at_least_4r"] = _gate(
                    "room_at_least_4r", room_r >= cfg.min_room_r,
                    f"room={room_r:.1f}R next={nl.price:.2f}")
        else:
            gates["room_at_least_4r"] = _gate("room_at_least_4r", False, "риск=0")
    else:
        gates["room_at_least_4r"] = _gate("room_at_least_4r", None, "нет цен")
    if (limit is None or stop is None or dirn == 0 or
            risk_ps is None or risk_ps <= 0):
        gates["target_at_least_3r"] = _gate(
            "target_at_least_3r", False, "нет допустимого входа/стопа")
    else:
        target = limit + dirn * cfg.tp_r * risk_ps
        valid_target = (isfinite(target) and target > 0 and
                        isfinite(cfg.tp_r) and cfg.tp_r >= cfg.min_rr and
                        dirn * (target - limit) >= cfg.min_rr * risk_ps)
        gates["target_at_least_3r"] = _gate(
            "target_at_least_3r", valid_target,
            f"entry={limit:.2f} stop={stop:.2f} target={target:.2f} "
            f"TP={cfg.tp_r}R")

    # 7. risk_approved — через RiskManager, если передан
    if risk_mgr is not None:
        ok_day, why_day = risk_mgr.can_open(intent.session)
        shares_rm, risk_usd = risk_mgr.position_size(intent.risk_per_share,
                                                     intent.limit_price,
                                                     intent.session)
        passed = bool(ok_day and shares_rm > 0)
        reason = (f"[risk-manager] {why_day}; {shares_rm} акций; "
                  f"риск ${risk_usd:.0f}")
        gates["risk_approved"] = _gate("risk_approved", passed, reason)
    elif risk_ps and risk_ps > 0 and limit:
        risk_money = equity * cfg.risk_per_trade_pct / 100
        shares = int(risk_money // risk_ps)
        affordable = shares > 0 and shares * limit <= equity
        # Preliminary count never proves native buying power, total
        # open exposure, daily/weekly loss limits or protected entry.
        gates["risk_approved"] = _gate(
            "risk_approved", None,
            f"UNVERIFIED PRELIMINARY shares={shares}, "
            f"planned risk USD={risk_money:.2f}, cash-fit={affordable}; "
            "no native risk approval")
    else:
        gates["risk_approved"] = _gate("risk_approved", None, "нет данных")

    # 8. matching_trade_model
    ok_model = model in ("breakout", "bounce", "false_breakout") and side in ("long", "short")
    gates["matching_trade_model"] = _gate(
        "matching_trade_model", ok_model, f"model={model} side={side}")

    return gates


def _check_m5(m5: pd.DataFrame, lvl: Level | None, side: str | None,
              model: str | None, cfg: StrategyConfig, ts: datetime) -> GateResult:
    """Minimal two-bar closed M5 evidence. NOT full Gerchik BSU/TVX."""
    if m5 is None or len(m5) < 2 or lvl is None or side not in ("long", "short"):
        return _gate("m5_confirmed", False, "нужны две закрытые M5 свечи")
    if not isinstance(m5.index, pd.DatetimeIndex) or m5.index.tz is None:
        return _gate("m5_confirmed", False, "время M5 не подтверждено")
    if m5.index[-1] - m5.index[-2] != pd.Timedelta(minutes=5):
        return _gate("m5_confirmed", False, "пропущенный M5 бар")
    if pd.Timestamp(m5.index[-1]) != pd.Timestamp(ts):
        return _gate("m5_confirmed", False, "несовпадение времени M5")
    prev, last = m5.iloc[-2], m5.iloc[-1]
    try:
        for bar in (prev, last):
            o, h, l, cl = (float(bar[k]) for k in ("open", "high", "low", "close"))
            if (not all(isfinite(v) and v > 0 for v in (o, h, l, cl))
                    or h < max(o, cl, l) or l > min(o, cl, h)):
                return _gate("m5_confirmed", False, "некорректный OHLC M5")
    except (KeyError, ValueError, TypeError, OverflowError):
        return _gate("m5_confirmed", False, "нет OHLC M5")
    price = lvl.price
    if model == "breakout":
        ok = (prev["close"] <= price < last["close"] if side == "long"
              else prev["close"] >= price > last["close"])
        return _gate("m5_confirmed", ok,
                     "M5 новый переход уровня" if ok else
                     "M5 закрытие по сторону уровня без нового пробоя")
    if model == "bounce":
        touched = last["low"] <= price <= last["high"]
        same_side = (prev["close"] > price and last["close"] > price
                     if side == "long" else
                     prev["close"] < price and last["close"] < price)
        ok = touched and same_side
        return _gate("m5_confirmed", ok,
                     f"two-bar touch={touched} return_side={same_side}; "
                     "полная BSU/BPU модель не подтверждена")
    if model == "false_breakout":
        ok = (prev["close"] <= price and last["high"] > price >= last["close"]
              if side == "short" else
              prev["close"] >= price and last["low"] < price <= last["close"])
        return _gate("m5_confirmed", ok, "M5 прокол и возврат"
                     if ok else "M5 простой ЛП не подтверждён")
    return _gate("m5_confirmed", None, f"неизвестная модель {model}")


def _limit_price(model: str | None, side: str, lvl: Level, m5: pd.DataFrame) -> float:
    """Цена лимитного входа. НЕ fill — только намерение."""
    if model == "breakout" and m5 is not None and not m5.empty:
        return float(m5["close"].iloc[-1])
    return float(lvl.price)


def _atr(d1: pd.DataFrame, cfg: StrategyConfig) -> float | None:
    """ATR(14) по дневкам. None — данных нет/недостаточно (fail closed).

    Раньше возвращал фиктивное 1.0 на пустых данных — это позволяло
    строить стопы и размеры позиций «из воздуха».
    """
    from .indicators import atr
    if d1 is None or d1.empty or len(d1) < cfg.atr_period + 1:
        return None
    v = atr(d1, cfg.atr_period).iloc[-1]
    if pd.isna(v) or v <= 0:
        return None  # No homemade ATR fallback
    return float(v)


def _session_levels(market: MarketData, ts: datetime, cfg: StrategyConfig,
                    session: date) -> list[Level]:
    from .levels import levels_for_session
    return levels_for_session(market.d1_asof(ts), session, cfg)


def build_intent(decision: ScenarioDecision, market: MarketData,
                 ts: datetime, cfg: StrategyConfig,
                 equity: float = 25_000.0,
                 risk_mgr=None) -> TradeIntent | None:
    """Строит торговое намерение с 8 гейтами. None — нет решения утром."""
    if not decision.accepted:
        return None
    d1 = market.d1_asof(ts)
    a = _atr(d1, cfg)
    if a is None:
        return None  # нет ATR — намерение не строим (fail closed)
    lvl = decision.level
    dirn = _direction(decision.side)
    buf = cfg.stop_buffer_atr * a
    stop = lvl.price - dirn * buf
    m5 = market.m5_asof(ts)
    limit = _limit_price(decision.model, decision.side, lvl, m5)
    risk_ps = abs(limit - stop)
    risk_money = equity * cfg.risk_per_trade_pct / 100
    shares = int(risk_money // risk_ps) if risk_ps > 0 else 0
    intent = TradeIntent(
        symbol=decision.symbol, session=decision.session, signal_at=ts,
        side=decision.side, model=decision.model, level_price=lvl.price,
        limit_price=limit, stop_price=stop, risk_per_share=risk_ps,
        shares=shares, tp_r=cfg.tp_r, room_r=None, atr=a,
        gates={}, features=decision.feature_map(),
        positives=decision.positives)
    intent.gates = evaluate_gates(intent, decision, market, ts, cfg, equity, risk_mgr)
    rg = intent.gates["room_at_least_4r"]
    if rg.passed and "room=" in rg.reason:
        try:
            intent.room_r = float(rg.reason.split("room=")[1].split("R")[0])
        except (ValueError, IndexError):
            intent.room_r = None
    return intent
