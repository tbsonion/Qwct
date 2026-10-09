"""Детектор формации BSU / BPU1 / BPU2 / TVX (PR #3, исследование).

Теория (gerchik.com/torgovye-patterny/bsu-bpu-teoriya):
- BSU — исторический бар, сформировавший уровень (у нас: D1-уровень).
- BPU1 — первый подтверждающий бар, коснувшийся ровно уровня
  (допуск — доли ATR, параметр bpu_tick_tol_atr).
- BPU2 — бар сразу после BPU1, на той же ценовой плоскости; может
  не дотянуть до уровня на «люфт» (20% дистанции до стопа).
- TVX — планируемый лимитный вход за ~30 секунд до закрытия BPU2,
  со смещением от уровня на люфт.
- Инвалидация: BPU2 пробивает BPU1 (закрытие за экстремумом BPU1)
  или уходит дальше люфта -> ждём новую формацию.

Честность точности (исправление PR #5):
- одних закрытых минутных свечей НЕДОСТАТОЧНО для точного сигнала
  «за 30 секунд до закрытия BPU2» — внутри минутного бара неизвестно,
  где была цена на отметке :30;
- precision="tick" — только на секундных/тиковых данных: момент входа
  достижим, lookahead исключён (данные только прошедшие);
- precision="m1_approx" — на M1: TVX отмечается по факту закрытия бара,
  30-секундная точность НЕ заявляется;
- precision="m5_approx" — на M5: грубая аппроксимация;
- без внутридневных данных детектор не запускается вообще.

Детектор — только наблюдение за формацией, НЕ ордер и НЕ fill.
"""
from dataclasses import dataclass, field
from datetime import datetime

from .config import StrategyConfig


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    timeframe: str = "M5"  # "TICK" | "SEC" | "M1" | "M5"
    volume: float = 0.0

    def precision_label(self) -> str:
        if self.timeframe in ("TICK", "SEC"):
            return "tick"
        if self.timeframe == "M1":
            return "m1_approx"
        return "m5_approx"


@dataclass
class BsuState:
    phase: str = "watch_bpu1"
    # watch_bpu1 -> bpu1 -> tvx_armed -> triggered
    # любое нарушение -> invalidated -> watch_bpu1 (новая формация)
    level_price: float = 0.0
    side: str = "long"          # направление отбоя
    bpu1_ts: datetime | None = None
    bpu1_extreme: float | None = None  # low (long) / high (short) бара BPU1
    luft: float = 0.0           # допуск в цене = 20% дистанции до стопа
    entry_price: float | None = None   # TVX
    stop_price: float | None = None
    precision: str = "m5_approx"  # tick | m1_approx | m5_approx
    reason: str = ""
    history: list = field(default_factory=list)


class BsuDetector:
    """Детектор для одного уровня и одного направления."""

    def __init__(self, cfg: StrategyConfig, level_price: float, side: str,
                 atr_value: float, stop_buffer_atr: float | None = None):
        assert side in ("long", "short")
        self.cfg = cfg
        self.state = BsuState(level_price=level_price, side=side)
        buf = (stop_buffer_atr or cfg.stop_buffer_atr) * atr_value
        # стоп за уровнем на буфер; люфт = 20% дистанции до стопа
        self.state.stop_price = (level_price - buf if side == "long"
                                 else level_price + buf)
        self.state.luft = cfg.luft_pct_of_stop / 100.0 * buf
        self._tick_tol = cfg.bpu_tick_tol_atr * atr_value
        self._atr_value = atr_value
        self._bpu2_expected_ts = None

    def _touch_exact(self, bar: Bar) -> bool:
        """Касание ровно уровня (BPU1)."""
        lvl = self.state.level_price
        if self.state.side == "long":
            return abs(bar.low - lvl) <= self._tick_tol
        return abs(bar.high - lvl) <= self._tick_tol

    def _pierced_bpu1(self, bar: Bar) -> bool:
        """BPU2 пробил BPU1: закрытие за экстремумом BPU1."""
        ex = self.state.bpu1_extreme
        if ex is None:
            return False
        if self.state.side == "long":
            return bar.close < ex
        return bar.close > ex

    def _beyond_luft(self, bar: Bar) -> bool:
        """Уход дальше люфта от плоскости уровня."""
        lvl = self.state.level_price
        if self.state.side == "long":
            return bar.low < lvl - self.state.luft
        return bar.high > lvl + self.state.luft

    def tvx_timing_note(self) -> str:
        """Честное описание достижимой точности TVX."""
        p = self.state.precision
        if p == "tick":
            return ("tick: секундные/тиковые данные позволяют разместить "
                    "лимит за ~30 секунд до закрытия BPU2 без lookahead")
        if p == "m1_approx":
            return ("m1_approx: по закрытым минутным барам отметка «за 30 "
                    "секунд до закрытия» недостижима — TVX фиксируется по "
                    "факту закрытия бара BPU2")
        return ("m5_approx: грубая аппроксимация, внутрибарная точность "
                "отсутствует")

    def on_bar(self, bar: Bar) -> BsuState:
        st = self.state
        lvl = st.level_price
        st.history.append(bar.ts)

        if st.phase == "watch_bpu1":
            if self._touch_exact(bar):
                st.phase = "bpu1"
                st.bpu1_ts = bar.ts
                st.bpu1_extreme = bar.low if st.side == "long" else bar.high
                st.precision = bar.precision_label()
                st.reason = (f"BPU1: точное касание {lvl} "
                             f"({bar.timeframe}, допуск {self._tick_tol:.3f})")
            return st

        if st.phase == "bpu1":
            # этот бар — кандидат в BPU2 (сразу после BPU1)
            if self._pierced_bpu1(bar):
                return self._invalidate(
                    f"BPU2 пробил BPU1 (close {bar.close}) — формация отменена")
            if self._beyond_luft(bar):
                return self._invalidate(
                    f"BPU2 ушёл дальше люфта {st.luft:.3f} — формация отменена")
            st.phase = "tvx_armed"
            st.entry_price = (lvl + st.luft if st.side == "long"
                              else lvl - st.luft)
            st.precision = bar.precision_label()
            st.reason = (f"BPU2 подтверждён; TVX={st.entry_price:.3f} "
                         f"(уровень ± люфт {st.luft:.3f}); "
                         f"точность: {st.precision}")
            return st

        if st.phase == "tvx_armed":
            # инвалидация на следующих барах
            if self._pierced_bpu1(bar) or self._beyond_luft(bar):
                return self._invalidate("структура сломана после TVX")
            # касание цены входа — сигнал (не fill!)
            touched = (bar.low <= st.entry_price if st.side == "long"
                       else bar.high >= st.entry_price)
            if touched:
                st.phase = "triggered"
                st.reason = (f"цена коснулась TVX {st.entry_price:.3f} — "
                             f"сигнал формации (не подтверждение сделки)")
            return st

        return st  # triggered / invalidated — ждёт reset()

    def _invalidate(self, reason: str) -> BsuState:
        st = self.state
        st.phase = "invalidated"
        st.reason = reason
        return st

    def reset(self) -> BsuState:
        """Новая формация после инвалидации."""
        lvl, side = self.state.level_price, self.state.side
        self.__init__(self.cfg, lvl, side, atr_value=self._atr_value)
        self.state.reason = "сброс: ждём новую формацию"
        return self.state
