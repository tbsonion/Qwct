# Qwct — TODO / Deep Research Roadmap

**Актуально:** 2026-10-13. **Ветка-источник:** `main`. **Режим:** `RESEARCH ONLY / ALL ORDERS DISABLED`.

> Единый актуальный TODO проекта. Старые отчёты в `docs/` — исторические срезы; утверждения в них вроде «LEAN не запускался» устарели. Спецификация правил: [docs/strategy_spec.md](docs/strategy_spec.md). «Готово в коде» **не означает** «доказано на настоящем LEAN / соответствует Герчику / прибыльно / разрешено торговать».

## 0. Зафиксированная рабочая база

- [x] Официальный QuantConnect LEAN Cloud **signal-only** алгоритм запускается без runtime exceptions. Последний пользовательский smoke: **2024-01-01 — 2024-02-05**, LEAN **2.5.0.0.18178**, **1,233,385** рыночных data points, **18,240** обработанных M5, **6** D1 сценариев, **456** M5 проверок, **6** проходов `m5_confirmed`, **0** BPU1, **0** research candidates, **0** trade intents, **0** ошибок. Это **не** торговый backtest с исполнением и P&L.
- [x] Автоматический LEAN Fundamental Universe: ликвидный top-50 candidate prefilter, затем до **10** D1-qualified бумаг; native D1 ATR(14), SMA и объём, независимые D1/M5 проверки по акциям. Нет одобренного фильтра «только знакомые акции».
- [x] Анализ уровней на D1 (confirmed swing clusters, mirror proxy), три предварительных сценария (bounce, breakout, false_breakout), 14 feature groups, 8 mandatory gates **в коде**, native M5 chart и diagnostic trace. Ни одна модель не доказана канонической на размеченных примерах.
- [x] Обработаны duplicate/late/out-of-order M5; `SplitOccurred` quarantine и rewarm; native SEC/-30s TVX observer и read-only native risk adapter присутствуют в исходниках и unit tests, **не подтверждены в настоящем секундном Cloud run**.
- [x] QuantConnect Free packaging через [tools/package_quantconnect_free.py](tools/package_quantconnect_free.py): **24 Python files** + неизменённый `research.ipynb` (25-й файл). Канонические `strategy/*.py` в GitHub **не объединять вручную**.
- [x] Базовый RAW subscriptions + as-of SCALED_RAW D1 History вариант запущен в Cloud. Уровень NVDA (2024-01-02) изменился примерно с **50.2660** (`SPLIT_ADJUSTED`) на **502.5744** (новая база), однако **BSU остаётся заблокированным**. Наблюдение не является исправлением точной цены BSU.
- [x] Торговые ордера **полностью отключены**; `risk_approved` не становится `True`, EOD exit код защищён `_native_exit_enabled = False`; ObjectStore export отключён на Cloud Free.
- [x] PR #1, #5, #6, #7, #8 merged; #2–#4 **closed, not merged** (устаревшие ветки, не вливать вслепую). Сверяйте актуальные PR перед следующим изменением.

**Reference:** [docs/NVDA_BSU_RAW_ASOF_2026-10-12.md](docs/NVDA_BSU_RAW_ASOF_2026-10-12.md), [docs/LEAN_CLOUD_TVX_30S_SMOKE_2026-10-11.md](docs/LEAN_CLOUD_TVX_30S_SMOKE_2026-10-11.md), [docs/QWCT_DEEP_IMPLEMENTATION_AUDIT_2026-10-11.md](docs/QWCT_DEEP_IMPLEMENTATION_AUDIT_2026-10-11.md).

## Новое: готовые решения, найденные в official LEAN (Deep Research 2026-10-12)

**Полный отчёт и ссылки на 18 первичных источников:** [docs/READY_BUILT_LEAN_RESEARCH_2026-10-12.md](docs/READY_BUILT_LEAN_RESEARCH_2026-10-12.md).

- [x] **Найден** встроенный **`RelativeDailyVolume` / `rdv()`**. Прежде чем расширять `opening_volume_research.py`, сравнить нативный `rdv(symbol,14)` с first-5m RVOL именно на 09:35, используя закрытые 14 прошлых регулярных сессий. **НЕ подключён к Qwct и parity не выполнена.**
- [x] **Найден** встроенный **`PivotPointsHighLow` / `pphl()`** и `DonchianChannel`. Применять как D1 baseline/comparator, **не объявлять эквивалентом авторских BSU/зеркал**.
- [x] **Подтверждено**: LEAN `History[TradeBar]` поддерживает отдельные `RAW` и `SCALED_RAW` запросы; `SCALED_RAW` может переносить старый экстремум с реальной native ценовой сетки вследствие уже известных сплитов/дивидендов. **Диагностировать точный RAW pivot, не округлять и не переименовывать кластерный median в pivot**.
- [x] **Подтверждено**: LEAN поддерживает `Resolution.SECOND`, `QuoteBar`, native `RiskManagementModel`, slippage/borrow providers, export Backtest Orders/Trades/Results; **поддержка API не является Cloud runtime proof в Qwct**.
- [x] **Критическая готовая API-ограниченность**: LEAN `Bracket`/OTO активирует защиту **только при полном parent fill**; у Schwab нельзя обновлять contingent set и нет OUO. **Partial-fill protection не готова.**
- [x] **Cloud 2026-10-13:** NVDA 2024-01-02 RAW original pivot (2023-08-24) = **502.66**, SCALED_RAW = **502.57439794**, tick = **0.01**, scaled tick offset = **0.00439794**, RAW last close = SCALED_RAW last close = **495.22**. Это доказано native Cloud логом, но НЕ доказывает причинную структуру split/dividend factor.
- [x] **Реализовано только в коде:** независимая проверка RAW original pivot/EndTime/as-of/latest-close/tick grid для каждого accepted bounce и передача RAW origin в read-only BPU; никаких ордеров. Pure CI зелёный; Free 24-file package проходит проверку.
- [ ] **Следующий Cloud эксперимент:** обновить оба файла `main.py` и `strategy/bsu_bridge.py` вместе из актуальной Cloud Free сборки, убедиться в `QWCT BSU BASIS NVDA` и исчезновении normalization blocker без ошибок. BPU1 не должен появляться искусственно без точного касания M5.

## 1. Технические задачи и критерии принятия

| ID | Приоритет | Что работает | Что НЕ завершено / критерий готовности |
| --- | --- | --- | --- |
| **P0-01 BSU price basis** | P0 | Native Cloud verified NVDA original RAW high **502.66** vs SCALED_RAW **502.57439794**; latest D1 closes align; code now resolves exact RAW pivot via fail-closed as-of evidence (CI green) | [ ] **New bridge still needs Cloud verification**: BPU observer arms using RAW 502.66, native M5 remains RAW, no false touch, no errors, orders disabled. Full split/factor and Gerchik validation remain open. |
| **P0-02 D1 levels vs course** | P0 | Swing/mirror proxy и 14 groups | [ ] Собрать независимый набор размеченных вручную **положительных и отрицательных** случаев BSU, mirror, infected zone, accumulation, trend, 4R room, no-level; определить precision/recall по каждой модели и цену false positives. Сейчас статистики нет. |
| **P0-03 BSU → BPU1 → BPU2** | P0 | Bounce-only native M5 observer, strict BPU source timestamp, BPU2 state | [ ] В real Cloud получить диагностируемые реальные M5 touch/under/over, BPU1+BPU2 или доказанное отсутствие события; проверить native end times и split day. Исторический swing pivot ≠ сертифицированный вручную BSU. Полный путь не готов. |
| **P0-04 True TVX -30s** | P0 | Обработчик `Resolution.SECOND`/preclose + тесты, opt-in `tvx_seconds=true` | [ ] Отдельный, ограниченный по стоимости Cloud backtest: SEC feed **>0**, корректная native-second timestamp at true -30s, реальные interval extremes, gaps/no-trades, no fill forward, last trade vs limit; BPU2 reconciliation без будущих данных. Текущий Cloud тест SEC **OFF**. |
| **P0-05 M5 & 8 gates** | P0 | 456 checks; 6 M5 proxy passes | [ ] Разобрать для каждого из 6 успехов `m5_confirmed` время, тикер, модель и независимые блокеры (`trend_aligned`, `room_at_least_4r`, `risk_approved`). Оценить соответствие `g06` M5 staircase, confirm/impulse, bounce/false breakout/breakout. Нельзя путать 450 M5 failures с багами, пока не размечены реальными свечами. |
| **P0-06 Real native risk ledger** | P0 | `risk_research.py` рассчитывает лимиты; `lean_risk_observer.py` умеет читать только часть LEAN snapshot | [ ] На источниках **LEAN/Schwab** подтвердить period-start equity, cashflows, realized P&L, order reservations, stop risk, open slots, losses/wins, pause 3 losing days, max 3 positions, 5 trades/day, $50/0.2%, 3% day/week, 10% month и полу-дни. `risk_approved` оставить UNKNOWN, пока нет полной проверки. |
| **P0-07 Canonical entry semantics** | P0 | Сценарии/ограничения существуют | [ ] Сопоставить реальные Герчик-материалы с формулой BSU stop/luft=20% и tick-sized limit; ATR stop proxy — **гипотеза**, не доказанное каноническое правило. Разметить опорные правильные и неверные сценарии, не копировать случайные стратегии. |
| **P1-01 Screener + RVOL** | P1 | Native auto-screener 50→10; read-only `opening_volume_research.py` 14-session opening RVOL протестирован отдельно | [ ] Исследовать universe misses (familiar only, earnings/news, spread, ATR, survivorship, liquidity and price basis) и интеграцию RVOL **после** 09:35 без 09:29 lookahead. RVOL сейчас **не влияет** на выбор акций; 50→10 отбрасывает часть рынка. SEC режим ограничивает universe ещё раньше. |
| **P1-02 Breakout / false breakout** | P1 | `breakout_retest.py` stateful three-phase observer, простые LP proxy | [ ] Проверить реальные breakout→retest→confirmation на размеченных M5 и независимые 3-модельные D1 сценарии. Сложные LP из исходных заметок не формализованы — не изобретать детали. |
| **P1-03 Durable reporting** | P1 | `_record`, `OnOrderEvent`, `TradeBuilder`, короткий Cloud summary | [ ] Найти поддерживаемый **native** способ полного сохранения signal rejects, intent gates, source candles, реальные order events / fills / fees / net P&L в Free/paper окружениях. На текущем Free ObjectStore export выключен: полный журнал **не сохранён**. Не придумывать fills / equity curve. |
| **P1-04 Multi-period validation** | P1 | Короткий Jan–Feb 2024 Cloud smoke | [ ] Исследование train/validation/test по годам и разным режимам, split/half-day/halts, out-of-sample, sensitivity к score/ATR, fees/spread/slippage и стабильности частоты сигналов. Пока **нет доказанной доходности, win rate или expectancy**. |
| **P1-05 Missing context** | P1 | Базовые OHLCV-фильтры | [ ] Подтвердить native historical bid/ask spreads, borrow/short permissions, earnings calendar, regime/news/sector, halt handling и fresh market-data evidence; не подменять исторические данные известными постфактум. |
| **P2-01 Protected execution** | P2 BLOCKED | `protected_entry.py` — read-only preflight | [ ] Документированно сравнить native LEAN Schwab limit, bracket/OCO/OTO, **partial fill без stop**, modifications/cancel acknowledgment, order rejection, disconnect, buying power, fees. Использовать только поддерживаемые native механизмы; **никакого своего OMS/software OCO**. Не включать исполнение, пока нельзя гарантировать проверяемый путь защиты риска. |
| **P2-02 TP / stop plan** | P2 BLOCKED | `tp_r=3`, `scale_out=(.70,.20,.10)` в конфиге | [ ] Сначала **один TP 3R** (условие первого месяца); затем только при доказанной совместимости и решении владельца 70%/20%/10%, перенос стопа, trailing (не отдавать >25% прибыли). Настройки ≠ исполняемые ордера. |
| **P2-03 EOD and broker** | P2 BLOCKED | Native schedules: cancel first → check → liquidate → verify, **disabled** | [ ] Изолированный paper/broker-native тест реальных LEAN `OrderEvents`, open-order cancellation/partial fills, early closes, flat evidence и Schwab behavior. Без этого никаких заверений «100% flat». |
| **P2-04 ORB / Hybrid** | P2 OPTIONAL | Отдельное read-only opening-volume исследование | [ ] Уточнить, нужна ли отдельная ORB стратегия. Не смешивать ORB с правилами Герчика и не переносить устаревшие ветки без воспроизводимого benchmark. |

## 2. Следующий *Deep Research* (исследование ДО нового кода)

**DR-01 — Native corporate-action & tick grid (первая задача).**
Вопросы: что именно означает native `minimum_price_variation` для D1 `SCALED_RAW` pivot до NVDA 10:1 split? Как сохранить строгий BSU exact touch при сопоставлении исторического pivot с RAW M5 в **одной as-of торговой дате**? Почему origin off-grid при 502.5744 median? Что делать с дивидендами и старым pre-split OHLC?
**Источники:** официальные QuantConnect requesting-data/corporate-action/history docs; реальный LEAN Cloud output с timestamps, factors, pivot extremes и native M5.
**Результат:** таблица цен/splits/ticks/ATR + отрицательные тесты; единственная минимальная исправленная проверка, которая **не** расширяет правило касания.

**DR-02 — Gerchik annotated rule equivalence.**
Вопросы: сколько действительно есть BSU/BPU1/BPU2, допустимые exact-touch/луфт, stronger/weaker levels, M5 staircase, simple/complex false breakouts? Какая точная формула стопа? Нужно собрать реальные исторические/авторские примеры с известным временем.
**Результат:** размеченный fixtures corpus (symbol/date/side/level/source candles/expected model/exclusion reason), precision/recall, trace каждого из 8 gates; правила должны отличать «UNKNOWN» от false.

**DR-03 — Native SECOND feed feasibility in QuantConnect Free.**
Вопросы: доступен ли SEC на нужной бирже/году/подписке; расходы данных / runtime quotas; статус TradeBar at cutoff, нет ли fill-forward и delayed delivery; допустимый native sequence callback.
**Результат:** отдельный short smoke с метриками `native SEC received`, M5 and TVX `-30s`, реальными bar-end timestamps; **не** просто зелёный pytest.

**DR-04 — Native portfolio risk + Schwab capabilities (исследование отдельно от включения ордеров).**
Вопросы: где брать периодические equity/P&L anchors, realized trades, multi-symbol reserved risk, cashflows; что происходит после partial limit fills; доступны ли действительно bracket child-stop и безопасное исправление при partial fill; поддерживает ли Schwab OCO/OTO/updates/short borrow.
**Результат:** capability matrix «native documented / observed in paper / unsupported / UNKNOWN», набор отказов, воспроизводимый no-money тест.

**DR-05 — Screener and tradable strategy quality.**
Вопросы: реальная потеря coverage при 50→10, API нативного same-clock RVOL, spread/borrow/earnings/news, selection bias; как отличить Gerchik setup от случайного свечного паттерна; пригодность стратегии в тренде/флэте.
**Результат:** отдельно frozen research snapshots 09:29 vs 09:35, ground-truth cases, multi-year out-of-sample protocol и **честная** статистика после costs, без обещаний %/мес.

**Приоритет:** DR-01 → DR-02 → DR-03 → DR-04 → DR-05. Исследовать готовые native решения **до** реализации. Отдельный ORB benchmark допускается лишь как сравнительная стратегия, не как доказательство Герчика.

## 3. Правила выполнения для следующих PR

- [ ] Сначала официальная документация **QuantConnect LEAN** + **Schwab** и сравнение существующих решений. Изменять **одну** подтверждённую проблему за PR; не строить второй брокер/календарь/индикаторы.
- [ ] Приложить источник фактических данных, «до/после», исходный bar timestamp, тесты **positive/negative**, риск lookahead, quantization, split/half-day, варианты неуспеха.
- [ ] Для каждого изменённого Cloud модуля подтвердить unit CI, `main.py` < 28k chars, generated ZIP **24 .py** и реальные M5/SEC Cloud observations (по соответствующему scope).
- [ ] Не менять risk gates/strategy thresholds только ради того, чтобы получить сигналы; no mocked fills; `risk_approved` нельзя проставить `True` без полного native evidence.
- [ ] Держать **ALL ORDERS DISABLED** до отдельного документированного решения об исполнении и брокерского paper test. Не трогать секреты/Schwab creds.
- [ ] Сравнить с последним native smoke; помечать `CODE`, `UNIT TESTED`, `CLOUD OBSERVED`, `BROKER/PAPER VERIFIED` раздельно.
- [ ] Merge в `main` только проверенного scoped PR. После каждого merge обновлять этот файл: отметки, blockers, конкретные ссылки на доказательства и следующий эксперимент.

## 4. Критерии готовности стадий

- **Research engine ready:** native price/tick/ATR as-of подтверждены, по каждой модели есть понятные valid + invalid cases, M5/TVX positive и negative, 8 gates дают воспроизводимое объяснение. **Сейчас НЕ готов.**
- **Trade strategy validated:** multi-year/out-of-sample распределение signals, реалистичные costs, risk of ruin и drawdown исследованы на настоящих данных. **Сейчас НЕ готов.**
- **Execution ready:** native Schwab-compatible protection на partial fills, EOD, fees/P&L и полная native risk ledger проверены в отдельном paper setup. **Сейчас НЕ готов.**
- **Live eligible:** требует **отдельного разрешения владельца**, после проверки предыдущих трёх стадий. **Сейчас запрещено.**

---
**Источники в репозитории:** [spec](docs/strategy_spec.md) · [deep audit](docs/QWCT_DEEP_IMPLEMENTATION_AUDIT_2026-10-11.md) · [native SEC Cloud protocol](docs/LEAN_CLOUD_TVX_30S_SMOKE_2026-10-11.md) · [RAW-as-of findings](docs/NVDA_BSU_RAW_ASOF_2026-10-12.md).