"""QWCT 3.2 read-only PIT D1 original-source provenance census.

Same 19/19 June native morning membership and 180 RAW D1 history as
QWCT 2.8, but counts EVERY D1 mirror for all 50 universe members
before Shadow cap, then audits only frozen eligible D1 origins and basis.
NO M1/M5, NO SIGNALS, NO ORDERS.
"""
from AlgorithmImports import *
from collections import Counter
from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo
import pandas as pd
from strategy.config import StrategyConfig
from strategy import select_liquid_fundamentals, passes_gerchik_screener
from strategy.levels import levels_for_session, native_cluster_tolerance, _confirmed_swings
from strategy.indicators import trend_direction, global_trend
from strategy.timing_gate import next_session_fundamentals, freeze_fundamental_event

ET=ZoneInfo("America/New_York")


def et(value):
    t=pd.Timestamp(value)
    return t.tz_localize(ET) if t.tzinfo is None else t.tz_convert(ET)


def audit_mirror(d1, level, session, swing_k, tolerance, lookback=60):
    """Return a reproducible causal D1 mirror source/breach/retest trace.

    Side must be inferred unambiguously from the ORIGINAL source bar's
    low/high proximity to the D1 cluster price; otherwise fail closed.
    An accepted mirror is still ONLY an automatic cluster-level proxy.
    """
    out = dict(status="UNKNOWN", reason="", original_kind=None,
               source=None, swing_confirm=None, breach=None,
               retest=None, valid_from=None, price=None)
    def finish(status, reason):
        out["status"], out["reason"] = status, reason
        return out
    if (getattr(level, "kind", None) != "mirror" or
            getattr(level, "source", None) != "swing_cluster"):
        return finish("SKIP", "NOT_SWING_MIRROR")
    if (d1 is None or len(d1)<2*swing_k+5 or
            not d1.index.is_unique or not d1.index.is_monotonic_increasing):
        return finish("UNKNOWN", "INVALID_D1_FRAME")
    i, j = level.first_idx, level.last_idx
    if not isinstance(swing_k,int) or swing_k<1 or not(
            swing_k<=i<j and j+swing_k<len(d1)):
        return finish("UNKNOWN", "UNCONFIRMED_SWING_WINDOW")
    price=float(level.price)
    tol=float(tolerance)
    if not all(isfinite(z) and z>0 for z in (price,tol)):
        return finish("UNKNOWN","BAD_PRICE_OR_CLUSTER_TOLERANCE")
    if level.valid_from is None or level.valid_from>session:
        return finish("UNKNOWN","NOT_VALID_BEFORE_SESSION")
    dates=[x.date() for x in d1.index]
    if (dates[-1]>=session or
            any(a>=b for a,b in zip(dates,dates[1:]))):
        return finish("UNKNOWN","D1_NOT_CAUSAL_TO_SESSION")
    source=d1.iloc[i]
    high,low=float(source["high"]),float(source["low"])
    if high<low or not all(isfinite(v) for v in (high,low)):
        return finish("UNKNOWN","INVALID_SOURCE_OHLC")
    is_high=abs(high-price)<=tol
    is_low=abs(low-price)<=tol
    if is_high==is_low:
        return finish("UNKNOWN","ORIGINAL_KIND_AMBIGUOUS")
    kind="resistance" if is_high else "support"
    last_confirm=dates[j+swing_k]
    base_from=last_confirm+timedelta(days=1)
    if (level.formed_at!=dates[j] or
            level.valid_from<=last_confirm):
        return finish("UNKNOWN","LEVEL_CHRONOLOGY_MISMATCH")
    out.update(original_kind=kind,source=str(dates[i]),
               swing_confirm=str(last_confirm),
               price=price,valid_from=str(level.valid_from))
    start=max(j+1,len(d1)-lookback,1)
    while start<len(d1) and dates[start]<base_from:
        start+=1
    breached=None
    for idx in range(start,len(d1)):
        b=d1.iloc[idx]
        if kind=="support":
            confirmed=(breached is not None and float(b["high"])>=price
                       and float(b["close"])<price)
            if not confirmed and float(b["close"])<price and breached is None:
                breached=idx
        else:
            confirmed=(breached is not None and float(b["low"])<=price
                       and float(b["close"])>price)
            if not confirmed and float(b["close"])>price and breached is None:
                breached=idx
        if confirmed:
            out["breach"]=str(dates[breached])
            out["retest"]=str(dates[idx])
            if dates[idx]+timedelta(days=1)!=level.valid_from:
                return finish("UNKNOWN","RETEST_DATE_DISAGREES_WITH_VALID_FROM")
            return finish("PROXY_VERIFIED","CLOSED_D1_BREACH_RETEST_ASOF")
    return finish("UNKNOWN","NO_SEPARATE_CAUSAL_BREACH_AND_RETEST")


def mirror_gates(lvl, proof, close, atr, gt, lt, cfg, stage2):
    """Original morning Stage2, strength, near, trend and inferred mirror side.

    Counts software mirror PROXIES, never manual BSU/BPU. No threshold changes.
    """
    price=float(lvl.price)
    good_atr=isfinite(float(atr)) and float(atr)>0
    distance=(abs(price-close)/atr if good_atr else float("inf"))
    side="short" if price>=close else "long"
    kind=proof["original_kind"]
    new_role=("resistance" if kind=="support" else
              "support" if kind=="resistance" else "UNKNOWN")
    role_ok=(new_role=="resistance" and side=="short" or
             new_role=="support" and side=="long")
    trend_ok=gt==lt==(1 if side=="long" else -1)
    strong=(lvl.touches>=cfg.min_touches and
            lvl.strength>=cfg.min_level_strength)
    near=good_atr and distance<=cfg.level_proximity_atr
    causal=proof["status"]=="PROXY_VERIFIED"
    eligible=bool(stage2 and strong and near and role_ok and trend_ok and causal)
    return dict(stage2=bool(stage2),strength=bool(strong),
                near=bool(near),role=bool(role_ok),trend=bool(trend_ok),
                causal=bool(causal),eligible=eligible,
                distance_atr=distance,side=side,new_role=new_role)



def native_source_audit(d1, lvl, proof, scaled, tick, cfg):
    """Strict independently confirmed ORIGINAL swing, grid, RAW/SCALED D1.

    Frozen morning RAW D1 vs separately observed as-of SCALED_RAW D1.
    Historical quote/subcent warnings are not claims of bad market data.
    """
    out=dict(origin=None,origin_day=None,last_swing_day=None,
             original_kind=proof.get("original_kind"),field=None,
             raw_grid="UNKNOWN",basis="UNKNOWN",status="UNKNOWN",
             scaled_origin=None,scaled_last=None,median_ticks=None,
             source_key=None,raw_delta=None)
    kind=out["original_kind"]
    if proof.get("status")!="PROXY_VERIFIED" or kind not in ("support","resistance"):
        out["status"]="CAUSAL_MIRROR_PROOF_UNVERIFIED"
        return out
    i,j=lvl.first_idx,lvl.last_idx
    k=cfg.swing_k
    if not (k<=i<j and j+k<len(d1) and
            d1.index.is_unique and d1.index.is_monotonic_increasing):
        out["status"]="INVALID_CONFIRMED_SOURCE_INDICES"
        return out
    field="high" if kind=="resistance" else "low"
    swings=_confirmed_swings(d1,k)[0 if field=="high" else 1]
    confirmations={n:c for n,_,c in swings}
    if (i not in confirmations or j not in confirmations or
            confirmations[j]!=d1.index[j+k].date() or
            str(d1.index[i].date())!=proof.get("source") or
            lvl.formed_at!=d1.index[j].date()):
        out["status"]="SOURCE_NOT_CONFIRMED_IN_NATIVE_D1"
        return out
    origin=float(d1.iloc[i][field])
    median=float(lvl.price)
    last_close=float(d1.iloc[-1]["close"])
    if not all(isfinite(x) and x>0 for x in (origin,median,last_close)):
        out["status"]="BAD_RAW_SOURCE_OR_PRICE"
        return out
    out.update(origin=origin,origin_day=str(d1.index[i].date()),
               last_swing_day=str(d1.index[j].date()),
               field=field,raw_delta=median-origin,status="RAW_SOURCE_CONFIRMED")
    out["source_key"]="|".join((
        kind,str(d1.index[i].date()),str(d1.index[j].date()),
        str(lvl.valid_from),f"{origin:.8f}"))
    try:
        tick=float(tick)
        if not isfinite(tick) or tick<=0:
            raise ValueError("missing positive tick")
    except (ValueError,TypeError,OverflowError):
        out["status"]="NATIVE_TICK_UNKNOWN"
        return out
    out["raw_grid"]=("ON_GRID" if abs(origin-round(origin/tick)*tick)<=tick*1e-5
                     else "OFF_GRID")
    out["median_ticks"]=(median-origin)/tick
    if scaled is None or not scaled:
        out["basis"]="UNKNOWN_SCALED_HISTORY"
        return out
    source_day=d1.index[i].date()
    latest_day=d1.index[-1].date()
    # All scaled bars were already checked as before 09:29 and strictly ordered.
    by_day={et(b.time).date():b for b in scaled}
    if source_day not in by_day or latest_day not in by_day:
        out["basis"]="UNKNOWN_ORIGIN_OR_LATEST_MISSING"
        return out
    source_bar,last_bar=by_day[source_day],by_day[latest_day]
    if (et(source_bar.end_time)!=et(d1.iloc[i]["bar_end"]) or
            et(last_bar.end_time)!=et(d1.iloc[-1]["bar_end"])):
        out["basis"]="UNKNOWN_ENDTIME_MISMATCH"
        return out
    if (getattr(source_bar,"is_fill_forward",False) or
            getattr(last_bar,"is_fill_forward",False)):
        out["basis"]="UNKNOWN_FILL_FORWARD_SCALED"
        return out
    so,sl=float(getattr(source_bar,field)),float(last_bar.close)
    out.update(scaled_origin=so,scaled_last=sl)
    if not all(isfinite(x) and x>0 for x in (so,sl)):
        out["basis"]="UNKNOWN_BAD_SCALED_PRICES"
        return out
    half=tick/2+tick*1e-7
    out["basis"]=("LATEST_CLOSE_DIFFERENCE" if abs(sl-last_close)>half else
                  "REBASED_SOURCE_HISTORY" if abs(so-origin)>half else
                  "MATCH")
    return out

class QwctSourceCensus(QCAlgorithm):
    """One census of actual frozen LEAN Fundamental50 sessions; no trades."""

    def initialize(self):
        start=datetime.strptime(
            self.get_parameter("scan_start") or "2024-06-01","%Y-%m-%d")
        end=datetime.strptime(
            self.get_parameter("scan_end") or "2024-06-30","%Y-%m-%d")
        if end<start or (end-start).days>35:
            raise ValueError("Census date range must be <=35 days")
        self.set_start_date(start.year,start.month,start.day)
        self.set_end_date(end.year,end.month,end.day)
        self.set_time_zone("America/New_York")
        self.set_cash(25000)
        self.cfg=StrategyConfig()
        self.timing_mode=(self.get_parameter("timing_mode") or "next_session").lower()
        if self.timing_mode not in ("next_session","strict"):
            raise ValueError("timing_mode must be next_session or strict")
        self.universe_settings.resolution=Resolution.DAILY
        self.universe_settings.fill_forward=False
        self.universe_settings.asynchronous=False
        self.universe_settings.data_normalization_mode=DataNormalizationMode.RAW
        self.by_day={}
        self.callback_at={}
        self.callback_events=[]
        self.scanned=set()
        self.count=Counter()
        self.reject=Counter()
        self.near_examples=[]
        self.ready_examples=[]
        self.source_count=Counter()
        self.source_groups={}
        self.source_records=0
        self.source_samples={}
        self.anchor=self.add_equity(
            "SPY",Resolution.MINUTE,fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW).symbol
        self.add_universe(self._select)
        self.schedule.on(
            self.date_rules.every_day(self.anchor),
            self.time_rules.before_market_open(self.anchor,1),self._prepare)
        self.debug(
            f"QWCT 3.2 SOURCE CENSUS ACTIVE {start.date()}..{end.date()} "
            f"timing={self.timing_mode}; Fundamental50 PIT RAW D1 180; "
            "ALL MEMBERS BEFORE SHADOW CAP; NO M1/M5 NO ORDERS")

    def _select(self, fundamentals):
        at=et(self.time)
        event=freeze_fundamental_event(
            fundamentals,self.cfg,at,select_liquid_fundamentals,et)
        day=at.date()
        self.by_day[day]=event["symbols"]
        self.callback_at[day]=at
        self.callback_events.append(event)
        self.count["callbacks"]+=1
        if day.weekday()>=5:
            self.count["weekend_callbacks"]+=1
        return event["symbols"]

    def _daily_history(self, symbols, day):
        # Copied from validated 2.8 D1 native source request; no daily future bars.
        bucket={sym:[] for sym in symbols}
        for packet in self.history[TradeBar](
                list(symbols),180,Resolution.DAILY,fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW):
            for sym,bar in packet.items():
                if sym not in bucket:
                    continue
                begin,end=et(bar.time),et(bar.end_time)
                if (begin.date()>=day or end.date()>=day
                        or end<=begin or (bucket[sym] and
                        begin<=et(bucket[sym][-1].time))):
                    bucket[sym]=None
                    continue
                if bucket[sym] is not None:
                    bucket[sym].append(bar)
        return bucket


    def _scaled_daily_history(self,symbols,day):
        """One native as-of batch, only symbols with eligible mirror proxies."""
        bucket={sym:[] for sym in symbols}
        for packet in self.history[TradeBar](
                list(symbols),180,Resolution.DAILY,fill_forward=False,
                data_normalization_mode=DataNormalizationMode.SCALED_RAW):
            for sym,bar in packet.items():
                if sym not in bucket:
                    continue
                begin,end=et(bar.time),et(bar.end_time)
                if (begin.date()>=day or end.date()>=day
                        or end<=begin or (bucket[sym] and
                        begin<=et(bucket[sym][-1].time))):
                    bucket[sym]=None
                    continue
                if bucket[sym] is not None:
                    bucket[sym].append(bar)
        return bucket

    def _native_frame(self,raw,day):
        # Same LEAN Wilder ATR, 50-day SMA and 20-day volume SMA as 2.8.
        if raw is None or len(raw)<60:
            raise ValueError("D1_INSUFFICIENT_CLOSED_RAW")
        atr=AverageTrueRange(self.cfg.atr_period,MovingAverageType.WILDERS)
        sma=SimpleMovingAverage(self.cfg.trend_sma)
        volume=SimpleMovingAverage(self.cfg.volume_lookback_days)
        rows,days,seen=[],[],set()
        for bar in raw:
            start,end=et(bar.time),et(bar.end_time)
            if (start.date() in seen or start.date()>=day
                    or end.date()>=day or end<=start):
                raise ValueError("D1_DUPLICATE_OR_NONCAUSAL")
            seen.add(start.date())
            atr.update(bar)
            sma.update(bar.end_time,bar.close)
            volume.update(bar.end_time,bar.volume)
            rows.append({
                "open":float(bar.open),"high":float(bar.high),
                "low":float(bar.low),"close":float(bar.close),
                "volume":float(bar.volume),"bar_end":end,
                f"atr{self.cfg.atr_period}":(
                    float(atr.current.value) if atr.is_ready else float("nan")),
                f"sma{self.cfg.trend_sma}":(
                    float(sma.current.value) if sma.is_ready else float("nan")),
                "volume_sma":(
                    float(volume.current.value) if volume.is_ready else float("nan"))
            })
            days.append(start.normalize())
        return pd.DataFrame(rows,index=pd.DatetimeIndex(days))

    def _prepare(self):
        day=et(self.time).date()
        if day in self.scanned:
            return
        self.scanned.add(day)
        self.count["scans"]+=1
        members=self.by_day.get(day)
        label="SAME_DAY"
        if day not in self.by_day and self.timing_mode=="next_session":
            event,reason=next_session_fundamentals(
                self.callback_events,et(self.time),
                self.securities[self.anchor].exchange.hours,et)
            if event is not None:
                members=event["symbols"]
                label="NEXT_SESSION"
                self.count["next_days"]+=1
                self.log(f"QWCT MIRROR TIMING VERIFIED {day} "
                         f"callback={event['at']} members={len(members)}")
            else:
                self.reject[reason]+=1
        if not members or (label=="SAME_DAY" and
                           self.callback_at[day]>et(self.time)):
            self.reject["NO_VERIFIED_FUNDAMENTAL_SELECTION"]+=1
            self.log(f"QWCT MIRROR SKIP {day} NO_VERIFIED_SELECTION")
            return
        if label=="SAME_DAY":
            self.count["strict_days"]+=1
        self.count["days"]+=1
        self.count["stock_days"]+=len(members)
        try:
            bucket=self._daily_history(members,day)
        except Exception as exc:
            self.reject["D1_REQUEST:"+str(exc)[:55]]+=1
            return
        daymirrors=0
        daynear=0
        dayready=0
        ready_records=[]
        ready_frames={}
        for sym in members:
            try:
                d1=self._native_frame(bucket[sym],day)
                self.count["d1_ready"]+=1
                last=d1.iloc[-1]
                close=float(last["close"])
                atr=float(last[f"atr{self.cfg.atr_period}"])
                volume=float(last["volume_sma"])
                stage2=passes_gerchik_screener(close,atr,volume,self.cfg)
                if stage2:
                    self.count["stage2"]+=1
                levels=levels_for_session(d1,day,self.cfg)
                mirrors=[lvl for lvl in levels if (
                    lvl.kind=="mirror" and lvl.source=="swing_cluster"
                    and lvl.valid_from is not None and lvl.valid_from<=day)]
                if mirrors:
                    self.count["mirror_stock_days"]+=1
                daymirrors+=len(mirrors)
                self.count["mirrors"]+=len(mirrors)
                if not mirrors:
                    continue
                tol=native_cluster_tolerance(d1,self.cfg)
                if tol is None:
                    self.reject["NATIVE_D1_ATR_CLUSTER_TOL_MISSING"]+=len(mirrors)
                    continue
                gt=global_trend(d1,len(d1)-1,self.cfg)
                lt=trend_direction(d1,len(d1)-1,self.cfg)
                for lvl in mirrors:
                    proof=audit_mirror(
                        d1,lvl,day,self.cfg.swing_k,tol,self.cfg.mirror_lookback)
                    gates=mirror_gates(lvl,proof,close,atr,gt,lt,self.cfg,stage2)
                    for name in ("causal","stage2","strength","near","role","trend"):
                        self.count["gate_"+name]+=int(gates[name])
                    # Funnel: count cases meeting all PRECEDING original gates,
                    # not marginal near histograms mistaken for approved signals.
                    a=bool(stage2)
                    for name in ("strength","near","role","trend","causal"):
                        a=a and gates[name]
                        self.count["funnel_"+name]+=int(a)
                    if gates["near"]:
                        daynear+=1
                        if len(self.near_examples)<40:
                            self.near_examples.append(
                                f"QWCT MIRROR NEAR {day} {sym.value} "
                                f"price={lvl.price:.4f} close={close:.4f} "
                                f"atr={atr:.4f} dATR={gates['distance_atr']:.3f} "
                                f"role={gates['new_role']} side={gates['side']} "
                                f"stage2={int(gates['stage2'])} "
                                f"strong={int(gates['strength'])} "
                                f"role_ok={int(gates['role'])} "
                                f"trend_ok={int(gates['trend'])} "
                                f"asof={lvl.valid_from} "
                                f"audit={proof['status']}; NOT BPU1")
                    if gates["eligible"]:
                        ready_records.append((sym,lvl,proof,gates))
                        ready_frames[sym]=d1
                        self.count["mirror_ready"]+=1
                        dayready+=1
                        self.ready_examples.append(
                            f"QWCT MIRROR READY {day} {sym.value} "
                            f"level={lvl.price:.4f} dATR={gates['distance_atr']:.3f} "
                            f"side={gates['side']} role={gates['new_role']} "
                            f"source={proof['source']} valid_from={lvl.valid_from} "
                            "RESEARCH ONLY / NO ORDERS")
                    elif not gates["causal"]:
                        self.reject["MIRROR_PROVENANCE:"+proof["reason"][:44]]+=1
            except Exception as exc:
                self.reject["RAW_D1:"+str(exc)[:55]]+=1

        # RAW source is inspected ONLY for original 3.0-eligible D1 records.
        # Any missing SCALED_RAW data stays UNKNOWN, never a missing record.
        scaled={}
        if ready_records:
            try:
                scaled=self._scaled_daily_history(list(ready_frames),day)
            except Exception as exc:
                self.reject["SCALED_D1_REQUEST:"+str(exc)[:55]]+=1
        for sym,lvl,proof,gates in ready_records:
            try:
                tick=float(
                    self.securities[sym].symbol_properties.minimum_price_variation)
            except Exception:
                tick=None
            try:
                info=native_source_audit(
                    ready_frames[sym],lvl,proof,scaled.get(sym),tick,self.cfg)
            except Exception as exc:
                self.reject["SOURCE_AUDIT_EXCEPTION:"+str(exc)[:46]]+=1
                info=dict(status="UNKNOWN_EXCEPTION",raw_grid="UNKNOWN",
                          basis="UNKNOWN_EXCEPTION",origin=None,
                          origin_day=None,last_swing_day=None,raw_delta=None,
                          median_ticks=None,source_key=None,
                          original_kind=None,field=None,
                          scaled_origin=None,scaled_last=None)
            self.source_records+=1
            self.source_count["status_"+info["status"]]+=1
            self.source_count["grid_"+info["raw_grid"]]+=1
            self.source_count["basis_"+info["basis"]]+=1
            consistent=bool(info["status"]=="RAW_SOURCE_CONFIRMED"
                            and info["raw_grid"]=="ON_GRID"
                            and info["basis"]=="MATCH")
            self.source_count["source_consistent"]+=int(consistent)
            if info["source_key"] is not None:
                key=sym.value+"|"+info["source_key"]
                if key not in self.source_groups:
                    self.source_groups[key]=dict(count=0,prices=set(),
                                                 days=set())
                group=self.source_groups[key]
                group["count"]+=1
                group["days"].add(str(day))
                group["prices"].add(round(float(lvl.price),8))
            # QC Free logs are capped at 10KB PER BACKTEST. Never log every
            # source record: 92 multi-column rows hide end-of-run summaries.
            # Keep up to TWO reproducible examples per *exception category*
            # and report authoritative counts at on_end_of_algorithm.
            category=("OFF_GRID" if info["raw_grid"]=="OFF_GRID" else
                      "REBASED" if info["basis"]=="REBASED_SOURCE_HISTORY" else
                      "UNKNOWN" if (info["status"]!="RAW_SOURCE_CONFIRMED" or
                                    info["raw_grid"]=="UNKNOWN" or
                                    info["basis"] not in ("MATCH",
                                                         "REBASED_SOURCE_HISTORY"))
                      else "MATCH_ON_GRID")
            samples=self.source_samples.setdefault(category,[])
            if len(samples)<2:
                samples.append(
                    f"QWCT 3.2 SAMPLE {category} {day} {sym.value} "
                    f"origin={info['origin']} cluster={lvl.price:.4f} "
                    f"grid={info['raw_grid']} basis={info['basis']} "
                    f"state={info['status']} "
                    f"origin_day={info['origin_day']}; NO ORDERS")

        self.log(f"QWCT MIRROR DAY {day} members={len(members)} "
                 f"mirrors={daymirrors} near={daynear} ready={dayready}; "
                 "SOURCE ONLY NO ORDERS")

    def on_end_of_algorithm(self):
        self.log(
            "QWCT MIRROR SUMMARY "
            f"scans={self.count['scans']} callbacks={self.count['callbacks']} "
            f"weekend_callbacks={self.count['weekend_callbacks']} "
            f"days={self.count['days']} strict_days={self.count['strict_days']} "
            f"next_days={self.count['next_days']} "
            f"stock_days={self.count['stock_days']} "
            f"d1_ready={self.count['d1_ready']} stage2={self.count['stage2']} "
            f"mirror_stock_days={self.count['mirror_stock_days']} "
            f"mirrors={self.count['mirrors']} "
            f"eligible_proxies={self.count['mirror_ready']}; NO ORDERS")
        self.log(
            "QWCT MIRROR GATES "
            f"causal={self.count['gate_causal']} "
            f"stage2={self.count['gate_stage2']} "
            f"strong={self.count['gate_strength']} "
            f"near={self.count['gate_near']} "
            f"role={self.count['gate_role']} "
            f"trend={self.count['gate_trend']} "
            f"f_strong={self.count['funnel_strength']} "
            f"f_near={self.count['funnel_near']} "
            f"f_role={self.count['funnel_role']} "
            f"f_trend={self.count['funnel_trend']} "
            f"f_causal={self.count['funnel_causal']}; "
            "RESEARCH ONLY NOT BPU1/TVX")

        groups=self.source_groups
        seen=sum(g["count"] for g in groups.values())
        self.log(
            "QWCT 3.2 SOURCE SUMMARY "
            f"ready_from_3_0={self.count['mirror_ready']} "
            f"records={self.source_records} "
            f"native_raw_confirmed={self.source_count['status_RAW_SOURCE_CONFIRMED']} "
            f"grid_on={self.source_count['grid_ON_GRID']} "
            f"grid_off={self.source_count['grid_OFF_GRID']} "
            f"basis_match={self.source_count['basis_MATCH']} "
            f"basis_rebased={self.source_count['basis_REBASED_SOURCE_HISTORY']} "
            f"basis_latest_difference={self.source_count['basis_LATEST_CLOSE_DIFFERENCE']} "
            f"source_consistent={self.source_count['source_consistent']} "
            f"distinct_source_lineages={len(groups)} "
            f"repeat_level_days={seen-len(groups)} "
            f"median_drift_lineages={sum(len(g['prices'])>1 for g in groups.values())}; "
            "NOT CERTIFIED BSU / NO M1/M5 / NO ORDERS")
        self.log("QWCT 3.2 SOURCE STATUS "+str({
            "source":{k:v for k,v in self.source_count.items()
                      if k.startswith("status_")},
            "grid":{k:v for k,v in self.source_count.items()
                    if k.startswith("grid_")},
            "basis":{k:v for k,v in self.source_count.items()
                     if k.startswith("basis_")}}))
        self.log(
            "QWCT 3.2 SOURCE CONSISTENCY "
            f"ready_records_match={int(self.source_records==self.count['mirror_ready'])} "
            f"unique_group_records={seen} "
            f"seen_matches_confirmed_sources={int(seen==self.source_count['status_RAW_SOURCE_CONFIRMED'])}; "
            "no inferred trades or tick executions")

        self.log(f"QWCT MIRROR REJECTS {dict(self.reject.most_common(16))}")
        # Never replay 40 near + 50 ready examples in QC Free 10KB logs.
        for category in ("OFF_GRID","REBASED","UNKNOWN","MATCH_ON_GRID"):
            for row in self.source_samples.get(category,[]):
                self.log(row)
        self.log(f"QWCT MIRROR OUTPUT near_samples={len(self.near_examples)} "
                 f"ready_total={len(self.ready_examples)} "
                 "individual_records_suppressed_due_to_10KB_LOG_LIMIT; NO ORDERS")
