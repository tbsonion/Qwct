# QWCT 4.1 - paste ALL this Python into ONE code cell in research.ipynb.
# Real historical LEAN Daily/Minute data, native M5 consolidation, no orders.
# Do NOT paste printed "QWCT 3.3 NATIVE SOURCE REVIEW" output as Python.
from AlgorithmImports import *
from QuantConnect.Research import QuantBook
from QuantConnect.Data.Consolidators import TradeBarConsolidator
from strategy.config import StrategyConfig
from strategy.levels import levels_for_session
from strategy.patterns_bsu import Bar, M5BsuSequenceScanner
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas as pd

ET = ZoneInfo('America/New_York')
DAY = datetime(2024, 6, 3)
TICKERS = ('AMAT', 'NFLX', 'SRPT', 'MSFT')
cfg = StrategyConfig()
qb = QuantBook()
qb.set_time_zone('America/New_York')
qb.set_start_date(2024, 7, 1)
qb.set_end_date(2024, 7, 2)


def eastern(value):
    x = pd.Timestamp(value)
    return x.tz_localize(ET) if x.tzinfo is None else x.tz_convert(ET)


for ticker in TICKERS:
    print('\n=== QWCT 4.1 NATIVE M5', ticker, '===')
    try:
        symbol = qb.add_equity(
            ticker, Resolution.MINUTE, fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW).symbol
        daily = list(qb.history[TradeBar](
            symbol, DAY - timedelta(days=335), DAY.replace(hour=9, minute=29),
            Resolution.DAILY, fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW))
        daily = [b for b in daily
                 if eastern(b.time).date() < DAY.date()
                 and not getattr(b, 'is_fill_forward', False)]
        if len(daily) < 180:
            raise ValueError(f'Only {len(daily)} closed D1 bars; need 180')
        daily = daily[-180:]

        atr = AverageTrueRange(cfg.atr_period, MovingAverageType.WILDERS)
        rows = []
        for b in daily:
            atr.update(b)
            rows.append({
                'date': eastern(b.time), 'open': float(b.open),
                'high': float(b.high), 'low': float(b.low),
                'close': float(b.close), 'volume': float(b.volume),
                f'atr{cfg.atr_period}':
                    float(atr.current.value) if atr.is_ready else float('nan'),
            })
        frame = pd.DataFrame(rows).set_index('date')
        d1_levels = levels_for_session(frame, DAY.date(), cfg)
        tick = float(qb.securities[symbol].symbol_properties.minimum_price_variation)
        scan = M5BsuSequenceScanner(
            cfg, session=DAY.date(), d1_levels=d1_levels,
            d1_atr=float(atr.current.value),
            previous_d1_close=float(frame.close.iloc[-1]),
            tick_size=tick)
        print('D1_levels=', len(d1_levels),
              'valid_M5_zones=', len(scan.zones), 'tick=', tick)

        start = DAY.replace(hour=9, minute=30)
        end = DAY.replace(hour=16, minute=0)
        minute = qb.history[TradeBar](
            symbol, start, end, Resolution.MINUTE, fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW)
        consolidator = TradeBarConsolidator(timedelta(minutes=5))
        minutes_seen = set()
        m5_bars = []

        def on_closed_m5(sender, closed):
            at = eastern(closed.end_time)
            # Reject incomplete/extended-hours/fill-forward M5 bars.
            if (at.date() != DAY.date()
                    or not (time(9, 35) <= at.time() <= time(16, 0))
                    or any(at - timedelta(minutes=k) not in minutes_seen
                           for k in range(5))
                    or float(closed.volume) <= 0):
                return
            m5_bars.append(Bar(
                ts=at.to_pydatetime(), open=float(closed.open),
                high=float(closed.high), low=float(closed.low),
                close=float(closed.close), timeframe='M5',
                volume=float(closed.volume)))

        consolidator.data_consolidated += on_closed_m5
        for minute_bar in minute:
            if not getattr(minute_bar, 'is_fill_forward', False):
                minutes_seen.add(eastern(minute_bar.end_time))
                consolidator.update(minute_bar)
        # Without a later 1m update, the full 15:55-16:00 M5 remains
        # buffered. Flush only genuine minute bars, never synthesize OHLC.
        consolidator.scan(DAY.replace(hour=16, minute=1))
        expected_minutes = [
            eastern(DAY.replace(hour=9, minute=31)) + timedelta(minutes=i)
            for i in range(390)]
        missing_1m = [x.strftime("%H:%M") for x in expected_minutes
                      if x not in minutes_seen]
        expected_m5_ends = [
            eastern(DAY.replace(hour=9, minute=35)) + timedelta(minutes=5*i)
            for i in range(78)]
        completed_ends = {eastern(b.ts) for b in m5_bars}
        missing_m5 = [x.strftime("%H:%M") for x in expected_m5_ends
                      if x not in completed_ends]
        print("QWCT 4.3 DATA AUDIT", ticker,
              "ACTUAL_1M=", len(minutes_seen), "/390",
              "COMPLETE_M5=", len(m5_bars), "/78",
              "MISSING_1M=", missing_1m[:15],
              "MISSING_M5=", missing_m5[:15])

        evidence = []
        for completed in m5_bars:
            evidence.extend(scan.observe(completed))
        print('QWCT 4.3 SUMMARY', ticker,
              'native_complete_M5=', len(m5_bars),
              'BPU1_exact=', scan.bpu1_count,
              'BPU2_closed=', scan.completed,
              'GAP_RESETS=', scan.rejected_counts.get(
                  'M5_SOURCE_CONTINUITY_GAP_RESET',0),
              'PIERCED_REJECTS=', scan.rejected_counts.get(
                  'BSU_SOURCE_PIERCED_BEFORE_BPU1',0),
              'AUTHOR_UNVERIFIED NO_ORDERS')
        for event in evidence[:20]:
            print(event.event,
                  'BSU_M5=', event.source_end,
                  'BPU1_M5=', event.bpu1_end,
                  'BPU2_M5=', event.bpu2_end,
                  'RAW_BSU_price=', event.level_price,
                  'D1_context=', event.d1_context_price,
                  'NO_ORDERS')
        if not evidence:
            print('No matching same-session M5 sequences; not proof of no BSU.')
    except Exception as exc:
        print('QWCT 4.1 ERROR', ticker, type(exc).__name__, str(exc))
        raise
