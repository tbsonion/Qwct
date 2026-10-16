# QWCT 5.6 — готовые order-flow возможности, 16.10.2026

**Решение:** GO для изолированного native data inventory; **BLOCKED для положительных limit-player/CVD подтверждений**. Исторические TRADE доступны по прошлому Cloud опыту 4.9; полнота/синхронизация QUOTE, классификация агрессора и текущие права аккаунта пока не доказаны. Новый Cloud запуск в этой сессии не выполнен: доступа к QuantConnect runtime среди подключённых инструментов нет. Ниже DOCUMENTED, CODE/UNIT и CLOUD OBSERVED разделены.

Изучена база main `71a768d74ca9376164fd12aa782089b45c83be2d`: TODO, STATUS, AGENTS, QWCT 5.3/5.4/5.5, `strategy/m5_reaction_taxonomy.py`, `strategy/native_second_tvx.py`, `strategy/second_runtime.py`, cells 4.8/4.8b/4.9 и существующие CI. Торговые файлы, BSU/BPU, 10 реакций и Risk Gate не изменены.

## 1. Подтверждённая причина нового audit

[Официальный equity tick format](https://www.quantconnect.com/docs/v2/lean-engine/data-format/us-equity) прямо описывает односторонние QUOTE updates: на другой стороне price/size равны нулю. В 4.9 отбор требовал одновременно bid/ask и оба size > 0. Поэтому «0 two_sided_quotes» **не доказывает отсутствие quote данных**. Какие именно из 80 ранее отклонённых тиков являются односторонними, покажет только повторный inventory. Не переписываем прошлые числа как новый результат.

Полноценная котировка потребует определения scope (venue BBO / consolidated NBBO), раздельного состояния сторон, withdrawal/cancel semantics, начального snapshot, freshness, condition flags и порядка событий. Просто последовательно соединить последние bid и ask разных бирж нельзя. Самодельный feed/book здесь не создаётся; сначала проверка native представления и готового источника. Raw quote sizes — отображаемая ликвидность, не исполненный объём и не скрытый iceberg.

[LEAN Tick schema](https://github.com/QuantConnect/Lean/blob/master/Common/Data/Market/Tick.cs) имеет `time`, `tick_type`, `price/quantity`, bid/ask prices/sizes, exchange, sale_condition, suspicious; native exchange aggressor flag для этих исторических форматов не найден. Точность timestamp в документации формата — миллисекунды; фактические 4.9 значения сохраняем без округления, не обещаем единой субмиллисекундной точности. Event timestamp не равен доказанному receive/availability timestamp. Равные времена не задают межпоточный порядок.

## 2. REQUIRED → AVAILABLE → QUALITY → READY → COST → DECISION

Стоимость: **C0** = без новой покупки для обычного cloud M1+; **CT** = SECOND/TICK требует документированного Quant Researcher entitlement, реальная текущая подписка/цена аккаунта UNKNOWN; **CX** = отдельная лицензия/котировка поставщика, ничего не приобреталось.

| Required data / задача | Available data | Data quality / ограничение | Ready solution | Cost | Implement / blocked |
|---|---|---|---|---|---|
| Реальные сделки price/qty/time, US shares | Native `History[Tick]`, TRADE, RAW | Ранее CLOUD OBSERVED SRPT; новый window coverage не измерен | QuantBook, без нового feed | CT | IMPLEMENTED inventory, Cloud pending |
| Bid/ask price/size/time | Native QUOTE ticks, часто one-sided | Обе стороны на одном tick не обязательны; venue/NBBO/withdrawal и freshness не проверены | Native Tick / QuoteBar; QuoteBar не восстанавливает intrabar sequencing | CT | IMPLEMENTED raw shape counts; book/classification BLOCKED |
| Aggressor side | В native историческом US equity/futures/crypto формате отдельного знака не найдено | Цена у bid/ask — оценка, midpoint/locked/stale/outside/equal-time случаи неоднозначны | Готового native CVD не найдено в [каталоге](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators); `Delta` в нём — опционный Greek | CT/CX | TRUE CVD BLOCKED; estimate тоже пока не реализован |
| Vertical volume | M1/M5 bar volume / trade quantity | Bar-building filters отличаются от raw ticks; сумма не обязательно совпадает | Native TradeBar/volume | C0/CT | Использовать как контекст, не signed flow |
| Session VWAP | Trades или закрытые TradeBars | Tick VWAP по реальным сделкам; bar VWAP по typical price — оценка; средняя всех сделок ≠ себестоимость одного игрока | [IntradayVwap](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/intraday-vwap), дневной reset | C0/CT | READY; не интегрирован до data proof |
| Rolling VWAP | Закрытые бары | Окно отличается от session reset; не подменять одно другим | [VolumeWeightedAveragePriceIndicator](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/volume-weighted-average-price-indicator) | C0 | READY context only |
| Volume-at-price / POC / VA | Готовый native VolumeProfile | Реализация MarketProfile кладёт **весь bar volume на округлённый Close**, а не распределяет реальные сделки | [VolumeProfile](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/volume-profile), [исходник MarketProfile](https://github.com/QuantConnect/Lean/blob/master/Indicators/MarketProfile.cs), [VolumeProfile.cs](https://github.com/QuantConnect/Lean/blob/master/Indicators/VolumeProfile.cs) | C0 | READY BAR_CLOSE_PROFILE_PROXY; exact executed VAP BLOCKED до tick quality / готового решения |
| Open Interest US shares | Не характеристика spot shares | OI опциона — другой инструмент, не позиция в акции | Не заменять shares опционами | — | N/A для SRPT shares |
| OI futures | Native OI/contract history | Не подписывает сделки; частота формата не означает новый exchange OI каждую секунду; нужен publication/as-of | [Futures History](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/asset-classes/futures) | C0/CT | DOCUMENTED, per-contract runtime pending |
| US futures tape | Trade/quote/OI по конкретному контракту | Нельзя брать склеенный continuous back-adjusted series для exact VAP/flow | [AlgoSeek US Futures](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures), native contract History | CT | READY API; coverage/aggressor proof BLOCKED |
| Crypto spot | Trade/quote по venue/pair | Не global book, no spot OI; generic Tick не сохраняет maker flag по умолчанию | [Coinbase dataset](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/coinbase-crypto-price-data), [research API](https://www.quantconnect.com/docs/v2/research-environment/datasets/crypto) | CT | DOCUMENTED, venue/date coverage pending |
| Crypto futures | Native venue-specific price data | Наличие price feed не доказывает исторический OI или maker/aggressor | [Binance futures dataset](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/binance-crypto-future-price-data) | CT/CX | Aggressor/OI BLOCKED до отдельного dataset proof |
| Готовый execution-flow proxy | Spectral Tick Flow Signal, daily, S&P500/SPY | Proprietary cadence inference; не CVD, не passive participant identity, не same-day M5 trigger | [Native SpectralTickFlowSignal](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/spectral-tick-flow-signal) | License price/entitlement UNKNOWN | READY discovery only; publication/revision timing BLOCKED |
| Конкретный крупный лимитный игрок | Native L1 не содержит identity, полную глубину/очередь и скрытые позиции | Даже signed flow не доказывает одного игрока или набор его позиции | Нет готового доказательства личности/позиции | — | BLOCKED; только явно размеченные hypotheses |

### Выбор готовых решений

Предпочтение: native QuantBook History + native VWAP; native VolumeProfile только с честной маркировкой bar-close proxy. [Исходник IntradayVwap](https://github.com/QuantConnect/Lean/blob/master/Indicators/IntradayVwap.cs) принимает TRADE tick с LastPrice/Quantity и закрытый non-fill-forward TradeBar с `(H+L+C)/3`.

[Sierra Chart Cumulative Delta](https://www.sierrachart.com/index.php?page=doc/StudiesReference.php&ID=292) — готовое приложение для Bid/Ask volume при подходящей истории; [Up/Down Tick Delta](https://www.sierrachart.com/index.php?page=doc/StudiesReference.php&ID=323) — другая оценка. Это не LEAN dependency и не исправление недостающих signed trades. [Тарифы](https://www.sierrachart.com/index.php?page=doc/Packages.php): отдельный package/data/exchange fees, стоимость требуемого комплекта UNKNOWN, не покупать на этом этапе.

[Databento Trades](https://databento.com/docs/schemas-and-data-formats/trades) / MBP-1 — готовая схема и SDK вместо своей инфраструктуры. `side` может быть None: [поддержка зависит от venue/dataset](https://databento.com/docs/knowledge-base/datasets), нельзя обещать aggressor для любых US shares. [Стоимость](https://databento.com/pricing) зависит от dataset, объёма/периода и лицензии; точная смета QWCT не получена. Это кандидат для отдельного сравнения **после** native audit, не новая зависимость/подключение сейчас.

## 3. Free Cloud и деньги

[Organization tiers](https://www.quantconnect.com/docs/v2/cloud-platform/organizations/tier-features): Free — minute..daily, один бесплатный research и backtest node; Quant Researcher — SECOND/TICK. Это не отменяет сохранённый успешный опыт 4.8/4.9 в конкретном аккаунте; tier/trial/entitlement того запуска UNKNOWN. Не утверждать «все tick бесплатно на Free» по общему dataset marketing.

[Текущая pricing table](https://www.quantconnect.com/pricing/): Free 32KB/file, 10KB/backtest log, один research node. 25 **Backtest Download Requests** — лимит импортируемых data files, не объяснение размера Python package. Существующий 24py package не меняем. Статическая выдача pricing не дала проверяемой точной месячной цены минимального Researcher комплекта: **UNKNOWN, не выдумываем $60/$10**. Сначала один bounded запрос в уже имеющемся notebook; никакой новой покупки. Ошибка History может быть API/data/entitlement: cell не объявляет любую ошибку доказательством отсутствия лицензии.

[Dataset licensing](https://www.quantconnect.com/docs/v2/cloud-platform/datasets/licensing): cloud use и локальная выгрузка — разные права/расходы. Bulk tick download за тысячи долларов с витрины не нужен для этого исследования. Текущий внешний расход — **$0**, платные продукты не подключены; это не утверждение о счёте пользователя.

## 4. Что проверяет новая одна cell

[QWCT_5_6_ORDER_FLOW_DATA_AUDIT_ONE_CELL.py](QWCT_5_6_ORDER_FLOW_DATA_AUDIT_ONE_CELL.py): SRPT и SPY, 03.06.2024 14:35–14:39:30 ET, native RAW ticks, без fill-forward, максимум 150000+1 строк на символ с отказом при cap. SPY — контроль retrieval, не доказательство полноты SRPT.

Вывод: counts по tick_type/exchange/condition, suspicious/fill-forward reject, BID_ONLY/ASK_ONLY/TWO_SIDED/LOCKED/CROSSED/ZERO_PRICE_UPDATE, zero-size sides, последнее событие, возраст, timestamp ties, наблюдавшийся trade volume, секунды со сделками и max event silence. Нулевая сторона update не превращается в malformed quote. Zero size не означает положительную доступную ликвидность; withdrawal semantics не интерпретируются.

Trade volume сравнивается с четырьмя **полностью закрытыми M1** 14:35–14:39. Границы trade buckets `[start,end)`, тик ровно cutoff остаётся в общей статистике. Бар 14:39–14:40 не читается. Native M1 имеет иные condition/FINRA/odd-lot/suspicious bar-building filters: [правила](https://www.quantconnect.com/docs/v2/cloud-platform/datasets/quantconnect/us-equities). Поэтому mismatch — диагностика, equality — не сертификат полноты. Полный parity требует тех же фильтров и независимого источника. Duplicate timestamps не удаляются: это могут быть разные реальные сделки. Отсутствие сделки не называется потерей пакетов; нужны source sequence/completeness evidence и timestamps доставки.

Всегда `coverage=NOT_CERTIFIED`, `CVD_UNAVAILABLE`, `ORDER_FLOW_UNAVAILABLE`, `can_trade=false`. Это **data-audit prototype**, не положительный Limit Player Observer. History replay фильтрует event times за cutoff, но не доказывает исторические receive-time задержки, отсутствие vendor revisions и своевременный OnData. Реальный TVX SRPT остаётся BLOCKED; существующие 10s/exact-cutoff фильтры неизменны.

## 5. Контракт будущего независимого Observer (DESIGN, не реализован)

Обязательная запись: `observation_id`, market/venue/instrument/contract, source/dataset/version, normalization, window_start/end, source_event_times, `available_at`, receive-time verification, classification_method (EXCHANGE / ESTIMATED / NONE), known/unknown signed volume и coverage denominator, quote ages каждого side, invalid/suspicious counts, tie policy, scope/BBO semantics, completeness status, reason codes, thresholds/version, `can_trade=false`. Если доступность/знак/покрытие неизвестны — abstain; неизвестное `available_at` нельзя подменять wall clock запуска notebook.

| Метка | Минимальное evidence | Условие отказа сейчас |
|---|---|---|
| ABSORPTION_CANDIDATE | Проверенный signed flow + ограниченная реакция цены, заранее заданное окно/порог | Непроверенный aggressor/coverage; OHLC не доказывает absorption |
| CVD_PRICE_DIVERGENCE | Сравнимые завершённые causal окна, известный reset CVD и unknown volume | Нет надёжной CVD; future extrema запрещены |
| POSITION_BUILD_PROXY | Последовательный flow/context; явно неизвестны identity и inventory | Не называть объём сделок открытием позиции |
| POSITION_DEFENSE_PROXY | Замороженный заранее диапазон/anchor + последующий проверенный поток | Нельзя выбрать диапазон по будущему отскоку |
| VOLUME_PROFILE_CONTEXT | Указан exact tick VAP или BAR_CLOSE_PROFILE_PROXY, native indicator/version | Нельзя выдавать M5 profile за exact footprint |
| ORDER_FLOW_UNAVAILABLE | Список отсутствующих prerequisite и источники | Текущий обязательный результат |

Положительные labels потребуют independent real positive/negative examples + holdout. Ни BPU1/BPU2, ни Risk Gate не импортируют этот слой. Порогов «Герчика» из головы не добавляем.

## 6. Проверка авторства — продвижение и блокер

Повторно открыта [2019 запись](https://rutube.ru/video/dedf3a4a8dc25130a205d9c2d59bebb5/): описанием подтверждены 11:13/27:50 BSU/BPU, 12:30 поджатие, 13:50 пила. Это всё ещё **оглавление**, не просмотренное аудио. Открытие YouTube watch через search retrieval не удалось; публичный caption-list запрос вернул HTTP 429, Rutube play-options — HTTP 403. Обхода/логина не предпринималось; это не доказательство отсутствия субтитров вообще. Новая расшифровка и идентификация спикера **не получены**. 12 пунктов 5.5 остаются USER_SUMMARY, не VERIFIED_GERCHIK_QUOTE.

| Категория | Текущее ПО / различие | Авторская проверка |
|---|---|---|
| FIXED BSU | Историческая замороженная source line; fixed-limit exact touches — отдельный proxy | UNKNOWN, 2019 11:13/27:50 только topic |
| FLOATING | Не приравнивать смену уровня к доказанному перемещению участника | UNKNOWN |
| Отбой / хвост | NEXT close away; wick fraction 0.40 — инженерный порог | UNKNOWN |
| ЛП 1/2 свечами | Геометрия возврата за frozen line | UNKNOWN; 05:07/21:30 только topic |
| Истинный пробой | 2 close + followthrough не доказывают будущую истинность | UNKNOWN |
| Зеркальный ретест | Только после ранее подтверждённого software break | UNKNOWN |
| Поджатие | Монотонное сближение closes + range shrink — heuristic | UNKNOWN; 12:30/20:20 только topic |
| Проторговка | ATR/intersections — proxy, не независимые касания | UNKNOWN |
| Пила | Перевороты closes — proxy; не объявлять ЛП | UNKNOWN; 13:50 только topic |
| Поглощение | В M5 taxonomy отсутствует signed flow | BLOCKED, конспект эфира не direct label |

`GERCHIK_DIRECT_M5_LABELS=0`, `ACCURACY=UNKNOWN`. CVD не универсальное обязательное условие методики. Полная авторская проверка остаётся открытой, а не закрывается этой таблицей.

## 7. Статус и одно следующее действие

DOCUMENTED: native trade/quote schema, one-sided update semantics, VWAP/profile implementation, OI by instrument, tier restrictions, alternative tools. CODE/UNIT: bounded data inventory и отрицательные/as-of tests. CLOUD OBSERVED: только прежние 4.8/4.9; **5.6 PENDING**. Aggressor, NBBO freshness, receive-time coverage, exact VAP, настоящая CVD и positive limit-player detection **BLOCKED**.

**Следующее действие:** в существующем `Qwct-M5-Cohort-Research/research.ipynb` добавить **одну новую Code Cell**, вставить целиком файл 5.6 и выполнить один раз. Сохранить вывод `QWCT 5.6` (SRPT + SPY). `main.py` и файлы production в этот маленький Research не переносить. Код не требует ручных правок или создания модулей.
