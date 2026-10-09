"""SessionPolicy — торговые часы по моделям (PR #3, исследование).

Расписание Герчика для US-акций (gerchik.com, торговый алгоритм):
- 09:30–10:30 — наблюдение без спешки, входов нет;
- 10:30–12:00 — пробои зеркальных уровней;
- 12:00–13:30 — преимущественно отбои;
- 13:30–15:00 — продолжение движения;
- 15:00–16:00 — наблюдение, входов нет.

Окна настраиваются через StrategyConfig (session_windows_*).
ORB + Stocks in Play живёт по своим часам (модуль orb_stocks_in_play,
там открытие диапазона в 9:35) и этим расписанием НЕ ограничивается:
политика применяется только к режиму Gerchik.
"""
from dataclasses import dataclass
from datetime import datetime, time

from .config import StrategyConfig


@dataclass(frozen=True)
class ModelWindow:
    model: str
    start: time
    end: time


def _parse_windows(raw: tuple, model: str) -> list[ModelWindow]:
    out = []
    for s, e in raw:
        sh, sm = map(int, s.split(":"))
        eh, em = map(int, e.split(":"))
        out.append(ModelWindow(model, time(sh, sm), time(eh, em)))
    return out


class SessionPolicy:
    """Разрешены ли входы модели Gerchik в момент ts (ET)."""

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self._windows = {
            "breakout": _parse_windows(cfg.session_windows_breakout, "breakout"),
            "bounce": _parse_windows(cfg.session_windows_bounce, "bounce"),
            "false_breakout": _parse_windows(
                cfg.session_windows_false_breakout, "false_breakout"),
        }

    def is_entry_allowed(self, model: str,
                         ts: datetime) -> tuple[bool, str]:
        """(разрешён, причина). ts — биржевое время (ET)."""
        t = ts.time()
        wins = self._windows.get(model, [])
        for w in wins:
            if w.start <= t < w.end:
                return True, f"{model}: окно {w.start:%H:%M}-{w.end:%H:%M}"
        if wins:
            spans = ", ".join(f"{w.start:%H:%M}-{w.end:%H:%M}" for w in wins)
            return False, f"{model}: вне окон ({spans})"
        return False, f"{model}: окна не заданы"

    def describe(self) -> dict[str, list[str]]:
        return {m: [f"{w.start:%H:%M}-{w.end:%H:%M}" for w in ws]
                for m, ws in self._windows.items()}
