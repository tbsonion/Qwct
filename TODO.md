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

**Последняя проверенная Cloud-сборка (март–апрель 2024) — код менять НЕ нужно. GitHub-ссылки остаются историческими ссылками для восстановления, а НЕ обязательным обновлением:** [`main.py`](https://github.com/tbsonion/Qwct/blob/main/deploy/quantconnect_free_20261014_bounce_audit/main.py), [`strategy/scenarios.py`](https://github.com/tbsonion/Qwct/blob/main/deploy/quantconnect_free_20261014_bounce_audit/strategy/scenarios.py), [`strategy/reporting.py`](https://github.com/tbsonion/Qwct/blob/main/deploy/quantconnect_free_20261014_bounce_audit/strategy/reporting.py). Это **Cloud-ready снимки**, особенно bundled `strategy/reporting.py`, а НЕ raw GitHub reporting.py. Заменить эти **три** существующих пути и оставить `strategy/m5_runtime.py` из уже работавшего скана без изменений. [Полная инструкция](deploy/quantconnect_free_20261014_bounce_audit/README.md). По следующим изменениям создавать НОВЫЕ verified GitHub-ссылки под действительно затронутые файлы.

## 2026-10-14: подтверждённый Cloud апрель–июнь — нет допущенных bounce

- [x] **Native QuantConnect LEAN 2.5.0.0.18179**, 2024-04-27 → 2024-06-07: `QWCT SCAN ACTIVE`, `SCENARIO=33` (`false_breakout=25`, `breakout=8`, **`bounce=0`**), `M5 bars=22039`, `M5 checks=2508`, `nearest=0`, `BPU1=0`, `BPU2=0`, `RESEARCH_CANDIDATE=0`, `ERROR=0`, ALL ORDERS DISABLED. `nearest=0` вызван отсутствием выбранных D1 bounce, а не доказанным отсутствием точных касаний цены всеми акциями.
- [x] **Cloud D1 bounce audit:** `nearby=155`, `eligible_level=71`, `scored_ge_threshold=0`, `below_threshold=71`, `outscored=0`, `tie_lost=0`, `selected=0`, `no_eligible_level=84`. Все 71 структурно подходящих D1 случаев не набрали существующий `min_model_score=4.0` для bounce. Не понижать порог ради появления сигналов без независимых размеченных примеров.
- [x] **Чарт `Qwct Focus` не является BSU proof:** в этом запуске Focus — `TSLA false_breakout/long` от 2024-04-29; синяя `D1 Level` на графике — меняющийся по сессиям выбранный D1 уровень, **не** фиксированный исторический RAW BSU pivot, и пересечение свечи с линией не доказывает BPU1.
- [x] **Итог четырёх неперекрывающихся native Cloud окон 2024-01-01…2024-06-07:** D1 accepted `6+15+28+33=82`, bounce `1+0+4+0=5`, native BPU1/BPU2 по всем окнам `0/0`. Это *наблюдения только по отобранному Qwct universe и текущим моделям*, не процент успеха стратегии и не основание для P&L выводов.
- [ ] **Приоритетная диагностика reuse-first, до дальнейшего перебора дат:** раздельно проверить `D1 swing level availability` vs `scored bounce winner` vs `native RAW M5 exact level touch`. Сейчас M5/BSU observer запускается **только** после selected `bounce`, поэтому `nearest=0` в любом окне с `bounce=0` ничего не говорит о касаниях на структурных уровнях. Предпочесть существующие LEAN `History`/`TradeBar`, `BpuTouchAudit`, `levels_for_session`; не строить новый feed/OMS. Если нужен отдельный shadow audit, сделать его **read-only** и явно отделить от `accepted` / score / trade intent, без lookahead, с нативной ценовой сеткой и RAW basis verification.
- [ ] **Опциональный следующий неизменённый Cloud запуск (если нужен ещё один статистический срез):** `scan_start=2024-06-08`, `scan_end=2024-07-19`, `tvx_seconds=false`; менять только даты в работающем `main.py`, никаких других файлов для LEAN. Но повторный `bounce=0` будет малоинформативен без отдельного измерения структурных касаний.

## 2026-10-14: проверенный Cloud март–апрель — 4 bounce, 0 exact BSU touches

- [x] **Native QuantConnect LEAN v2.5.0.0.18179:** 2024-03-16 → 2024-04-26; `QWCT SCAN ACTIVE`, `ERROR=0`, `SCENARIO=28` (`false_breakout=20`, `bounce=4`, `breakout=4`), `M5 checks=2128`, `nearest=4`, `BPU1=0`, `BPU2=0`, ордера OFF. Два предыдущих Cloud mismatch (`SessionPolicy` и `scan_model_audit`) фактически больше не воспроизводятся.
- [x] **D1 Bounce Audit в реальном Cloud:** `nearby=129`, `eligible_level=60`, `scored_ge_threshold=4`, `below_threshold=56`, `outscored=0`, `tie_lost=0`, `selected=4`, `no_eligible_level=69`. В текущем периоде 4 прошедших порог bounce **выбраны без арбитражных потерь**; остальные 56 D1 примеров с подходящими уровнями не набрали исходный score ≥4.0. Не повышать score искусственно.
- [x] **Четыре фактических ближайших закрытых RAW M5 случая (отдельные дни):** MSFT 2024-04-11 pivot **427.83**, ближайший M5 high **427.79** (`-0.04` = **4 native ticks**, в 13:45); AMZN 2024-03-22 pivot **180.14**, M5 high **179.25** (`-0.89`); MSFT 2024-04-12 `-2.67`; MSFT 2024-04-10 `-3.77`. **Ни одного exact touch на native tick-grid**, поэтому BPU1/BPU2 корректно остаются 0; `-0.04` **не** подтверждение BSU/BPU1.
- [x] **Следующий Cloud тест 2024-04-27..2024-06-07 завершён:** 33 D1 (25 false_breakout, 8 breakout, 0 bounce), D1 audit eligible_level=71, bounce score>=4: 0, BPU1/BPU2=0, errors=0. Результаты и новый приоритет research-first — в разделе выше. Переписывать файлы в QuantConnect сейчас не требуется.
- [ ] Если следующие несколько окон тоже дают `exact=0`, исследовать **point-in-time** полноту universe, подтверждение исторических уровней, число реально наблюдавшихся native M5 touch и сравнение с независимыми ручными Gerchik примерами. Не менять допуск нативного тика, не выдавать near-miss за BPU и не использовать будущие свечи.

## 2026-10-14: Cloud mismatch scenarios.py vs reporting.py — end-of-run crash

- [x] **Ошибка пользователя (LEAN 2024-03-16…2024-04-26):** `on_end_of_algorithm() → write_reports → self._scenario_evaluator.scan_model_audit` поднял `AttributeError: 'ScenarioEvaluator' object has no attribute 'scan_model_audit'`. Это **несовпадение версий Cloud файлов**, а не отрицательный результат поиска BSU/BPU. Достоверная статистика этого запуска не выведена.
- [x] **Источники GitHub сверены:** Cloud-ready [`strategy/scenarios.py`](https://github.com/tbsonion/Qwct/blob/main/deploy/quantconnect_free_20261014_bounce_audit/strategy/scenarios.py) уже содержит `self.scan_model_audit = Counter()`; bundled `strategy/reporting.py` требует этот атрибут. Следовательно, реально запущенный Cloud `strategy/scenarios.py` не соответствует этому исходнику (нельзя доказать, что именно было вставлено, без Cloud файла).
- [x] **Добавлен regression guard в package CI:** проверять, что пакетные `strategy/scenarios.py` и `strategy/reporting.py` совместимы, `ScenarioEvaluator(StrategyConfig()).scan_model_audit` существует; CI **не может** проверить вручную обновлённые файлы Cloud.
- [x] **Cloud mismatch resolved by later native run:** после обновления пользователь запустил полный 2024-03-16…2024-04-26 тест, и `QWCT D1 BOUNCE AUDIT` вывел все счётчики без `AttributeError`; дальнейшее повторное копирование `strategy/scenarios.py` **не нужно**.

## 2026-10-14: ошибка импорта SessionPolicy в QuantConnect Cloud

- [x] **Диагноз по Cloud backtest:** `Algorithm.Initialize() Error: cannot import name 'SessionPolicy' from 'strategy.sessions'` (`main.py:17`). Исходник GitHub [`strategy/sessions.py`](https://github.com/tbsonion/Qwct/blob/main/strategy/sessions.py) **уже содержит** `class SessionPolicy`; значит Cloud-копия `strategy/sessions.py` не соответствует корректному GitHub исходнику (причина рассинхронизации без содержимого Cloud файла точно не доказана). Никаких торговых сигналов в этом запуске не вычислялось.
- [x] **Защита от повторения:** тест Cloud Free package проверяет определение `class SessionPolicy` в `strategy/sessions.py` и делает импорт `from strategy.sessions import SessionPolicy` в отдельном Python процессе. Это тест упаковки/исходника, но не подтверждение состояния Cloud editor.
- [x] **Cloud import mismatch resolved by later native run:** 2024-03-16…2024-04-26 прошёл до `on_end_of_algorithm` с `ERROR=0`. Повторно вставлять `strategy/sessions.py` **не нужно**.

## 2026-10-14: результат второго реального Cloud BPU scan и диагноз отбора

- [x] **Настоящий LEAN Cloud 2.5.0.0.18179:** `2024-02-06..2024-03-15`, лог подтвердил `QWCT SCAN ACTIVE`, `SCENARIO=15`, **все 15 — `false_breakout`; `bounce=0`**, `M5 bar checks=1140`, `QWCT SCAN nearest=0`, `BPU1=0`, `BPU2=0`, `ERROR=0`, ордера OFF. **Это означает: ни один из текущих 15 D1 winner-сценариев не вооружил BSU bounce observer.** Это **не** доказательство отсутствия подлинных исторических касаний на рынке и не основание ослабить уровень/tick.
- [x] **Код research-only:** добавлена диагностика **D1 bounce model arbitration** поверх исходного `ScenarioEvaluator.evaluate` с уже вычисленными признаками. Отдельно считает наличие структурно допустимого swing_cluster D1, bounce score относительно оригинального порога 4, случаи когда bounce проиграл другой модели, и выбранный bounce. Выбранный сценарий, веса, пороги, BPU и trading gates **не изменены**. GitHub pure CI **330 passed**, Free 24 Python packaging passed; **ещё нет Cloud runtime проверки нового audit**.
- [x] **Тест Cloud 2024-03-16…2024-04-26 завершён:** 28 сценариев, bounce=4, `eligible_level=60`, `outscored=0`, `BPU1=0`, `ERROR=0`. Подробная статистика и следующий период приведены выше. Новых файлов для Cloud сейчас не требуется.

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
- [x] **Проверка Cloud Feb–Mar завершена:** `2024-02-06..2024-03-15` в настоящем LEAN, ошибки 0, все 15 accepted D1 `false_breakout`, ни одного D1 `bounce`, поэтому `nearest=0` и `BPU1=0`. Следующая задача — отделить отсутствие допустимых D1 уровней от `bounce`, проигравшего арбитражу моделей; текущий новый Cloud-ready audit описан выше.
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