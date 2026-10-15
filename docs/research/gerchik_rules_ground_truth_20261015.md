# Gerchik BSU/BPU and trend rules: evidence audit before any strategy changes

**Date:** 2026-10-15. **Status:** PRIMARY-SOURCE REVIEW, not independently scored dataset. **Canonical Qwct rules remain frozen.**

## Sources actually checked

| Source | Supported claim | Does NOT prove |
|---|---|---|
| [Gerchik: БСУ и БПУ (2024-05-09)](https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya) | BSU can originate in prior history; BPU1 exactly retests origin (not necessarily the next bar); BPU2 is immediately after BPU1, must not exceed BPU1 extreme, may stay shy by <=20% of SL; limit TVX at -30s. | Mandatory *prior* second D1 swing for BSU creation; a specific SMA trend rule; a full US-equity trading approval. |
| [Gerchik: Инструкция для отбоя от уровня](https://gerchik.com/journal/instrukczii/otboi-ot-urovnya/) | D1 level, trade direction, available room, M5 BSU/BPU, limit before BPU2 close, stop and >=3:1. Explicitly describes **reduced risk 0.1% for countertrend trades**, versus baseline 0.2% in that example. | Blanket permission to replace Qwct `allow_countertrend=False`; valid countertrend equity BSU/BPU samples; assurance of positive expectancy. The article gives example sizing for its own trading context. |
| [Gerchik: Отбой от уровня — ВТБ (2024-08-27 publication)](https://gerchik.com/journal/instrukczii/otboi-ot-urovnya-vtb/) | A **labeled example** of bounce: symbol VTB; D1 level 0.0501; global/local **down/down**, SHORT; BPU pattern stated; entry 0.04977, stop 0.04986. | Trade's exact historical exchange-session timestamp, U.S.-equity dataset or rigorous independent machine-readable BPU annotations. **This is MOEX VTB**, not AAPL/MSFT/AMZN. |
| [Gerchik: Пробой уровня и отбой шорт — ВТБ (2024-08-27 publication)](https://gerchik.com/journal/instrukczii/proboi-urovnia-y-otboi-short-vtb/) | Local+global short and a short bounce described among two separate strategies; confirms trend context is recorded. | Independently time-stamped BPU1/BPU2 OHLC on US equities. Mixed setup article is **not** a pure positive BSU/BPU sample. |
| [Gerchik: Как правильно отбирать графики и ордера (2026-08-19)](https://gerchik.com/journal/instrukczii/domashnee-zadanie-kak-pravilno-otbirat-grafiki-i-ordera-dlya-torgovli/) | Recommends screening many charts, writing an advance trading plan, documenting separately selected trade styles; described example daily level → direction/room → BSU/BPU → limit order. | Specific universal numeric Qwct D1 cluster count, double-SMA formula, 12:00–13:30 exclusivity or expected returns. |
| [Gerchik: идеальная сделка и статистика](https://gerchik.com/journal/foreks/kak-viglyadit-idealnaya-sdelka-i-statistika-razbor-ot-aleksandra-gerchika/) | Explicitly discusses global vs local trend, advance scenario, historical levels, many qualitative trade examples; also describes examples where trends diverge. | An executable backtest ground-truth set; precise timestamp and point-in-time raw exchange ticks; its informal chart examples cannot be treated as expert-labeled US-equity benchmarks. |

## What this establishes for Qwct

1. Existing Qwct `levels.py` **2 prior confirmed D1 swings** is a **specific algorithmic/owner spec requirement**, not a direct literal requirement in the published short BSU/BPU glossary. So its difference from the published definition merits investigation, but **changing it now would fit a selected 3-case exploratory sample** and is not supported by an independent label study.
2. Original Qwct `signals.py` with `allow_countertrend=False` requires global SMA and local SMA trend both matching trade direction. Published Gerchik materials include **one against-trend risk-reduction rule** in a particular instructional example and lots of with-trend examples. This indicates countertrend is discussed in parts of the broader ecosystem, **not** that Qwct's canonical two-trend requirement is incorrect or the filter may be silently removed.
3. We still lack a **minimum 10–20 independently dated and explicitly labeled** positive/negative **U.S. stock D1+M5 BSU/BPU** references. **Do not fabricate them** from a published date, a retrospective scanner result, a generic diagram, or a different country's symbols.

## Reproducible labeling protocol (required before changing original rules)

A *genuine independent* row needs: `market`, `ticker`, `exchange_session_date`, `time_zone`, `D1_source_bar_date`, `D1_level_price`, `D1_reference_chart_URL`, `M5_BPU1_end_ET`, `M5_BPU2_end_ET`, `expected_SIDE`, `expert_label_valid_BSU_BPU`, `global_trend_rule`, `local_trend_rule`, `expert_annotation_URL`, `what_information_was_visible_before_preclose`, `ambiguity`. Annotate **before** using the algorithm's results.

- Include negative chart examples, at least one explicit failed BPU2, near-touch instead of exact, old BSU level vs recent retest, different GMT/local trends, and corporate action event.
- Keep **raw structural correctness, D1 model eligibility, risk, and execution** as distinct labels; do not equate the presence of a pivot with a trade.
- Version labels and required date/time before testing. Count **unique ticker+date+historical-level origin**, not 5-minute checks.

## One-variable-at-a-time next experiment: universe D1 audit

A new, isolated [QuantConnect Universe research project](../../research/universe_cloud/README.md) uses Qwct's **existing** `select_liquid_fundamentals`, `passes_gerchik_screener`, `levels_for_session`, `global_trend`, `trend_direction`, native `AverageTrueRange`, `SimpleMovingAverage`, and point-in-time **RAW D1 TradeBar History** to screen **up to 50 liquidity names into the existing watchlist limit 10**. It logs **how many ticker-days have approved original two-touch levels within 1 ATR and with the unchanged aligned trend**.

This first study **does not run PPHL/M5/BPU/SEC**, measure trade outcomes, change `min_touches`, enable `allow_countertrend`, or alter the existing 3-ticker Cloud BSU project. It tests *coverage of the unchanged Qwct screen*, not the frequency/profitability of complete Gerchik trading opportunities.

### Caveat on price history normalization
Research uses RAW D1. Original Qwct's dynamic warmup uses SCALED_RAW for technical indicator calculation on RAW subscriptions. Cross-study price basis is **not automatically equivalent around splits**. Log snapshot provenance and identify any split-affected ticker-days before treating differences as meaningful.
