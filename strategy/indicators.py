"""Read indicator snapshots computed by built-in QuantConnect LEAN indicators.

No home-grown ATR or moving-average calculations. The QCAlgorithm feeds
the 'atr14' and 'sma50' columns from AverageTrueRange and SimpleMovingAverage.
Missing data is explicit (NaN) and all dependent gates must fail closed.
"""
import pandas as pd

from .config import StrategyConfig


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    col = f"atr{period}"
    if col not in df.columns:
        return pd.Series(float("nan"), index=df.index, dtype=float)
    return df[col].astype(float)


def trend_direction(df: pd.DataFrame, idx: int, cfg: StrategyConfig,
                    bars: int | None = None) -> int:
    """Same Gerchik directional rule, using only LEAN-provided SMA snapshots."""
    bars = bars or cfg.local_trend_bars
    col = f"sma{cfg.trend_sma}"
    if col not in df or idx >= len(df) or idx - bars < 0:
        return 0
    try:
        now = float(df[col].iloc[idx])
        prior = float(df[col].iloc[idx - bars])
        close = float(df["close"].iloc[idx])
    except (TypeError, ValueError, IndexError, KeyError):
        return 0
    if pd.isna(now) or pd.isna(prior) or pd.isna(close):
        return 0
    if now > prior and close > now:
        return 1
    if now < prior and close < now:
        return -1
    return 0


def global_trend(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> int:
    return trend_direction(df, idx, cfg, bars=cfg.trend_sma // 2)
