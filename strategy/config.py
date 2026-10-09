"""Параметры стратегии «Уровни» (Герчик, LMS).

Источник истины по смыслу: docs/strategy_spec.md.
Источник истины по текущим решениям владельца: AGENTS.md
(счёт $25 000, риск 0.2% = $50 на сделку, фаза «только код»).

Единицы:
- деньги — USD;
- риск на сделку — % от equity;
- пороги баров/диапазонов — в единицах ATR(14);
- время — America/New_York (биржевое).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyConfig:
    # ---- Счёт ----
    starting_equity: float = 25_000.0   # USD, виртуальный портфель
    risk_per_trade_pct: float = 0.2     # % депо на сделку -> $50
    max_daily_loss_pct: float = 3.0     # макс. дневной убыток, %
    max_weekly_loss_pct: float = 3.0    # макс. недельный убыток, %
    max_monthly_loss_pct: float = 10.0  # макс. месячный убыток, %
    max_daily_risk_pct: float = 3.0     # макс. суммарный риск открытых сделок в день, %

    # ---- Лимиты активности ----
    max_losing_trades_per_day: int = 3
    max_positions: int = 3
    max_trades_per_day: int = 5
    losing_days_break: int = 3          # убыточных дней подряд -> перерыв
    break_days: int = 3                 # длительность перерыва, торговых дней

    # ---- Фильтр инструментов (скринер) ----
    min_volume: int = 500_000           # акций в день
    min_atr: float = 1.0                # USD
    min_price: float = 5.0              # USD
    volume_lookback_days: int = 20      # объём — среднее за N дней
    data_stale_after_min: int = 60      # данные старше — fail closed

    # ---- Таймфреймы и сессия ----
    timezone: str = "America/New_York"
    session_open: str = "09:30"         # ET
    session_close: str = "16:00"       # ET, к закрытию — флэт
    flatten_before_close_min: int = 5  # принудительное закрытие за N минут
    atr_period: int = 14

    # ---- Уровни (D1) ----
    swing_k: int = 3                    # плечо фрактала; подтверждение через k баров
    level_tolerance_atr: float = 0.25   # допуск кластеризации, в ATR
    min_touches: int = 2
    min_level_strength: float = 2.0     # минимальный скор силы для торговли
    mirror_lookback: int = 60           # окно зеркальности, баров

    # ---- Тренд ----
    trend_sma: int = 50
    local_trend_bars: int = 10

    # ---- Пороги признаков (в ATR) ----
    big_bar_atr: float = 1.5
    small_bar_atr: float = 0.6
    paranormal_bar_atr: float = 2.0
    tight_range_atr: float = 0.5
    tight_bars: int = 5
    accumulation_bars: int = 20
    accumulation_range_atr: float = 1.5
    retest_window: int = 10             # торговых дней
    pullback_free_bars: int = 5
    max_pullback_atr: float = 0.5
    tail_atr: float = 0.15
    level_proximity_atr: float = 1.0    # «возле уровня»
    stop_buffer_atr: float = 0.25       # буфер стопа за уровнем

    # ---- Фильтр «идеальной сделки» ----
    min_room_r: float = 4.0
    min_rr: float = 3.0

    # ---- Выходы ----
    tp_r: float = 3.0
    scale_out: tuple = (0.70, 0.20, 0.10)
    trailing_atr: float = 2.0
    giveback_pct: float = 25.0          # не отдавать >25% max-прибыли

    # ---- Веса моделей (скорее эвристика, не вероятности) ----
    breakout_weights: dict = field(default_factory=lambda: {
        "g01": 2.0,
        "g02": 2.0,
        "g03": 2.0,
        "g04": 1.5,
        "g05": 2.0,
        "g06": 1.5,
        "g07": 1.5,
        "g08": 1.0,
        "g09": 1.0,
        "g10": 1.0,
    })
    bounce_weights: dict = field(default_factory=lambda: {
        "g09.long_pullback_free": 2.0,
        "g09.big_bars_approach": 2.0,
        "g12": 1.5,
        "g13": 1.0,
    })
    false_breakout_weights: dict = field(default_factory=lambda: {
        "g11": 2.5,
        "g14": 1.5,
        "g04": 1.0,
        "g05": -1.0,  # нет отката после ЛП -> скорее пробой
    })
    min_model_score: float = 4.0

    # ---- BSU / BPU1 / BPU2 / TVX (исследование PR #3) ----
    luft_pct_of_stop: float = 20.0   # «люфт» BPU2 — % от дистанции до стопа
    bpu_tick_tol_atr: float = 0.05   # допуск «точного» касания BPU1, в ATR
    bsu_max_bars_back: int = 60      # сколько баров назад ищем BPU1

    # ---- SessionPolicy (исследование PR #3, ET, "HH:MM") ----
    # Расписание Герчика для US-акций: 9:30-10:30 наблюдение без входов,
    # 10:30-12:00 пробои зеркальных, 12:00-13:30 отбои, 13:30-15:00
    # продолжение, 15:00-16:00 наблюдение. ORB живёт по своим часам
    # (модуль orb_stocks_in_play) и этим расписанием НЕ ограничивается.
    session_windows_breakout: tuple = (("10:30", "12:00"), ("13:30", "15:00"))
    session_windows_bounce: tuple = (("12:00", "13:30"),)
    session_windows_false_breakout: tuple = (("10:30", "15:00"),)

    # ---- Контртренд (исследование PR #3) ----
    # False = совпадение трендов обязательно (LMS). True — отдельный
    # экспериментальный режим, требует решения владельца.
    allow_countertrend: bool = False

    # ---- Качество исполнения (исследование PR #3) ----
    max_spread_bps: float = 10.0        # макс. спред, б.п.
    max_entry_distance_atr: float = 0.3  # не гнаться: вход не дальше X ATR от уровня
    limit_order_timeout_min: int = 30    # отмена устаревшего лимита
    max_attempts_per_level: int = 2      # макс. попыток входа на уровень в день
    reentry_cooldown_min: int = 30       # пауза перед повторным входом
