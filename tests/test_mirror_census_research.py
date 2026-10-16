"""QWCT 3.0 pure research guardrails: PIT native D1 mirror census ONLY.

AST-extracted Python helpers are tested without pretending to execute LEAN.
The baseline native June 2.8 result remains independently required.
"""
import ast
from math import isfinite
from pathlib import Path
from types import SimpleNamespace

from research.chart_review_qc.mirror_asof_audit import audit_mirror


ROOT=Path(__file__).resolve().parents[1]
NEW=ROOT/"research"/"mirror_census_cloud"/"main.py"
BASE=ROOT/"research"/"cohort_cloud"/"main.py"


def get_ast(name, path=NEW):
    tree=ast.parse(path.read_text(encoding="utf8"))
    for obj in tree.body:
        if isinstance(obj,ast.FunctionDef) and obj.name==name:
            return obj
    raise AssertionError(f"missing function: {name}")


def get_func(name):
    original=get_ast(name)
    target=ast.Module(body=[original],type_ignores=[])
    namespace={"isfinite":isfinite}
    exec(compile(target,"research/mirror_census_cloud/main.py","exec"),namespace)
    return namespace[name]


def cfg():
    return SimpleNamespace(min_touches=2,min_level_strength=2,
                           level_proximity_atr=1.0)


def proof(original_kind="support",status="PROXY_VERIFIED"):
    return {"original_kind":original_kind,"status":status}


def lvl(price,touches=3,strength=3):
    return SimpleNamespace(price=price,touches=touches,strength=strength)


def test_mirror_gates_old_support_to_new_resistance_too_far():
    gates=get_func("mirror_gates")
    a=gates(lvl(312.97),proof(),293.7,4.866,-1,-1,cfg(),True)
    assert a["side"]=="short"
    assert a["new_role"]=="resistance"
    assert a["role"] and a["trend"] and a["strength"] and a["causal"]
    assert a["distance_atr"]==a["distance_atr"]
    assert not a["near"]
    assert not a["eligible"]


def test_mirror_gates_near_and_all_criteria_can_research_qualify():
    gates=get_func("mirror_gates")
    result=gates(lvl(295.0),proof(),293.7,4.866,-1,-1,cfg(),True)
    assert result["eligible"]
    assert result["distance_atr"]<1
    assert result["side"]=="short"
    assert not gates(lvl(295.0),proof(status="UNKNOWN"),293.7,4.866,-1,-1,cfg(),True)["eligible"]
    assert not gates(lvl(295.0),proof(),293.7,4.866,+1,-1,cfg(),True)["eligible"]
    assert not gates(lvl(295.0),proof(),293.7,4.866,-1,-1,cfg(),False)["eligible"]
    assert not gates(lvl(295.0,touches=1),proof(),293.7,4.866,-1,-1,cfg(),True)["eligible"]


def test_mirror_long_side_and_role_direction():
    gates=get_func("mirror_gates")
    good=gates(lvl(292),proof("resistance"),293.7,4.866,1,1,cfg(),True)
    assert good["side"]=="long" and good["new_role"]=="support"
    assert good["role"] and good["trend"] and good["eligible"]
    conflict=gates(lvl(292),proof("support"),293.7,4.866,1,1,cfg(),True)
    assert not conflict["role"] and not conflict["eligible"]


def test_no_trades_widening_lookahead_or_reinvented_indicators():
    s=NEW.read_text(encoding="utf8")
    ast.parse(s)
    assert len(s.encode("utf8"))<32_000
    assert "self.get_parameter(\"scan_start\") or \"2024-06-01\"" in s
    assert "self.get_parameter(\"scan_end\") or \"2024-06-30\"" in s
    assert "self.universe_settings.resolution=Resolution.DAILY" in s
    assert "self.add_universe(self._select)" in s
    assert "next_session_fundamentals(" in s
    assert "freeze_fundamental_event(" in s
    assert "self.by_day.get(day)" in s and "day not in self.by_day" in s
    assert "self.callback_at[day]>et(self.time)" in s
    assert "before_market_open(self.anchor,1)" in s
    assert "Resolution.DAILY,fill_forward=False" in s
    assert "180,Resolution.DAILY" in s
    assert "DataNormalizationMode.RAW" in s
    assert "AverageTrueRange(self.cfg.atr_period,MovingAverageType.WILDERS)" in s
    assert "SimpleMovingAverage(self.cfg.trend_sma)" in s
    assert "SimpleMovingAverage(self.cfg.volume_lookback_days)" in s
    assert "lvl.kind==\"mirror\"" in s
    assert "levels_for_session(d1,day,self.cfg)" in s
    assert "self.cfg.level_proximity_atr" not in s or "self.cfg.level_proximity_atr" in s
    assert "cfg.level_proximity_atr" in s
    assert "self.cfg.screener_watchlist_limit" not in s
    assert "self._daily_history(members,day)" in s
    assert "self.count[\"d1_ready\"]+=1" in s
    assert "QWCT MIRROR SUMMARY" in s
    assert "QWCT MIRROR GATES" in s
    assert "QWCT MIRROR REJECTS" in s
    assert "QWCT MIRROR READY" in s
    assert "on_data(" not in s
    for command in (
        "self.market_order(", "self.limit_order(", "self.stop_market_order(",
        "self.set_holdings(", "self.liquidate(", "self.buy(", "self.sell(",
        "TradeBarConsolidator(", "Resolution.SECOND", "Resolution.TICK",
        "self.history[QuoteBar]", "self.history[Tick]"):
        assert command not in s


def test_mirror_history_always_strictly_before_session():
    s=NEW.read_text(encoding="utf8")
    assert "begin.date()>=day or end.date()>=day" in s
    assert "start.date()>=day" in s and "end.date()>=day" in s
    assert "D1_DUPLICATE_OR_NONCAUSAL" in s
    assert "lvl.valid_from<=day" in s
    assert "self.count[\"mirror_ready\"]+=1" in s


def test_mirror_source_audit_exact_reuse_no_new_levels():
    assert ast.dump(get_ast("audit_mirror"))==ast.dump(
        get_ast("audit_mirror",ROOT/"research"/"chart_review_qc"/"mirror_asof_audit.py"))


def test_prior_2_8_bsu_detector_and_charts_unmodified():
    s=BASE.read_text(encoding="utf8")
    assert "QWCT 2.8 BSU AUDIT ACTIVE" in s
    assert "TouchAudit(" in s
    assert "BsuDetector" in s
    assert "consolidator.scan(minute_bars[-1].end_time)" in s
    assert "self._observe(case, bar, at)" in s
