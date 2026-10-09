"""Оценщик утренних сценариев: сводит 14 групп признаков в решение по модели.

Вход: замороженные до открытия уровни + D1 as-of.
Выход: ScenarioDecision — лучшая (модель, сторона, уровень) или отказ с причинами.

Направление:
- уровень выше цены: пробой -> long, отбой -> short;
- уровень ниже цены: пробой -> short, отбой -> long;
- ложный пробой: против прокола (прокол вверх -> short).

Скоринги — взвешенные эвристики с прозрачным provenance (не вероятности).
"""
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from .config import StrategyConfig
from .features import FeatureResult, evaluate_all
from .levels import Level, nearest_levels


@dataclass
class ModelScore:
    model: str            # breakout | bounce | false_breakout
    side: str             # long | short
    score: float
    positives: list[str] = field(default_factory=list)


@dataclass
class ScenarioDecision:
    symbol: str
    session: date
    decided_at: datetime          # момент решения (tz-aware)
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
        """Плоская карта g01..g14 -> True/False/None (для GerchikEvidence)."""
        return {gid: fr.value for gid, fr in self.features.items()}


def _score_breakout(feats: dict[str, FeatureResult],
                    cfg: StrategyConfig) -> tuple[float, list[str]]:
    total, prov = 0.0, []
    for gid, w in cfg.breakout_weights.items():
        fr = feats.get(gid)
        if fr is not None and fr.value is True:
            total += w
            prov.append(gid)
    g03 = feats.get("g03")
    if g03 is not None and g03.value is True:
        if g03.detail.get("three_bar_retest"):
            total += 0.5
            prov.append("g03.three_bar_retest")
        if g03.detail.get("gap_retest"):
            total += 0.5
            prov.append("g03.gap_retest")
    return round(total, 2), prov


def _score_bounce(feats: dict[str, FeatureResult],
                  cfg: StrategyConfig) -> tuple[float, list[str]]:
    total, prov = 0.0, []
    g09 = feats.get("g09")
    if g09 is not None and g09.detail.get("long_pullback_free"):
        total += cfg.bounce_weights["g09.long_pullback_free"]
        prov.append("g09.long_pullback_free")
    if g09 is not None and g09.detail.get("big_bars_approach"):
        total += cfg.bounce_weights["g09.big_bars_approach"]
        prov.append("g09.big_bars_approach")
    g12 = feats.get("g12")
    if g12 is not None and g12.value is True:
        total += cfg.bounce_weights["g12"]
        prov.append("g12")
    g13 = feats.get("g13")
    if g13 is not None and g13.value is True:
        total += cfg.bounce_weights["g13"]
        prov.append("g13")
    return round(total, 2), prov


def _score_false_breakout(feats: dict[str, FeatureResult],
                          cfg: StrategyConfig) -> tuple[float, list[str]]:
    total, prov = 0.0, []
    for gid, w in cfg.false_breakout_weights.items():
        fr = feats.get(gid)
        if fr is not None and fr.value is True:
            total += w
            prov.append(gid)
    return round(total, 2), prov


class ScenarioEvaluator:
    """Утренняя оценка: для каждого уровня рядом с ценой считает 14 групп
    и выбирает лучшую модель."""

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg

    def evaluate(self, symbol: str, session: date, decided_at: datetime,
                 d1_asof: pd.DataFrame, m5_asof: pd.DataFrame | None,
                 levels: list[Level]) -> ScenarioDecision:
        cfg = self.cfg
        if d1_asof.empty:
            return ScenarioDecision(symbol, session, decided_at, None, None, None,
                                    rejected_reasons=["нет данных D1"])
        price = float(d1_asof["close"].iloc[-1])
        a = _atr_value(d1_asof, cfg)
        cands = nearest_levels(levels, price, cfg.level_proximity_atr, a)
        if not cands:
            return ScenarioDecision(symbol, session, decided_at, None, None, None,
                                    rejected_reasons=["нет уровней рядом с ценой"])

        best: ModelScore | None = None
        best_level: Level | None = None
        best_feats: dict[str, FeatureResult] = {}
        rejected: list[str] = []

        for lvl in cands:
            feats = evaluate_all(d1_asof, m5_asof, decided_at, lvl, levels, cfg)
            # breakout
            s_br, p_br = _score_breakout(feats, cfg)
            side_br = "long" if lvl.price >= price else "short"
            # bounce (против уровня)
            s_bo, p_bo = _score_bounce(feats, cfg)
            side_bo = "short" if lvl.price >= price else "long"
            # false breakout (против прокола)
            s_fp, p_fp = _score_false_breakout(feats, cfg)
            g14 = feats.get("g14")
            side_fp = "short" if lvl.price >= price else "long"

            for model, side, score, prov in (
                    ("breakout", side_br, s_br, p_br),
                    ("bounce", side_bo, s_bo, p_bo),
                    ("false_breakout", side_fp, s_fp, p_fp)):
                if score < cfg.min_model_score:
                    rejected.append(f"{model}@{lvl.price:.2f}: скор {score} < {cfg.min_model_score}")
                    continue
                if best is None or score > best.score:
                    best = ModelScore(model, side, score, prov)
                    best_level = lvl
                    best_feats = feats

        if best is None or best_level is None:
            return ScenarioDecision(symbol, session, decided_at, None, None, None,
                                    features=best_feats, rejected_reasons=rejected)
        return ScenarioDecision(symbol, session, decided_at, best_level,
                                best.model, best.side, best.score, best.positives,
                                best_feats, rejected)


def _atr_value(d1: pd.DataFrame, cfg: StrategyConfig) -> float:
    from .indicators import atr
    v = atr(d1, cfg.atr_period).iloc[-1]
    if pd.isna(v) or v <= 0:
        v = (d1["high"] - d1["low"]).tail(14).mean()
    return float(max(v, 1e-9))
