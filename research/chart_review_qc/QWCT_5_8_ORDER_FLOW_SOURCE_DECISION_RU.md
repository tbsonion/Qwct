# QWCT 5.8 — решение по источнику order flow и стоимости
**Проверено 16.10.2026. Research-only. Никаких покупок/новых Cloud cells/изменений стратегии.**

## Решение

1. **Native QC TRUE CVD остаётся BLOCKED.** Проверки 5.6–5.7 доказали наличие ticks, volume parity и структурных пар, а не exchange aggressor.
2. **Native ESTIMATED Delta не внедряем в положительный Observer сейчас.** Quote-relative исследовательский proxy принципиально возможен с явным ESTIMATED/UNVERIFIED, но точное NBBO mapping и ошибка классификации ещё не установлены.
3. **Выбранный кандидат для независимого benchmark:** Databento **XNAS.ITCH / TBBO**, только SRPT+SPY, один исторический интервал, **usage-based**, без месячной подписки. Это Nasdaq-venue subset, не весь рынок и не доказательство одного крупного игрока. Источник выбран документально; данные НЕ получены, actual side coverage UNKNOWN.
4. **AlgoSeek TAQ/пакет и месячные планы пока не покупать.** Историческую точную цену маленького запроса сначала получить через бесплатный metadata.get_cost. Без авторизованного Databento доступа конкретная сумма остаётся UNKNOWN.

## 1. Native mapping: что проверено и где заканчивается доказательство

[QC equity format](https://www.quantconnect.com/docs/v2/lean-engine/data-format/us-equity) и [pinned LEAN equity readme](https://github.com/QuantConnect/Lean/blob/1a914155265ef0f3e979b7d6bd9671b1e8e3cb8f/Data/equity/readme.md) описывают one-sided quote ticks с time, bid/ask price/size, exchange, condition и suspicious. [Reader Tick.cs](https://github.com/QuantConnect/Lean/blob/1a914155265ef0f3e979b7d6bd9671b1e8e3cb8f/Common/Data/Market/Tick.cs) разбирает эти поля, но не даёт исходный TAQ EventType (NB vs market-center), source sequence, receive time или aggressor.

[QC handling-data](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/handling-data) называет QuoteBar консолидацией NBBO quotes. Это документация агрегата; из неё нельзя вывести правило выбора каждой raw quote row.

**Ограниченный поиск реализации:** получено полное recursive tree публичного LEAN на pinned commit (truncated=false); среди путей AlgoSeek/converter найдены futures converters, equity converter не найден. GitHub search AlgoSeekEquity не дал результатов. Это **не доказательство отсутствия** частного/иначе названного upstream converter. Проверенная открытая equity conversion specification, однозначно устанавливающая какие TAQ event types попадают в QC Tick, **не найдена**. Futures converter не является доказательством equity mapping.

[AlgoSeek TAQ API tutorial](https://algoseek.com/docs/rest-api/tutorial/fetch-your-first-market-data) сохраняет явный EventType и показывает фильтр QUOTE BID NB / QUOTE ASK NB, отдельно от market-center QUOTE BID / QUOTE ASK. Поэтому прямой продукт поставщика может закрыть ambiguity типа события, но это другая схема, а не автоматически дополнительные native Tick поля.

**Фактический вывод:** paired NBBO explanation совместима с нашим output, но source mapping остаётся UNVERIFIED. Нельзя объявлять NBBO доказанным для всех native групп по одинаковым timestamps или совпадению M1 volume.

## 2. Готовые источники вместо собственного стакана

| Решение | Что уже готово | Главная граница | Выбор |
|---|---|---|---|
| QC native Trade/Quote Tick | Уже получены реальные данные; native History | Нет native aggressor, EventType NB и receive time в просмотренном формате | Сохранить для QWCT; TRUE_CVD BLOCKED |
| Прямой AlgoSeek TAQ | EventType и NBBO rows; готовый API | SIP trade/quote не превращается в exchange-classified buy/sell; quote classification всё ещё estimate | Не покупать ради TRUE CVD |
| AlgoSeek Extended TAQ / Buy-Sell Pressure | Готовые derived bars/аналитика вместо собственного вычислителя | Производные/вероятностные признаки не становятся истинной CVD или identity игрока | Не подменять ими ground truth |
| Databento XNAS.ITCH Trades | Готовая нормализация executed trades, side, sequence и timestamps | Nasdaq venue only; side=None возможен | Подходит для signed subset, если качество реальных данных подтверждено |
| Databento XNAS.ITCH TBBO | Сделка + BBO непосредственно до её эффекта; поля side и provenance | BBO одной venue, не национальный NBBO; side=N остаётся неизвестным | **Выбран для небольшого benchmark**; не активирован |
| Databento TCBBO / несколько venues | Готовый consolidated trade/BBO формат | Dataset/publisher coverage и side=N требуют проверки; нельзя обещать full-market signed flow | Не расширять первый запрос до всех venues/MBO |

[AlgoSeek Buy/Sell Pressure product](https://algoseek.com/dataset/us-equities-buy-sell-pressure-and-retail-indicators-minute-bar/) прямо описывает вероятностные retail indicators. Эти сигналы не являются подтверждением одного лимитного участника.

[Databento TBBO/TCBBO schema](https://databento.com/docs/schemas-and-data-formats/tbbo): есть цена/size, предшествующий BBO, publisher, sequence, event/receive timestamps и side B/A/N. Это готовая альтернатива нашему собственному quote join. Порядок bid/ask и знака нельзя путать: в нормализованном Trade **B = buy aggressor, A = sell aggressor, N = unknown**, а не «A означает купили по ask». Сторона пассивного Fill — другой объект.

[Спецификация XNAS.ITCH](https://databento.com/docs/venues-and-datasets/xnas-itch): Order Executed нормализуется в Trade/Fill/Cancel; некоторые non-printable Trade omitted; non-displayed Trade (Non-Cross) и Cross Trade дают side=None. Поэтому маркетинговое обещание «direct feed / 100% accuracy» не является гарантией наличия знака у всех сделок. Для суммирования использовать нормализованные Trade records/TBBO, не складывать Trade+Fill+Cancel как три сделки.

[Каталог US equities](https://databento.com/catalog/us-equities) документирует XNAS.ITCH как Nasdaq feed, отдельный от остальных exchanges/TRF. Покрытие всех NMS tickers не равно покрытию всех их сделок: SPY и SRPT торгуются на разных venues. Вывод по Nasdaq subset нельзя сопоставлять с полным QC volume как с одним знаменателем.

## 3. Деньги: опубликованные цены и неизвестное

| Вариант | Проверенная цена/условие | Практический вывод |
|---|---|---|
| Повторное использование уже доступного QC | Новая покупка не нужна для данных, уже полученных пользователем; конкретный tier/account bill не проверен | Не обещаем бесплатные ticks всем Free accounts |
| AlgoSeek Equity TAQ | **$1500/месяц**, individual dataset lease minimum **12 месяцев** | Минимальная номинальная сумма **$18000** при этом list rate; custom/incubator условия отдельно |
| AlgoSeek Extended TAQ minute bars | **$1500/месяц**, те же общие lease terms | Покупка analytics не решает ground-truth signed-side вопрос |
| AlgoSeek Equities Research Package | **$2500/месяц, 2-year term** | Номинально **$60000**, несоразмерно первому QWCT test |
| Databento historical usage | Публичная equities страница: **от $0.40/GB**; исторический usage-based доступ без обязательной подписки | Это нижняя рекламная ставка, **не точный XNAS/TBBO тариф и не цена нашего окна** |
| Databento subscription | Entry Standard опубликован **$199/месяц**; отдельное обновление июня 2026 меняет один equities plan до **$4000/месяц** | Не выбирать месячный план для tiny historical test; не путать планы и CME default pricing |
| Databento credits | Публично **$125** новым подходящим пользователям, срок 6 месяцев, один набор на team | Eligibility/balance пользователя не проверены; не считаем sample автоматически бесплатным |
| Metadata cost query | Документация: metadata/symbology бесплатно | Нужен API-auth; это не загрузка market data |
| Конкретный SRPT/SPY TBBO запрос | **UNKNOWN** — не выполнен authenticated get_cost | Никакого вымышленного $0.01/$1 за тест |

Источники цен: [AlgoSeek list pricing/lease](https://algoseek.com/pricing/), [Databento equities lower bound](https://databento.com/equities), [Databento pricing/credits](https://databento.com/pricing), [январский Standard plan](https://databento.com/blog/upcoming-changes-to-pricing-plans-in-january-2025), [обновление 22.06.2026](https://databento.com/blog/updates-to-subscription-pricing). Текущая product page XNAS указывает, что live TotalView требует Plus/Unlimited; исторический usage доступ отдельно. **Мы не выбираем live/месячный план.**

## 4. Готовый точный запрос стоимости, без загрузки

[QWCT_5_8_DATABENTO_METADATA_QUOTE_REQUEST.json](QWCT_5_8_DATABENTO_METADATA_QUOTE_REQUEST.json) фиксирует параметры для официального **Historical.metadata.get_cost**, а не свой downloader:

- dataset XNAS.ITCH; symbols SRPT, SPY; raw_symbol; schema **tbbo**;
- quote range **2024-06-03T18:30:00Z .. 18:40:00Z**, начало включено, конец исключён;
- benchmark subset **18:35:00Z .. 18:39:30Z**, cutoff включён; до загрузки проверить доступность даты/schema/symbol mapping;
- не запрашивать MBO/all symbols/все venues или одновременно Trades и TBBO с дублирующими сделками.

[Официальный Historical API](https://databento.com/docs/api-reference-historical?historical=http) предупреждает, что get_cost может завышать оценку для диапазонов, не кратных 10 минутам. Поэтому указан один полный 10-minute quote, а не «точные 270 секунд». Реальный счёт считается по переданным несжатым binary bytes; цена get_cost — estimate, не жёсткий spending cap. Повторный stream может тарифицироваться повторно. Эти расходы сейчас **не понесены**.

Временные фильтры API для схем с ts_recv основаны на **ts_recv**, не ts_event. При будущем исследовании cutoff проверять по обоим временам; vendor capture receipt не является receive-time пользователя или QuantConnect OnData. Правую границу и будущие записи не использовать для предшествующих наблюдений.

**Authenticated quote не выполнен:** у текущих подключённых инструментов нет Databento session/API authorization. Никаких ключей не искали, не запрашивали в чат и не вставляли в GitHub. JSON — спецификация, не выполненный заказ. Чтобы получить реальную сумму, требуется авторизованный бесплатный metadata query; покупка/скачивание не требуется для получения estimate.

## 5. Существенное актуальное изменение данных

[Официальное объявление от 30.09.2026](https://databento.com/blog/nasdaq-historical-data-changes-2026-09): **31.10.2026** меняется историческая XNAS.ITCH база (pre-28.11.2023 instrument IDs, winter after-hours coverage, midnight snapshots); preview доступен отдельно до cutover. Наш кейс June 2024 RTH не совпадает с перечисленными pre-2023/winter cases, но runtime parity версий не проверена. Для воспроизводимости сохранить gateway, дату извлечения, schema/SDK version и checksum; не смешивать preview и normal history. Preview сам по себе не бесплатный feed.

## 6. Go/No-go и следующий шаг

**Закрыто:** сравнительное исследование источников, pricing basis, native mapping limitation, выбор узкого готового benchmark и спецификация quote-only запроса. Никакого homemade order book/индикатора/нового Cloud test.

**GO сейчас:** получить **бесплатный авторизованный cost estimate** для JSON, когда есть Databento account access. **DATA BLOCKED:** sample не загружен, точная цена и доля side=B/A/N не измерены. После доступного sample сначала оценить known/unknown-side volume и timestamps на одной venue; только затем решать о quote-relative ESTIMATED Delta. Отсутствующий знак не заменять нулём, volume=None не синтезировать; не переносить partial venue CVD на весь рынок.

**NO-GO:** настоящая полная CVD US shares из current native data, положительные Limit Player labels, изменение BPU/Risk Gate, сделки, месячная подписка «на всякий случай». Даже надёжный signed subset не доказывает identity или факт набора позиции крупным участником.

**Файлы QuantConnect заменять не нужно.** Исследовательский outcome — source choice + конкретный access/cost blocker, а не очередное предложение прогнать те же ticks.
