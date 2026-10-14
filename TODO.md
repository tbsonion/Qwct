# Qwct — TODO / Deep Research Roadmap

**Актуально:** 2026-10-14. **Ветка-источник:** `main`. **Режим:** `RESEARCH ONLY / ALL ORDERS DISABLED`.

> Единый актуальный TODO проекта. Старые отчёты в `docs/` — исторические срезы; утверждения в них вроде «LEAN не запускался» устарели. Спецификация правил: [docs/strategy_spec.md](docs/strategy_spec.md). «Готово в коде» **не означает** «доказано на настоящем LEAN / соответствует Герчику / прибыльно / разрешено торговать».

## Обязательное правило передачи изменений в QuantConnect LEAN Cloud

**Каждый раз, когда Qwct меняется и пользователю требуется обновить QuantConnect LEAN Cloud, заканчивать ответ отдельным разделом «GitHub-ссылки для обновления LEAN».** Нужны **ссылки на GitHub**, а **не** sandbox-файлы, прикреплённые `.py`, локальные пути или предложение скачивать файлы из чата.

1. Перечислить **каждый конкретный Cloud-путь**, который надо заменить, и дать отдельную **кликабельную GitHub-ссылку** на соответствующий код/готовый пакет. Если изменён один файл — показывать один файл, не предлагать переустановку проекта целиком.
2. Для обычных несобираемых модулей давать прямую ссылку на актуальный исходник GitHub, например **[`main.py`](https://github.com/tbsonion/Qwct/blob/main/main.py)** или **[`strategy/m5_runtime.py`](https://github.com/tbsonion/Qwct/blob/main/strategy/m5_runtime.py)**. При необходимости добавлять ссылку на конкретный commit SHA, чтобы версия не менялась между открытием и копированием.
3. **Критично для QuantConnect Free (24 Python + `research.ipynb`):** GitHub `strategy/reporting.py` **НЕ эквивалентен** Cloud `strategy/reporting.py`: упаковщик встраивает в него `strategy/runtime_reporting.py`. Также `strategy/focus.py`, `strategy/screener.py`, `strategy/native_m5_validation.py` объединены с другими Cloud-файлами. **Никогда не выдавать обычную ссылку на неполный исходник за готовый Cloud-файл.** Для таких изменений давать ссылку на **[GitHub Actions — QuantConnect Free 24-file package](https://github.com/tbsonion/Qwct/actions/workflows/quantconnect-free-package.yml)** (либо на конкретный успешный run/artifact) и **точно указывать путь файла внутри сборки**.
4. Если нужный Cloud-ready файл доступен только внутри GitHub Actions ZIP, прямо писать: «Отдельной ссылки на Cloud-ready файл на GitHub нет; открой GitHub Actions artifact и возьми `<Cloud-path>`». **Не придумывать несуществующие ссылки** и не подменять ZIP сырой несовместимой версией.
5. Указать в конце кратко: **что заменять, что НЕ заменять, состояние проверки GitHub CI / реального Cloud backtest**. Не называть результат Cloud-verified, если только GitHub CI прошёл.
6. После каждого следующего изменения **обновлять список ссылок в ответе** под реальные затронутые Cloud-файлы, а не механически повторять старые три файла. Инструкция действует постоянно для всего проекта Qwct.

**Пример для текущего Cloud scan:** GitHub [`main.py`](https://github.com/tbsonion/Qwct/blob/main/main.py), [`strategy/m5_runtime.py`](https://github.com/tbsonion/Qwct/blob/main/strategy/m5_runtime.py), и **`strategy/reporting.py` из [сгенерированной Cloud Free сборки на GitHub Actions](https://github.com/tbsonion/Qwct/actions/workflows/quantconnect-free-package.yml)**, НЕ исходный `strategy/reporting.py` напрямую. Исходные `main.py` и `strategy/m5_runtime.py` содержат импортные пути canonical-репозитория; при разнице импортов с Free-пакетом приоритет у соответствующего Cloud-ready варианта из ZIP.

## 0. Зафиксированная рабочая база

- [x] Официальный QuantConnect LEAN Cloud **signal-only** алгоритм запускается без runtime exceptions. Последний пользовательский smoke: **2024-01-01 — 2024-02-05**, LEAN **2.5.0.0.18179**, **1,233,565** рыночных data points, **18,240** обработанных M5, **6** D1 сценариев, **456** M5 проверок, **6** проходов `m5_confirmed`, **0** BPU1, **0** research candidates, **0** trade intents, **0** ошибок. Это **не** торговый backtest с исполнением и P&L.
- [x] Автоматический LEAN Fundamental Universe: ликвидный top-50 candidate prefilter, затем до **10** D1-qualified бумаг; native D1 ATR(14), SMA и объём, независимые D1/M5 проверки по акциям. Нет одобренного фильтра «только знакомые акции».
- [x] Анализ уровней на D1 (confirmed swing clusters, mirror proxy), три предварительных сценария (bounce, breakout, false_breakout), 14 feature groups, 8 mandatory gates **в коде**, native M5 chart и diagnostic trace. Ни одна модель не доказана канонической на размеченных примерах.
- [x] Обработаны duplicate/late/out-of-order M5; `SplitOccurred` quarantine и rewarm; native SEC/-30s TVX observer и read-only native risk adapter присутствуют в исходниках и unit tests, **не подтверждены в настоящем секундном Cloud run**.
- [x] QuantConnect Free packaging через [tools/package_quantconnect_free.py](tools/package_quantconnect_free.py): **24 Python files** + неизменённый `research.ipynb` (25-й файл). Канонические `strategy/*.py` в GitHub **не объединять вручную**.
- [x] Базовый RAW subscriptions + as-of SCALED_RAW D1 History вариант запущен в Cloud. Уровень NVDA (2024-01-02) изменился примерно с **50.2660** (`SPLIT_ADJUSTED`) на **502.5744** (новая база), исторический RAW pivot **502.66** теперь **подключается в Cloud**, при сохранении исходного D1 cluster median как отдельной величины.
- [x] Торговые ордера **полностью отключены**; `risk_approved` не становится `True`, EOD exit код защищён `_native_exit_enabled = False`; ObjectStore export отключён на Cloud Free.
- [x] PR #1, #5, #6, #7, #8 merged; #2–#4 **closed, not merged** (устаревшие ветки, не вливать вслепую). Сверяйте актуальные PR перед следующим изменением.

**Reference:** [docs/NVDA_BSU_RAW_ASOF_2026-10-12.md](docs/NVDA_BSU_RAW_ASOF_2026-10-12.md), [docs/LEAN_CLOUD_TVX_30S_SMOKE_2026-10-11.md](docs/LEAN_CLOUD_TVX_30S_SMOKE_2026-10-11.md), [docs/QWCT_DEEP_IMPLEMENTATION_AUDIT_2026-10-11.md](docs/QWCT_DEEP_IMPLEMENTATION_AUDIT_2026-10-11.md).

## 2026-10-13: найденные ГОТОВЫЕ решения BSU/BPU и решение reuse-first

**Новый сравнительный отчёт:** [READY_MADE_GERCHIK_BSU_BPU_SOLUTIONS_2026-10-13.md](docs/READY_MADE_GERCHIK_BSU_BPU_SOLUTIONS_2026-10-13.md). Исследованы MT4/MT5, TradingView, GitHub, native LEAN и первоисточник Герчика. **До внедрения новых функций сверяться с ним.**

- [x] **FREE** готовый внешний индикатор с близкими именованными BSU/BPU1/BPU2: MQL5 **Trade by levels (MT4)** и **TBL for mt5** (Dmitriy Tyunin). Можно изучить как независимый **визуальный** comparator. Это **не** open-source LEAN Python, портабельный код/данные US equities не доказаны. Некоторые заявленные правила H1/люфт 2–3 points/вход на следующем баре отличаются от Qwct M5 и -30s TVX.
- [x] Другие готовые коммерческие решения (VibeFox BSU BPU $30, TradingView invite-only GERCHIK+SMC) найдены; их логика широкой зоны/фракталов и доступ к закрытому исходнику не подтверждают соответствие строгому exact-touch Герчика. **Не покупать/не портировать вслепую.**
- [x] LEAN **PPHL**, **RollingWindow/consolidator.Window**, нативные History/QuantBook/SEC/TradeBar уже доступны для поиска и сопоставления без самодельного feed/pivot/window. Официальный LEAN не содержит полного BPU1→BPU2→TVX детектора. В Qwct уже есть собственный read-only observer.
- [x] **Cloud scan подготовлен в коде (2026-10-13):** повторно используем существующий native LEAN observer, `BpuTouchAudit`, M5 callbacks и Cloud Free reporting, параметризованные `scan_start`/`scan_end`, один прогон максимум 45 календарных дней. В логи выводятся 5 ближайших реальных M5 экстремумов и первые 4 BPU1/BPU2, если они существуют. **Это не результат нового Cloud запуска.** Подробные инструкции: [NATIVE_BSU_BPU_CASE_SCAN_2026-10-13.md](docs/NATIVE_BSU_BPU_CASE_SCAN_2026-10-13.md).
- [ ] **Следующий P0 — реальный Cloud:** Cloud лог, полученный 2026-10-14, **снова прогнал старое окно 2024-01-01…2024-02-05**, `SCENARIO=6`, `BPU1=0`, `ERROR=0`, без `QWCT SCAN` — это **не новая проверка**. Поэтому исправлены defaults GitHub `main.py`: **автоматически** 2024-02-06 → 2024-03-15, `_case_scan=True`, startup log `QWCT SCAN ACTIVE`. Заменить Cloud-ready `main.py`, а также установить `strategy/m5_runtime.py` + bundled `strategy/reporting.py` из [GitHub Actions Cloud Free ZIP](https://github.com/tbsonion/Qwct/actions/workflows/quantconnect-free-package.yml), если не обновлены ранее. Сбросить сохранённые `scan_start`/`scan_end`, которые могут переопределять defaults; `tvx_seconds=false`. **Cloud проверка нового окна ещё не выполнена**. Далее прочитать `QWCT SCAN NEAREST`/`QWCT SCAN EVENT` и `ERROR`; не считать отсутствующее касание BPU1.
- [ ] **Проверка перед любым новым кодом:** доказать, что конкретного наблюдения нельзя получить нынешним native M5 audit и QuantBook; только тогда добавить узкий read-only case-finder. NO ORDERS / не ослаблять tick/exact-touch.

## Новое: готовые решения, найденные в official LEAN (Deep Research 2026-10-12)

**Полный отчёт и ссылки на 18 первичных источников:** [docs/READY_BUILT_LEAN_RESEARCH_2026-10-12.md](docs/READY_BUILT_LEAN_RESEARCH_2026-10-12.md).

- [x] **Найден** встроенный **`RelativeDailyVolume` / `rdv()`**. Прежде чем расширять `opening_volume_research.py`, сравнить нативный `rdv(symbol,14)` с first-5m RVOL именно на 09:35, используя закрытые 14 прошлых регулярных сессий. **НЕ подключён к Qwct и parity не выполнена.**
- [x] **Найден** встроенный **`PivotPointsHighLow` / `pphl()`** и `DonchianChannel`. Применять как D1 baseline/comparator, **не объявлять эквивалентом авторских BSU/зеркал**.
- [x] **Подтверждено**: LEAN `History[TradeBar]` поддерживает отдельные `RAW` и `SCALED_RAW` запросы; `SCALED_RAW` может переносить старый экстремум с реальной native ценовой сетки вследствие уже известных сплитов/дивидендов. **Диагностировать точный RAW pivot, не округлять и не переименовывать кластерный median в pivot**.
- [x] **Подтверждено**: LEAN поддерживает `Resolution.SECOND`, `QuoteBar`, native `RiskManagementModel`, slippage/borrow providers, export Backtest Orders/Trades/Results; **поддержка API не является Cloud runtime proof в Qwct**.
- [x] **Критическая готовая API-ограниченность**: LEAN `Bracket`/OTO активирует защиту **только при полном parent fill**; у Schwab нельзя обновлять contingent set и нет OUO. **Partial-fill protection не готова.**
- [x] **Cloud 2026-10-13:** NVDA 2024-01-02 RAW original pivot (2023-08-24) = **502.66**, SCALED_RAW = **502.57439794**, tick = **0.01**, scaled tick offset = **0.00439794**, RAW last close = SCALED_RAW last close = **495.22**. Это доказано native Cloud логом, но НЕ доказывает причинную структуру split/dividend factor.
- [x] **Подтверждено в Cloud 2026-10-13:** native RAW original pivot/EndTime/as-of/latest-close/tick grid reconciled; NVDA bounce **armed** `pivot=502.6600`, `cluster=502.57`. `BSU block reasons={}`, `ERROR=0`, `NO ORDERS`. Pure CI зелёный, Free 24-file packaging проходит проверку.
- [x] **Cloud RAW bridge smoke завершён:** `QWCT BSU BASIS NVDA` присутствует; `QWCT BSU NVDA ... armed`; normalization blocker отсутствует.
- [ ] **Следующий P0:** найти нативный проверяемый `bounce` с реальным касанием RAW BSU на M5. На NVDA 2024-01-02 **0/76 точных касаний**, максимум native M5 high **493.00** против RAW BSU **502.66** (gap **9.66**); `BPU1=0` корректен для этого дня. Не снижать строгий touch фильтр и не фабриковать результаты.

## 1. Технические задачи и критерии принятия

| ID | Приоритет | Что работает | Что НЕ завершено / критерий готовности |
| --- | --- | --- | --- |
| **P0-01 BSU price basis** | P0 | **Cloud verified** NVDA bounce armed with RAW pivot **502.66** and distinct SCALED_RAW cluster **502.57439794**; native RAW M5 max high **493.00** on 2024-01-02 so no touch; `ERROR=0`, BSU block reasons `{}`; no orders. | [ ] Confirm factor/corporate-action provenance and historical matching on independent examples; this is a swing-proxy, not yet a certified discretionary BSU. |
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