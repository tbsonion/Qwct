"""Build one notebook cell from selected canonical READ-ONLY rule definitions.

No execution/broker/risk-ledger modules or production project copies.
Existing small Cloud project supplies config, levels and BSU modules.
"""
import ast
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'research/chart_review_qc/QWCT_5_10_PIPELINE_ACCEPTANCE_ONE_CELL.py'
PARTS={
 'strategy/indicators.py':['atr','trend_direction','global_trend'],
 'strategy/data.py':['_et','MarketData'],
 'strategy/features.py':['FeatureResult','_a','_dist','_dir_to_level',
   *[n.name for n in ast.parse((ROOT/'strategy/features.py').read_text()).body
     if isinstance(n,ast.FunctionDef) and n.name.startswith('g')],
   '_simple_false_breakout','_without_exception','FEATURES','_coerce','evaluate_all'],
 'strategy/scenarios.py':['ModelScore','ScenarioDecision','_score_breakout','_score_bounce',
                          '_score_false_breakout','ScenarioEvaluator','_atr_value'],
 'strategy/breakout_retest.py':['M5','TERMINAL','BreakoutRetestEvidence','BreakoutRetestObserver'],
 'strategy/bpu_tvx_evidence.py':['BpuTvxEvidence'],
 'strategy/signals.py':['GATE_IDS','GateResult','TradeIntent','_direction','_gate','evaluate_gates',
                      '_check_m5','_limit_price','_atr','_session_levels','build_intent'],
 'strategy/patterns_bsu.py':['_positive','FixedFloatingEvidence','FixedFloatingLimitObserver'],
 'strategy/bsu_bridge.py':['BsuResearchLink','RawBsuEvidence','create_bsu_research_observer'],
 'strategy/native_m5_validation.py':['_duration_seconds','validate_m5_tradebar'],
 'strategy/native_second_tvx.py':['SECOND','BPU2_LENGTH','PRECLOSE_GAP','MAX_SECONDS',
                                'MAX_UNOBSERVED_GAP','NativePrecloseSample','NativeSecondTvxWindow'],
 'strategy/pipeline_audit.py':['_aware','_chronology','feature_snapshot','gate_snapshot','audit_pipeline'],
 'strategy/m5_reaction_taxonomy.py':['KINDS','M5ReactionEvent','M5ReactionHeuristics','M5TenReactionObserver'],
}

class BindExistingDefinitions(ast.NodeTransformer):
    def visit_FunctionDef(self,node):
        self.generic_visit(node)
        if node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str):
            node.body.pop(0)
        return node

    def visit_ClassDef(self,node):
        return self.visit_FunctionDef(node)

    def visit_ImportFrom(self,node):
        if not node.level:
            return node
        # Equivalent local bindings; no imports of missing Cloud modules.
        assignments=[]
        for name in node.names:
            if name.asname and name.asname!=name.name:
                assignments.append(ast.Assign(
                    targets=[ast.Name(id=name.asname,ctx=ast.Store())],
                    value=ast.Name(id=name.name,ctx=ast.Load())))
        return assignments


def selected_nodes(path,names):
    tree=ast.parse((ROOT/path).read_text(encoding='utf-8'))
    found={}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)):
            found[node.name]=node
        elif isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name): found[target.id]=node
    return [BindExistingDefinitions().visit(deepcopy(found[name])) for name in names]

HEADER='''# QWCT 5.10 — paste WHOLE file into ONE NEW CODE CELL, then Run.
# Existing Qwct-M5-Cohort-Research/research.ipynb. Do not replace main.py.
# Fixed four-stock native history sample; no orders, fills or CVD.
# Generated from canonical pure rules by tools/build_qwct_pipeline_cell.py.
from __future__ import annotations
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from QuantConnect.Data.Consolidators import TradeBarConsolidator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time
from collections import Counter
from math import isfinite
from zoneinfo import ZoneInfo
import json
import pandas as pd
import numpy as np
from strategy.config import StrategyConfig
from strategy.levels import Level, levels_for_session, nearest_levels, next_level, native_cluster_tolerance
from strategy.patterns_bsu import Bar, BsuDetector

ET = ZoneInfo("America/New_York")
'''

DRIVER=r'''

def _native_et(value):
    value=pd.Timestamp(value)
    return value.tz_localize(ET) if value.tzinfo is None else value.tz_convert(ET)


def _json_value(value):
    if isinstance(value,(np.bool_,)): return bool(value)
    if isinstance(value,(np.integer,)): return int(value)
    if isinstance(value,(np.floating,)): return float(value) if isfinite(value) else None
    if isinstance(value,(datetime,date,pd.Timestamp)): return value.isoformat()
    if isinstance(value,float) and not isfinite(value): return None
    if isinstance(value,dict): return {str(k):_json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_json_value(v) for v in value]
    return value


def _emit(label,**values):
    print('QWCT 5.10 '+label+' '+json.dumps(_json_value(values),ensure_ascii=False,allow_nan=False,sort_keys=True))


def _frozen_level_role(previous_close,price,tick):
    gap=float(previous_close)-float(price)
    if abs(gap)<=float(tick)*(0.5+1e-7): return None
    return 'long' if gap>0 else 'short'


def _native_prices(bar,expected_symbol,seconds=None):
    if bar.symbol!=expected_symbol or getattr(bar,'is_fill_forward',False):
        raise ValueError('NATIVE_SYMBOL_OR_FILL_FORWARD')
    opened,closed=_native_et(bar.time),_native_et(bar.end_time)
    if seconds is not None and (_duration_seconds(bar.period)!=seconds or
                               _duration_seconds(bar.end_time-bar.time)!=seconds):
        raise ValueError('NATIVE_PERIOD_MISMATCH')
    o,h,l,c,v=map(float,(bar.open,bar.high,bar.low,bar.close,bar.volume))
    if (not all(isfinite(x) for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or
            v<=0 or h<max(o,l,c) or l>min(o,h,c) or closed<=opened):
        raise ValueError('NATIVE_OHLCV_INVALID')
    return opened,closed


def _load_daily(qb,symbol,day,cfg):
    freeze=_native_et(day.replace(hour=9,minute=29))
    raw=list(qb.history[TradeBar](symbol,day-timedelta(days=335),
             freeze.to_pydatetime().replace(tzinfo=None),Resolution.DAILY,
             fill_forward=False,data_normalization_mode=DataNormalizationMode.RAW))
    rows=[]; previous=None
    # Exclude only outside-asof rows; bad in-window observations fail closed.
    closed=[]
    for bar in raw:
        start,end=_native_prices(bar,symbol)
        if start.date()>=day.date() or end>=freeze: continue
        if previous is not None and start<=previous: raise ValueError('D1_DUPLICATE_OR_UNORDERED')
        previous=start; closed.append(bar)
    if len(closed)<180: raise ValueError('D1_FEWER_THAN_180_NATIVE_BARS')
    native_atr=AverageTrueRange(cfg.atr_period,MovingAverageType.WILDERS)
    native_sma=SimpleMovingAverage(cfg.trend_sma)
    for bar in closed[-180:]:
        start,end=_native_et(bar.time),_native_et(bar.end_time)
        native_atr.update(bar); native_sma.update(bar.end_time,bar.close)
        rows.append({'date':start,'bar_end':end,'open':float(bar.open),
                     'high':float(bar.high),'low':float(bar.low),'close':float(bar.close),
                     'volume':float(bar.volume),
                     'atr'+str(cfg.atr_period):float(native_atr.current.value) if native_atr.is_ready else float('nan'),
                     'sma'+str(cfg.trend_sma):float(native_sma.current.value) if native_sma.is_ready else float('nan')})
    frame=pd.DataFrame(rows).set_index('date')
    _chronology(frame,daily=True,at=freeze)
    return frame,freeze


def _load_m5(qb,symbol,day):
    minute=list(qb.history[TradeBar](symbol,day.replace(hour=9,minute=30),
                day.replace(hour=16,minute=0),Resolution.MINUTE,fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW))
    by_end={}; previous=None; accepted=[]; rejected=Counter()
    for bar in minute:
        start,end=_native_prices(bar,symbol,60)
        if start.date()!=day.date() or not time(9,30)<=start.time()<time(16): continue
        if end.second or end.microsecond or end in by_end or (previous is not None and end<=previous):
            raise ValueError('M1_DUPLICATE_UNORDERED_OR_UNALIGNED')
        previous=end; by_end[end]=bar
    consolidator=TradeBarConsolidator(timedelta(minutes=5))
    def completed(sender,bar):
        at=_native_et(bar.end_time)
        good,why=validate_m5_tradebar(bar,at.to_pydatetime())
        complete=all(at-timedelta(minutes=i) in by_end for i in range(5))
        if not good or not complete:
            rejected[why if not good else 'M5_MISSING_NATIVE_MINUTE']+=1; return
        if at.date()==day.date() and time(9,35)<=at.time()<=time(16): accepted.append(bar)
    consolidator.data_consolidated+=completed
    for bar in by_end.values(): consolidator.update(bar)
    consolidator.scan(day.replace(hour=16,minute=1))
    missing=[(day.replace(hour=9,minute=35)+timedelta(minutes=5*i)).isoformat() for i in range(78)
             if not any(_native_et(b.end_time).to_pydatetime().replace(tzinfo=None)==
                        day.replace(hour=9,minute=35)+timedelta(minutes=5*i) for b in accepted)]
    return accepted,rejected,missing


def _historical_second(qb,symbol,bpu1):
    win=NativeSecondTvxWindow(bpu1)
    rows=list(qb.history[TradeBar](symbol,bpu1.replace(tzinfo=None),
              (win.cutoff+timedelta(seconds=1)).replace(tzinfo=None),Resolution.SECOND,
              fill_forward=False,data_normalization_mode=DataNormalizationMode.RAW))
    sample=None
    for bar in rows:
        end=_native_et(bar.end_time).to_pydatetime()
        if not bpu1<end<=win.cutoff: continue
        sample=win.accept(bar,symbol=symbol,end_at=end)
        if win.blocked_reason or sample is not None: break
    _emit('HISTORICAL_SEC',symbol=symbol.value,bpu1_end=bpu1,cutoff=win.cutoff,
          sample_observed=sample is not None,
          reason=win.blocked_reason or ('EXACT_HISTORICAL_SAMPLE_ONLY' if sample else 'NO_EXACT_CUTOFF_SAMPLE'),
          accepted_seconds=win.count,unobserved_seconds=win.unobserved_seconds,
          availability='HISTORICAL_EVENT_TIME_ONLY_RECEIVE_TIME_UNKNOWN',can_trade=False)
    return sample


def run_qwct_pipeline_acceptance():
    day=datetime(2024,6,3); cfg=StrategyConfig()
    qb=QuantBook(); qb.set_time_zone('America/New_York')
    qb.set_start_date(2024,7,1); qb.set_end_date(2024,7,2)
    _emit('START',sample=['AMAT','NFLX','SRPT','MSFT'],session=day.date(),
          scope='FIXED_SAMPLE_NOT_FUNDAMENTAL_TOP10_OR_HOLDOUT',
          source='QC_NATIVE_RAW_D1_M1_NATIVE_M5',risk_gate='UNCHANGED',
          orders='DISABLED',tvx_delivery='NOT_TESTED',author_accuracy='UNKNOWN')
    summary=Counter()
    for ticker in ('AMAT','NFLX','SRPT','MSFT'):
        try:
            sym=qb.add_equity(ticker,Resolution.MINUTE,fill_forward=False,
                    data_normalization_mode=DataNormalizationMode.RAW).symbol
            tick=float(qb.securities[sym].symbol_properties.minimum_price_variation)
            if not isfinite(tick) or tick<=0: raise ValueError('NATIVE_TICK_MISSING')
            d1,freeze=_load_daily(qb,sym,day,cfg)
            levels=tuple(levels_for_session(d1,day.date(),cfg))
            decision=ScenarioEvaluator(cfg).evaluate(ticker,day.date(),freeze.to_pydatetime(),d1,None,list(levels))
            a=float(d1['atr'+str(cfg.atr_period)].iloc[-1])
            _emit('D1',symbol=ticker,accepted=decision.accepted,model=decision.model,side=decision.side,
                  score=decision.score,level=decision.level.price if decision.level else None,
                  last_d1_end=d1.bar_end.iloc[-1],frozen_at=freeze,levels=len(levels),
                  rejects=decision.rejected_reasons[:3],can_trade=False)
            # Keep a premarket-only feature probe even if no scenario is accepted.
            near=nearest_levels(list(levels),float(d1.close.iloc[-1]),cfg.level_proximity_atr,a)
            probe=decision.level or (near[0] if near else None)
            if probe is None:
                _emit('NO_NEARBY_LEVEL',symbol=ticker,can_trade=False); summary['no_nearby_level']+=1; continue
            feats=decision.features if decision.accepted else evaluate_all(d1,None,freeze.to_pydatetime(),probe,list(levels),cfg)
            feature_rows,feature_errors=feature_snapshot(feats)
            _emit('FEATURES_14',symbol=ticker,scope='ACCEPTED_FROZEN_DECISION' if decision.accepted else 'PREMARKET_PROBE_ONLY',
                  level=probe.price,features=feature_rows,errors=feature_errors)
            if feature_errors: raise ValueError('FEATURE_CONTRACT_OR_CALCULATION_ERROR')
            bars,rejected,missing=_load_m5(qb,sym,day)
            _emit('M5_COVERAGE',symbol=ticker,observed=len(bars),expected=78,missing=missing,rejects=dict(rejected))
            if not bars: raise ValueError('NO_NATIVE_M5')
            side=_frozen_level_role(float(d1.close.iloc[-1]),probe.price,tick)
            reactions=M5TenReactionObserver(probe.price,side,tick) if side else None
            m5_atr=AverageTrueRange(cfg.atr_period,MovingAverageType.WILDERS)
            link,link_reason=create_bsu_research_observer(decision,d1,tick,cfg)
            _emit('BSU',symbol=ticker,status='SOFTWARE_D1_PROXY' if link else 'UNAVAILABLE',
                  reason=link_reason,source=link.origin_time if link else None,
                  pivot=link.origin_price if link else None,cluster=link.cluster_price if link else None,
                  author_verified=False,can_trade=False)
            breakout=(BreakoutRetestObserver(symbol=ticker,session=day.date(),side=decision.side,
                level_price=decision.level.price,atr_value=a,max_confirm_chase_atr=cfg.max_entry_distance_atr,
                max_retest_bars=cfg.breakout_retest_max_bars,retest_tolerance_atr=cfg.breakout_retest_touch_atr,
                invalidation_atr=cfg.breakout_retest_invalid_atr) if decision.accepted and decision.model=='breakout' else None)
            fixed_price=link.origin_price if link else probe.price
            fixed=(FixedFloatingLimitObserver(fixed_price,side,tick)
                   if side and abs(fixed_price/tick-round(fixed_price/tick))<=1e-6 else None)
            fixed_counts=Counter(); fixed_last=None
            seen=[]; counts=Counter(); gate_counts={name:Counter() for name in GATE_IDS}
            best=None; best_rank=-1; sec_queries=0
            for native in bars:
                at=_native_et(native.end_time).to_pydatetime()
                b=Bar(at,float(native.open),float(native.high),float(native.low),float(native.close),'M5',float(native.volume))
                m5_atr.update(native)
                causal_atr=float(m5_atr.current.value) if m5_atr.is_ready else None
                if reactions is not None: counts.update(e.kind for e in reactions.observe(b,causal_atr))
                if fixed is not None:
                    fixed_last=fixed.observe(b); fixed_counts[fixed_last.status]+=1
                seen.append({'date':at,'open':b.open,'high':b.high,'low':b.low,'close':b.close,'volume':b.volume})
                if link is not None:
                    before=link.detector.state.phase
                    observed=link.detector.on_bar(b)
                    if before!=observed.phase and observed.phase in ('bpu1','bpu2_confirmed','invalidated'):
                        _emit('BPU',symbol=ticker,phase=observed.phase,at=at,reason=observed.reason,can_trade=False)
                    if observed.phase=='bpu1' and before!='bpu1' and sec_queries<2:
                        sec_queries+=1
                        try:
                            sample=_historical_second(qb,sym,at)
                            if sample is not None:
                                link.detector.observe_preclose(observed_at=sample.observed_at,bpu2_end=sample.bpu2_end,
                                  observed_low=sample.observed_low,observed_high=sample.observed_high,
                                  last_price=sample.last_price,source=sample.source,observed_since=sample.observed_since)
                        except Exception as exc:
                            _emit('HISTORICAL_SEC_BLOCKED',symbol=ticker,reason=str(exc)[:180],can_trade=False)
                if breakout is not None:
                    breakout.on_m5(at=at,open_price=b.open,high=b.high,low=b.low,close=b.close,volume=b.volume)
                if not decision.accepted: continue
                frame=pd.DataFrame(seen).set_index('date')
                market=MarketData(ticker,d1,frame,session_levels=levels,
                    breakout_retest=breakout.evidence if breakout else None,bpu_tvx=None)
                # History cannot create native OnData BpuTvxEvidence.
                report=audit_pipeline(decision,market,at,cfg,equity=cfg.starting_equity)
                for name,row in report['gates'].items():
                    value=row['passed']; gate_counts[name]['TRUE' if value is True else 'FALSE' if value is False else 'UNKNOWN']+=1
                rank=(100 if report['gates']['m5_confirmed']['passed'] is True else 0)+sum(row['passed'] is True for row in report['gates'].values())
                if rank>best_rank: best,best_rank=report,rank
            _emit('FIXED_FLOATING',symbol=ticker,scope='STRICT_LIMIT_PROXY_ONLY_NOT_UNIVERSAL_BSU',
                  price=fixed_price,side=side,status_counts=dict(fixed_counts),
                  last_status=fixed_last.status if fixed_last else ('UNAVAILABLE_OFF_GRID' if side else 'UNAVAILABLE_ROLE_AMBIGUOUS'),
                  hits=fixed_last.hits if fixed_last else None,author_verified=False,can_trade=False)
            _emit('REACTIONS_10',symbol=ticker,scope='FROZEN_LEVEL_SOFTWARE_TAGS_NOT_AUTHOR_ACCURACY',
                  counts={name:counts[name] if reactions else None for name in KINDS},
                  frozen_role=side,gap_resets=reactions.gap_resets if reactions else None,can_trade=False)
            _emit('GATES_8',symbol=ticker,counts={key:dict(value) for key,value in gate_counts.items()},
                  note='NO_CANONICAL_GATE_EVALUATION' if not decision.accepted else 'PER_BAR_COUNTS_NOT_TRADES')
            if best:
                best.pop('features',None)
                _emit('PIPELINE_EXAMPLE',**best)
            summary['symbols_completed']+=1
        except Exception as exc:
            summary['symbols_blocked']+=1
            _emit('BLOCKED',symbol=ticker,reason=type(exc).__name__+': '+str(exc)[:220],can_trade=False)
    _emit('END',summary=dict(summary),orders='DISABLED',cvd='DEFERRED_BY_OWNER',
          tvx_pass=False,author_accuracy='UNKNOWN',data_source_version='LOCAL_LEVELS_CONFIG_NOT_INDEPENDENTLY_CERTIFIED')
    return summary

run_qwct_pipeline_acceptance()
'''


def build():
    parts=[HEADER]
    for path,names in PARTS.items():
        nodes=selected_nodes(path,names)
        tree=ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[]))
        parts.append('\n# Canonical read-only subset: '+path+'\n'+ast.unparse(tree)+'\n')
    return '\n'.join(parts)+DRIVER


if __name__=='__main__':
    content=build(); ast.parse(content)
    TARGET.write_text(content,encoding='utf-8')
    print(f'Built {TARGET.name}: {len(content)} characters; one notebook cell, no broker/execution code')
