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


def _standalone_shadow():
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "d1_shadow_shortlist")
    env = {}
    exec(compile(ast.fix_missing_locations(
        ast.Module(body=[fn], type_ignores=[])), str(APP), "exec"), env)
    return env["d1_shadow_shortlist"]



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


def test_role_conflict_resistance_below_price_not_long_bsu():
    env = _standalone_classifier()
    env["levels_for_session"] = lambda *_: [_level(179.835, "resistance")]
    r = env["classify_snapshot"](_d1(), StrategyConfig(), date(2024,4,1))
    assert r["near"] == 1 and r["aligned"] == 1
    assert r["role_aligned"] == 0 and r["role_conflict"] == 1
    assert r["examples"][0][8] == "BSU_ROLE_MISMATCH"


def test_role_match_support_below_price_matches_long_bsu():
    env = _standalone_classifier()
    env["levels_for_session"] = lambda *_: [_level(179.835, "support")]
    r = env["classify_snapshot"](_d1(), StrategyConfig(), date(2024,4,1))
    assert r["aligned"] == r["role_aligned"] == 1
    assert r["role_conflict"] == 0
    assert r["examples"][0][8] == "BSU_ROLE_OK"


def test_role_audit_does_not_relax_trend_or_volume():
    env = _standalone_classifier()
    env["levels_for_session"] = lambda *_: [_level(179.835, "resistance")]
    env["global_trend"] = lambda *_: -1
    r = env["classify_snapshot"](_d1(), StrategyConfig(), date(2024,4,1))
    assert r["aligned"] == r["role_aligned"] == 0
    d1 = _d1()
    d1["volume_sma"] = 1
    bad = env["classify_snapshot"](d1, StrategyConfig(), date(2024,4,1))
    assert not bad["stage2"]
    assert bad["aligned"] == bad["role_aligned"] == 0


def test_cloud_role_diagnostics_and_file_limits():
    s = APP.read_text(encoding="utf-8")
    for token in ("watch_bsu_role_aligned=", "unique_aligned_tickers=",
                  "unique_bsu_role_aligned_tickers=",
                  "bsu_role_conflict_level_days=", "BSU_ROLE_MISMATCH"):
        assert token in s
    assert len(s.encode("utf-8")) < 32_000


def test_full50_audit_uses_existing_stage2_results_without_changing_top10():
    """Simulated native snapshot: one conflicting Top10 and one valid outside10.

    This unit test only verifies ranking and counters, not LEAN history
    availability or the existence of such a real-market outside10 stock.
    """
    from collections import Counter
    from datetime import datetime
    from zoneinfo import ZoneInfo

    class Sym:
        def __init__(self, value):
            self.value = value

    day = date(2024, 4, 1)
    symbols = tuple(Sym("T%02d" % i) for i in range(12))
    observations = {}
    for i, symbol in enumerate(symbols):
        observations[symbol.value] = {
            "stage2": True, "price": 100.0, "atr": 2.0,
            "volume": 1_000_000, "eligible": 2,
            "near": 1 if i in (0, 11) else 0,
            "aligned": 1 if i in (0, 11) else 0,
            "role_aligned": 1 if i == 11 else 0,
            "role_conflict": 1 if i == 0 else 0,
            "shadow_levels": [(100., "support", "long", 2, 2.0,
                               "2024-03-29", "2024-03-28")] if i == 11 else [],
            "examples": [],
        }
    observed = []
    requests = []
    zone = ZoneInfo("America/New_York")
    algo = SimpleNamespace(
        time=datetime(2024, 4, 1, 9, 29, tzinfo=zone),
        cfg=StrategyConfig(), screen_by_day={day: symbols},
        covered_days=set(), counts=__import__("collections").Counter(),
        rejections=Counter(), example_rows=[], stock_day_ids=set(),
        aligned_day_ids=set(), bsu_role_aligned_day_ids=set(),
        aligned_distinct_tickers=set(), role_aligned_distinct_tickers=set(),
        full50_near_tickers=set(), full50_bsu_role_tickers=set(),
        outside10_examples=[], shadow_picks_logged=[],
        shadow_unique_tickers=set(), shadow_unique_level_origins=set(),
        log=observed.append,
    )
    def histories(members, session):
        requests.append((members, session))
        return {symbol: symbol.value for symbol in members}
    algo._history_asof = histories
    algo._native_frame = lambda raw, session: raw

    tree = ast.parse(APP.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "QwctUniverseResearch")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_prepare")
    env = {
        "et": lambda t: pd.Timestamp(t),
        "classify_snapshot": lambda raw, cfg, session: observations[raw],
        "d1_shadow_shortlist": _standalone_shadow(),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(APP), "exec"), env)
    env["_prepare"](algo)
    assert len(requests) == 1
    assert requests[0][0] is symbols
    assert algo.counts["stage2_pass"] == 12
    assert algo.counts["watchlist_days"] == 10
    assert algo.counts["watch_with_trend_aligned_bounce"] == 1
    assert algo.counts["watch_with_bsu_role_aligned"] == 0
    assert algo.counts["full50_near_symbol_days"] == 2
    assert algo.counts["full50_scenario_aligned_symbol_days"] == 2
    assert algo.counts["full50_bsu_role_aligned_symbol_days"] == 1
    assert algo.counts["outside10_near_symbol_days"] == 1
    assert algo.counts["outside10_bsu_role_aligned_symbol_days"] == 1
    assert algo.counts["shadow_symbol_days"] == 1
    assert algo.counts["shadow_legacy_overlap_symbol_days"] == 0
    assert algo.counts["shadow_outside_legacy_symbol_days"] == 1
    assert algo.counts["shadow_nonempty_days"] == 1
    assert len(algo.shadow_picks_logged) == 1
    assert algo.shadow_picks_logged[0][1:4] == ("T11", 12, 1)
    assert len(algo.shadow_unique_tickers) == 1
    assert len(algo.shadow_unique_level_origins) == 1
    assert any("QWCT SHADOW DAY " in row for row in observed)
    assert len(algo.stock_day_ids) == 10
    assert len(algo.outside10_examples) == 1
    assert algo.outside10_examples[0][1] == "T11"
    assert algo.outside10_examples[0][2] == 12
    # Already prepared once: a duplicate callback cannot double count.
    env["_prepare"](algo)
    assert len(requests) == 1


def test_full50_reports_stay_d1_only_and_under_cloud_limit():
    code = APP.read_text(encoding="utf-8")
    assert "QWCT UNIVERSE FULL50 " in code
    assert "QWCT UNIVERSE OUTSIDE10 " in code
    assert "bsu_role_aligned_symbol_days=" in code
    assert "outside10_bsu_role_aligned_symbol_days=" in code
    assert "unique_bsu_role_aligned_tickers=" in code
    assert len(code.encode("utf-8")) < 32_000
    assert code.count("self._history_asof(members, day)") == 1
    for forbidden in ("self.market_order(", "self.limit_order(",
                      "self.set_holdings(", "self.buy(", "self.sell("):
        assert forbidden not in code


def test_d1_shadow_selection_preserves_liquidity_rank_and_ten_cap():
    select = _standalone_shadow()
    symbols = [SimpleNamespace(value=f"S{i:02d}") for i in range(15)]
    rows = [
        (i, symbols[i], {
            "stage2": i != 2,
            "role_aligned": 1 if i != 3 else 0,
        }) for i in range(15)
    ]
    # Deliberately reverse: selection must still sort by original
    # Fundamental dollar-volume liquidity rank, not incoming list order.
    picks = select(list(reversed(rows)), 10)
    ranks = [rank for rank, sym, obs in picks]
    assert len(picks) == 10
    assert ranks == [0, 1, 4, 5, 6, 7, 8, 9, 10, 11]
    assert not any(rank in (2, 3) for rank in ranks)


def test_d1_shadow_empty_and_partial_do_not_fill_with_unqualified_names():
    select = _standalone_shadow()
    symbols = [SimpleNamespace(value="A"), SimpleNamespace(value="B")]
    rows = [
        (0, symbols[0], {"stage2": True, "role_aligned": 0}),
        (1, symbols[1], {"stage2": True, "role_aligned": 1})
    ]
    assert len(select(rows, 10)) == 1
    assert select(rows[:1], 10) == []
    import pytest
    with pytest.raises(ValueError, match="capacity"):
        select(rows, 0)


def test_shadow_rows_keep_original_provenance_without_future_history():
    env = _standalone_classifier()
    env["levels_for_session"] = lambda *_: [
        _level(179.835, "support"), _level(181, "resistance")
    ]
    r = env["classify_snapshot"](_d1(), StrategyConfig(), date(2024,4,1))
    assert r["role_aligned"] == 1
    assert len(r["shadow_levels"]) == 1
    assert r["shadow_levels"][0][:3] == (179.835, "support", "long")
    assert r["shadow_levels"][0][3:5] == (2, 2.5)


def test_shadow_code_keeps_legacy_watchlist_and_single_native_history_request():
    s = APP.read_text(encoding="utf-8")
    assert "watchlist = passed[:self.cfg.screener_watchlist_limit]" in s
    assert "shadow = d1_shadow_shortlist(passed, self.cfg.screener_watchlist_limit)" in s
    assert s.count("self._history_asof(members, day)") == 1
    for phrase in ("QWCT SHADOW DAY ", "QWCT SHADOW SUMMARY ",
                   "QWCT SHADOW PICK ", "D1 ONLY / NO M5 / NO ORDERS"):
        assert phrase in s
    assert len(s.encode("utf-8")) < 32_000
    for action in ("self.market_order(", "self.limit_order(",
                   "self.buy(", "self.sell(", "self.set_holdings("):
        assert action not in s
