"""Source-grounded, no-orders tests for separate native universe D1 study."""
import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from strategy.config import StrategyConfig
from strategy.levels import Level

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "research" / "universe_cloud" / "main.py"


def _standalone_classifier():
    code = APP.read_text(encoding="utf-8")
    tree = ast.parse(code)
    method = next(n for n in tree.body if
                  isinstance(n, ast.FunctionDef)
                  and n.name == "classify_snapshot")
    env = {
        "passes_gerchik_screener": lambda p, a, v, cfg: (
            p > cfg.min_price and a >= cfg.min_atr
            and v >= cfg.min_volume),
        "levels_for_session": lambda *_: [],
        "global_trend": lambda *_: 1,
        "trend_direction": lambda *_: 1,
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(APP), "exec"), env)
    return env


def _d1():
    days = pd.bdate_range("2023-09-01", periods=180)
    d1 = pd.DataFrame(index=days)
    d1["close"] = 180.0
    d1["atr14"] = 2.0
    d1["volume_sma"] = 2_000_000.0
    return d1


def _level(price, kind, touches=2, strength=2.5):
    return Level(price=price, kind=kind, touches=touches,
                 strength=strength, source="swing_cluster",
                 valid_from=date(2023, 9, 1))


def test_universe_d1_direction_matches_canonical_scenario_side():
    env = _standalone_classifier()
    env["levels_for_session"] = lambda *_: [
        _level(181., "resistance"),
        _level(179.5, "support")]
    # Up/up: support below price implies LONG (PASS);
    # resistance above price implies SHORT (FAIL).
    result = env["classify_snapshot"](
        _d1(), StrategyConfig(), date(2024, 4, 1))
    assert result["stage2"]
    assert result["eligible"] == 2
    assert result["near"] == 2
    assert result["aligned"] == 1
    assert sorted((x[2], x[5]) for x in result["examples"]) == [
        ("long", "PASS"), ("short", "FAIL")]


def test_universe_levels_require_original_two_touches_and_strength():
    env = _standalone_classifier()
    env["levels_for_session"] = lambda *_: [
        _level(179.5, "support", touches=1),
        _level(179.5, "support", strength=1),
        _level(179.5, "support", touches=2, strength=2)]
    got = env["classify_snapshot"](
        _d1(), StrategyConfig(), date(2024, 4, 1))
    assert got["eligible"] == 1
    assert got["near"] == 1
    assert got["aligned"] == 1


def test_native_stage2_rejects_before_level_or_trend(monkeypatch):
    env = _standalone_classifier()
    d1 = _d1()
    d1["volume_sma"] = 10
    result = env["classify_snapshot"](
        d1, StrategyConfig(), date(2024, 4, 1))
    assert not result["stage2"]
    assert result["near"] == result["aligned"] == 0


def test_cloud_source_uses_existing_screening_and_native_daily_indicators():
    source = APP.read_text(encoding="utf-8")
    ast.parse(source)
    assert len(source.encode("utf-8")) < 32_000
    assert "from strategy import select_liquid_fundamentals, passes_gerchik_screener" in source
    pkg = (APP.parent / "strategy_init_cloud.py").read_text(encoding="utf-8")
    root_screen = (ROOT / "strategy" / "screener.py").read_text(encoding="utf-8")
    assert pkg.startswith((ROOT / "strategy" / "__init__.py").read_text(encoding="utf-8").rstrip())
    assert root_screen[root_screen.index("def _positive("):] in pkg
    assert "select_liquid_fundamentals(fundamentals, self.cfg)" in source
    assert "passes_gerchik_screener(price, a, v, cfg)" in source
    assert "self.cfg.screener_watchlist_limit" in source
    assert "self.add_universe(self._screen)" in source
    assert "Resolution.DAILY" in source and "Resolution.MINUTE" in source
    assert "data_normalization_mode=DataNormalizationMode.RAW" in source
    assert "AverageTrueRange" in source and "SimpleMovingAverage" in source
    assert "self.history[TradeBar]" in source
    assert "st.date() >= day or end.date() >= day" in source
    assert "levels_for_session(d1, session, cfg)" in source
    assert "QWCT UNIVERSE SUMMARY" in source
    for cmd in ("self.market_order(", "self.limit_order(",
                "self.set_holdings(", "self.buy(", "self.sell("):
        assert cmd not in source


def test_universe_history_receives_list_not_unmarshallable_tuple():
    """Reproduce native Cloud error: typed History overload rejected tuple.

    This only tests Python call shape; actual C#/Python binding remains
    to be verified in the next real QuantConnect Cloud backtest.
    """
    from collections import Counter
    from datetime import datetime
    from zoneinfo import ZoneInfo

    parsed = ast.parse(APP.read_text(encoding="utf-8"))
    cls = next(x for x in parsed.body if isinstance(x, ast.ClassDef)
               and x.name == "QwctUniverseResearch")
    func = next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                and x.name == "_history_asof")
    timezone = ZoneInfo("America/New_York")

    def as_et(value):
        return pd.Timestamp(value).tz_convert(timezone)

    env = {
        "TradeBar": object,
        "Resolution": SimpleNamespace(DAILY="daily"),
        "DataNormalizationMode": SimpleNamespace(RAW="raw"),
        "et": as_et,
    }
    module = ast.fix_missing_locations(ast.Module(body=[func], type_ignores=[]))
    exec(compile(module, str(APP), "exec"), env)
    history_asof = env["_history_asof"]

    class TypedHistory:
        def __init__(self):
            self.symbol_arg = None

        def __getitem__(self, kind):
            assert kind is object

            def get(symbols, bars, resolution, fill_forward,
                    data_normalization_mode):
                assert type(symbols) is list  # LEAN's typed overload
                assert symbols == ["AAPL", "MSFT"]
                assert bars == 180
                assert resolution == "daily"
                assert fill_forward is False
                assert data_normalization_mode == "raw"
                self.symbol_arg = symbols
                prev = SimpleNamespace(
                    time=datetime(2024, 3, 29, 9, 30, tzinfo=timezone),
                    end_time=datetime(2024, 3, 29, 16, 0, tzinfo=timezone))
                return [{"AAPL": prev, "MSFT": prev}]
            return get

    history = TypedHistory()
    algo = SimpleNamespace(history=history, rejections=Counter())
    result = history_asof(algo, ("AAPL", "MSFT"), date(2024, 4, 1))
    assert history.symbol_arg == ["AAPL", "MSFT"]
    assert len(result["AAPL"]) == len(result["MSFT"]) == 1
    assert not algo.rejections


def test_new_universe_history_fix_does_not_expand_cloud_files():
    source = APP.read_text(encoding="utf-8")
    assert "list(symbols), 180, Resolution.DAILY" in source
    assert len(source.encode("utf-8")) < 32_000
    for bad in ("self.market_order(", "self.limit_order(",
                "self.set_holdings(", "self.buy(", "self.sell("):
        assert bad not in source
