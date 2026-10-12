# Qwct — Deep Research: какие готовые решения УЖЕ есть в LEAN

**Дата:** 2026-10-12 · **Тип:** research / архитектурное решение, **НЕ** реализация и **НЕ** новое подтверждение Cloud.  
**Проект:** `tbsonion/Qwct`, QuantConnect Free, исходные правила: [strategy_spec](strategy_spec.md).  
**Режим:** `SIGNAL ONLY — ALL ORDERS DISABLED`. Реальный пользовательский Cloud backtest: 6 D1 setups, 456 M5 checks, 0 BPU1, 0 research candidates, 0 trade intents, 0 errors.

## Executive conclusion

**Не нужно строить собственные market feed, corporate-action engine, ATR/SMA, RVOL, swing-pivot indicator, риск-фреймворк, торговый OMS или генератор отчётов о сделках.** В официальном LEAN уже есть компоненты. Часть из них служит *готовым входом/эталоном для сравнения*, а не заменяет правила Герчика. **Готового проверенного полного BSU→BPU1→BPU2→TVX, полностью безопасного для Schwab partial-limit-fill, в подтверждённых источниках не найдено.**

Важная новая находка: **LEAN имеет официальный встроенный `RelativeDailyVolume`/`rdv()` и `PivotPointsHighLow`/`pphl()`**. Перед созданием очередного собственного индикатора эти реализации надо прогнать side-by-side против существующих Qwct research функций.

## Сравнение «готово / использовать / НЕ копировать вслепую»

| Блок | Готовое нативное решение | Что делать с Qwct | Степень готовности |
| --- | --- | --- | --- |
| D1/M5 данные/консолидация | `add_universe`, `History[TradeBar]`, `consolidate`, native `TradeBar.EndTime` | **Оставить** существующий LEAN-пайплайн, не писать альтернативный feed | Готовый движок; в Qwct Cloud minute подтверждён |
| Нормализация и splits | `RAW` подписки, `SCALED_RAW` исторический warmup, `History[Split]`, `Slice.splits`, LEAN-native split handling | **Использовать готовый механизм**. Разнести *tradable RAW-pivot OHLC* и *SCALED_RAW-indicator warmup*, **только после Cloud сопоставления**. Не округлять `SCALED_RAW` pivot под $0.01 | API готов, BSU reconciliation НЕ готов |
| Поиск D1 pivot | **`pphl(symbol,...)` — PivotPointsHighLow** | Сделать независимый comparator на тех же **закрытых D1**, проверить lookahead/подтверждение. Qwct swing clusters/mirror/BSU provenance сами по себе не заменить `pphl` | Готовый индикатор, **не** доказанная замена Герчику |
| Границы диапазонов | **`dch` — DonchianChannel**, `zig_zag` (только при подтверждении доступной сигнатуры) | Использовать как benchmark / baseline экстремумов и накопления, не как самостоятельный сигнал | Готовые индикаторы, не стратегия |
| Выбор бумаг | **Fundamental universe + `SelectionData` + indicator warmup**, native volume/dollar-volume/price | Qwct 50→10 уже есть; сравнить coverage и влияние ограничения на found scenarios. Нельзя брать 09:35 activity в скринер на 09:29 | Готовый механизм, политика отбора ограничена |
| **RVOL** | **`rdv(symbol,14)` — built-in RelativeDailyVolume** | Первый кандидат на повторное использование **вместо нового RVOL-движка**. Отдельный Qwct `opening_volume_research.py` оставить comparator и проверить: значения на **09:35** = объём 09:30–09:35 / среднее этой же пятиминутки за 14 отдельных сессий. RDV по определению **кумулятивный**: после 09:35 НЕ равен RVOL одной M5 свечи; сравнивать только при одинаковых cutoffs, regular-hours и split-volume basis | Готовый индикатор; подключение/Qwct-equivalence НЕ проверено |
| TVX за -30 сек | `Resolution.SECOND`, native `TradeBar` / `QuoteBar`, `OnData` | Готова подача секунды, **НЕ** готов detector Герчика. Qwct observer оставить; короткий Cloud smoke `tvx_seconds=true`; не восстанавливать :30 из future closed M5 | API поддерживает SEC; entitlement/data/runtime в этом аккаунте НЕ проверены |
| Корректность спреда | US Equity native second/minute `QuoteBar`, bid/ask, official `EquityFillModel` | Дополнить независимым as-of spread preflight; trade OHLC не раскрывает ask/bid | Готов источник котировок при наличии соответствующих данных; не протестирован |
| Модель исполнения и издержек | `EquityFillModel`, `ConstantSlippageModel`, **`VolumeShareSlippageModel`**, brokerage fee model | При **будущем** backtest with orders учитывать fees/slippage; не приписывать нулевое проскальзывание живым сделкам. Сейчас Qwct без ордеров | Готово для исследования, результаты не получены |
| Шорты / borrow | `InteractiveBrokersShortableProvider`, `ShortMarginInterestRateModel`, dataset **US Equities Short Availability** | Dataset/provider проверить по лицензии и совпадению с **Schwab**, IB borrow availability ≠ Schwab availability | Есть опциональный нативный источник; **Schwab borrow NOT validated** |
| Portfolio risk | `MaximumDrawdownPercentPortfolio`, `MaximumDrawdownPercentPerSecurity`, `CompositeRiskManagementModel`, native `Portfolio/Transactions` | Использовать как *reference/comparator*, **НЕ замену** $50/trade + дневной/недельный/месячный лимит + 3 потери + 2L1W + резерв стопов. Фреймворк таргет-ориентированный; встроенный portfolio drawdown не знает именно эти правила | Частичные готовые модели; полный Qwct risk policy **нет** |
| Limit/TP/SL/EOD | `OrderTicket`, `OnOrderEvent`, `Transactions`, `Schedule`, `Exchange.Hours`; **native Bracket Orders/OTO/OCO** | **Не** писать software OMS/OCO. Самый опасный разрыв: `Bracket` включает children **только после полного fill entry**; Schwab запрещает обновление contingent set. При **partial fill** стоп может быть неактивным. Требуется отдельная проверенная модель до торгов | API готов, защита при partial fill **не доказана** |
| Торговые журналы | QuantConnect Backtest **Download Results JSON / Download Orders CSV / Download Trades CSV**, LEAN `OnOrderEvent` и `TradeBuilder` | **Использовать встроенный экспорт реальных orders/trades**; для rejected signals/gates необходим отдельно определённый audit trail. На **Free** ObjectStore не допускает записи. Не считать summary полноценным журналом | Trade export готов **после появления реальных backtest orders**; Qwct decision dump — нет |
| Локальная отладка | **LEAN CLI Docker** + local results, официальная библиотека Lean | Альтернатива для масштабных тестов, если оправданы подписки. **CLI требует paid organization**, для локальных backtests — собственные лицензированные данные, не «бесплатный обход Cloud» | Доступно с затратами / не первоочередно |
| ORB / Stocks-in-Play | **Официальная опубликованная ORB стратегия Derek Melchin (Dec 2024)**, multi-stock + opening RVOL | Готовый **независимый benchmark**, **не Gerchik**. Не копировать чужой Sharpe: в обсуждении разные Python/C# реализации давали разные результаты из-за ATR frequency | Исследовательский comparator, не сертифицированная прибыльность Qwct |

## P0: Наиболее важное готовое решение — RAW History для точных уровней + SCALED_RAW для warmup

### Что доказано официально

- `RAW` содержит **исторические реальные trade prices** до корректировки; подписки в Qwct уже `RAW`.
- `SCALED_RAW` для `History` пересчитывает прошлые цены по **известным к моменту запроса** split/dividend событиям, чтобы индикаторы могли прогреваться рядом с RAW-подпиской. Из-за дробных факторов старые D1 highs/lows **не обязаны попадать на $0.01 grid**, даже если *исходный биржевой экстремум* был ровно $0.01.
- LEAN поддерживает два отдельных запроса `History[TradeBar](..., data_normalization_mode=...)`, `History[Split]` и native split rewarm. Поэтому **мы можем измерить** разницу между tradable RAW pivot и SCALED_RAW pivot. **Это рабочая гипотеза исследования, а не готовая починка:** если split произошёл *внутри* lookback, RAW старые/новые цены относятся к разному числу акций, поэтому просто заменить все D1 на RAW опасно.
- NVDA в последнем Cloud: median 502.5744 и блокировка `BSU historical origin off native tick grid`. **Median и raw `origin_price` — разные величины**; пока RAW origin не распечатан, нельзя объявлять проблемой 0.0044 между median и ближайшим центом. Известны дивиденды NVDA в 2023, поэтому factor distortion **правдоподобен**, но **не доказан именно для pivot**.

### Самый короткий нативный эксперимент DR-01 (без изменения правил стратегии)

Для **NVDA, as-of 2024-01-02 09:29 ET** вывести:
`symbol`, `origin_date`, `origin_end`, `RAW original high/low`, `SCALED_RAW original high/low`, `cluster median`, `minimum_price_variation`, `normalized tick error`, `observed RAW M5 high/low`, `ATR source/mode`, `History[Split]` за lookback. Отдельно испытать период **с корпоративным сплитом** в lookback; никакого lookahead.

**Pass:** источник дробного off-grid установлен, итоговый D1 pivot и M5 проверяются в одной as-of-share-basis, exact-tick sensitivity и отсутствие fabricated BPU1 гарантированы unit + real Cloud. **Fail:** если basis не подтверждена — BSU остаётся заблокированным.

## Плюс два решения, которые мы упускали

### DR-02: Уже готов LEAN `RelativeDailyVolume`

В официальной документации [Relative Daily Volume] указано: текущий *кумулятивный* объём с открытия / средний кумулятивный объём к **тому же времени дня** за N сессий. В 09:35 регулярной сессии это **кандидат** на эквивалент опубликованного ORB `first 5m volume / mean first 5m volume of prior 14 sessions`, но не гарантия идентичности (pre/postmarket, 14 business sessions, warmup, split-adjusted volume, time-zone, incomplete bars). Нужна parity-test against `strategy/opening_volume_research.py`; только затем подключать после 09:35. Не копировать `rv[o]l` скрипты со сторонних сайтов.

### DR-03: Уже готов LEAN `PivotPointsHighLow`

Нативный pivot indicator можно использовать как **базовую независимую метку swing**. Но D1 BSU включает много касаний, происхождение, зеркальность, infected zones и дискретионную силу уровня. `PPHL` выдаёт pivot points, **не** полный Gerchik scenario. Проводим side-by-side на закрытых D1 и вручную размеченных примерах, а не замену ради меньшего количества строк.

## Опасная часть: Bracket + Schwab — готовый API НЕ означает «защищённая сделка»

**Факт из документации QuantConnect:**
1. `bracket_order` активирует stop-loss / take-profit только при **полном** исполнении parent entry.
2. `OTO` тоже срабатывает при **полном** parent fill, `OUO` обновляет объёмы по partial-fill. LEAN поддерживает типы в принципе.
3. Schwab поддерживает contingent sets, **не поддерживает OUO и обновление ордеров в группе**; набор нужно отменять и выставлять заново.
4. Следовательно, «послал limit+bracket ⇒ любой частичный fill сразу под стопом» — **ложное утверждение**. Не писать собственную software OCO и не включать ордера до отдельного интеграционного/бумажного теста, который докажет защиту и отмены.

Это настоящая P0 угроза перед execution, даже если BSU/M5 будут исправлены.

## Проверка готовой ORB как независимого benchmark

Публикация QuantConnect (Derek Melchin, 2024) содержит воспроизводимый **иной** подход: до 1,000 ликвидных US equities, opening 5-minute RVOL за 14 прошлых дней, top-20 stocks in play, native ATR/stop, EOD. Опубликован Sharpe ~2.4 на авторском бэктесте, но в комментариях сообщается о расхождениях Python/C# из-за неверной частоты ATR и слабых периодах. **Не переносить результаты на Герчика** и не обещать %/месяц. Польза — сверить native universe/volume/time/ATR алгоритмически; Qwct не должен превращаться в ORB.

## Рекомендуемое следующее действие

| Порядок | Эксперимент | Код для заимствования | Решение |
| --- | --- | --- | --- |
| **1** | Cloud compare RAW vs SCALED_RAW NVDA original swing & native M5 | **Только официальные History modes, Split** | Исправляем tick basis строго, если доказано |
| **2** | Parallel `pphl` benchmark против `levels.py` на размеченных свечах | Native **PivotPointsHighLow** | Пригодность или отказ; избежать изобретения индикатора |
| **3** | Parallel `rdv(symbol,14)` vs current opening-volume comparator at 09:35 | Native **RelativeDailyVolume** | Подключать лишь после parity/pass |
| **4** | SEC 30s short test (10 stocks max, короткий horizon) | Native **Resolution.SECOND**, `OnData` | Подтвердить data entitlement и timestamps |
| **5** | Portfolio drawdown/native position/order ledger + Schwab partial-fill matrix | Native risk models, Tickets/OrderEvents, broker docs | Достаточно доказательств для будущей бумажной торговли? Пока нет |

**Решение по архитектуре:** сохранить Qwct в **Python LEAN**, **никакой замены на Backtrader/Zipline/самодельный брокер**, не импортировать непроверенные «готовые Герчик боты». Публично подтверждённого репозитория с полным и независимо валидированным Gerchik TVX+Schwab нет в этом поиске; отсутствие подтверждения **не** доказывает, что аналогов нигде нет.

## Первичные источники (приоритет — official docs)

1. [LEAN US Equity normalization RAW/SCALED_RAW](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data)
2. [LEAN US Equity Corporate Actions / native split reset](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions)
3. [LEAN Fundamental Universes + SelectionData](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/equity/fundamental-universes)
4. [LEAN Pivot Points High Low](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/pivot-points-high-low)
5. [LEAN Donchian Channel](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/donchian-channel)
6. [LEAN Relative Daily Volume](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/relative-daily-volume)
7. [LEAN Equity SECOND + QuoteBar availability](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/requesting-data)
8. [LEAN built-in risk models](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/supported-models)
9. [LEAN US equity shorting & borrow](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/shorting)
10. [LEAN slippage models](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models)
11. [LEAN Order Tickets/Transaction Manager](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-management/transaction-manager)
12. [LEAN contingent order semantics](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders)
13. [LEAN Bracket Orders — full parent fill](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/contingent-orders/bracket-orders)
14. [Schwab brokerage-specific restrictions](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/charles-schwab)
15. [Backtest Results: orders/trades/JSON downloads](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results)
16. [Object Store paid-only (Cloud Free cannot write)](https://www.quantconnect.com/docs/v2/cloud-platform/organizations/object-store)
17. [LEAN CLI paid org/local data requirement](https://www.quantconnect.com/docs/v2/lean-cli/backtesting/deployment)
18. [Published ORB benchmark, not Gerchik](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/)
