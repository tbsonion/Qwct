# QWCT 5.7 — native bid/ask: готовые механизмы и границы доверия

**Решение:** native LEAN умеет сохранять bid/ask и строить QuoteBar, но просмотренные API не предоставляют готовый проверенный контракт «свежий bid + свежий ask + надёжный aggressor». Положительный Order Flow Observer и CVD пока BLOCKED. Подготовлен один bounded metadata audit; это не новый feed, consolidator, стакан или индикатор.

Основание — [Cloud output 5.6](QWCT_5_6_CLOUD_DATA_AUDIT_RESULT_RU.md): реальные сделки и QUOTE для SRPT/SPY, 8/8 совпадений M1 объёма. Следующий вопрос **не наличие quotes**, а способ их публикации и причинное сопоставление со сделками. Торговые файлы/пороги не изменены.

## 1. Проверенные готовые решения

Исходники прочитаны на upstream LEAN commit **`1a914155265ef0f3e979b7d6bd9671b1e8e3cb8f`** (HEAD, получен git ls-remote 16.10.2026). Версия Cloud engine пользователя UNKNOWN; это SOURCE_VERIFIED, а не проверка runtime parity.

| Native решение | Что действительно делает | Почему недостаточно для signed flow |
|---|---|---|
| [Tick equity reader](https://github.com/QuantConnect/Lean/blob/1a914155265ef0f3e979b7d6bd9671b1e8e3cb8f/Common/Data/Market/Tick.cs) | Читает timestamp, bid/ask prices/sizes, exchange, sale_condition, suspicious; нули отсутствующей стороны не превращает в полный quote | Нет exchange aggressor и исходного TAQ event_type/sequence/receive-time в просмотренном equity формате |
| [SecurityCache](https://github.com/QuantConnect/Lean/blob/1a914155265ef0f3e979b7d6bd9671b1e8e3cb8f/Common/Securities/SecurityCache.cs) | Для QUOTE обновляет только ненулевые price/size каждой стороны | Публичные bid/ask scalar fields не сопровождаются отдельными last-change timestamp/venue; нули не очищают их в этом update path. Это cache для движка, а не гарантия корректной обработки withdraw для CVD |
| [QuoteBar.Update](https://github.com/QuantConnect/Lean/blob/1a914155265ef0f3e979b7d6bd9671b1e8e3cb8f/Common/Data/Market/QuoteBar.cs) | Обновляет bid/ask OHLC, LastBidSize/LastAskSize только при size > 0 | EndTime — время бара, не last-change обеих сторон; нулевой size не сбрасывает LastSize в этом методе |
| [TickQuoteBarConsolidator](https://github.com/QuantConnect/Lean/blob/1a914155265ef0f3e979b7d6bd9671b1e8e3cb8f/Common/Data/Consolidators/TickQuoteBarConsolidator.cs) | Фильтрует QUOTE; при новом workingBar переносит previous bid/ask Close и sizes, затем применяет tick | Перенос возможен в баре без fill-forward flag; метод не является venue-aware NBBO builder и не выдаёт separate-side ages |
| Native History[QuoteBar] SECOND/MINUTE | [Документация](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/handling-data) называет QuoteBars консолидацией NBBO quotes | Готовый context comparator, но aggregate OHLC не восстанавливает порядок внутри секунды; close нельзя применять к более раннему trade |

Вывод **не** «native quotes бесполезны». Для обычного LEAN pricing использовать native механизмы. Для causal aggressor estimate требуется дополнительное доказательство структуры исходных quote observations; current cache values в notebook не являются historical as-of quote.

## 2. Что объясняет первичный поставщик

[AlgoSeek US Equity TAQ Guide, стр. 7–9](https://us-equity-market-data-docs.s3.amazonaws.com/algoseek.US.Equity.TAQ.pdf) различает market-center QUOTE BID/ASK и QUOTE BID NB/ASK NB. При изменении NBBO пример показывает две NB-строки с одним timestamp, в том числе с разными exchanges для сторон. Возможны несколько изменений с одинаковым временем, transient crossed/locked состояния, zero quotes на закрытии и поздние trade cancellations/corrections.

Следовательно:

- Равные 320/320 и 18288/18288 BID_ONLY/ASK_ONLY в 5.6 **совместимы** с paired NBBO публикацией, но не доказывают её.
- Разные биржи у bid/ask не являются автоматической ошибкой NBBO.
- Две строки с одним временем не означают, что обе стороны физически изменились в этот момент: мог быть повтор состояния.
- Исходный vendor TAQ и QC native format — разные схемы. Точная политика отбора NB rows в QC conversion не установлена этим чтением. Не переносить все поля/гарантии исходного продукта в native Tick.

[QC Data Preparation](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/data-preparation) описывает consolidated SIP sourcing; [QC equity format](https://www.quantconnect.com/docs/v2/lean-engine/data-format/us-equity) — one-sided ticks. Это подтверждает документированную поддержку NBBO-контекста, но не полноту каждого конкретного runtime window. Endpoint 5.6 доказал только ограниченные availability/parity.

## 3. Выбранный минимальный эксперимент

[QWCT_5_7_NATIVE_QUOTE_PAIR_AUDIT_ONE_CELL.py](QWCT_5_7_NATIVE_QUOTE_PAIR_AUDIT_ONE_CELL.py) — **одна самостоятельная cell**, SRPT/SPY, прежнее окно 2024-06-03 14:35–14:39:30 ET. Использует native RAW History[Tick], no fill-forward, cap 150000+1 на символ. **Свечи не создаются**, asynchronous sides не соединяются, состояния стакана нет.

Проверяет:

1. Группы по **точному исходному timestamp**, без округления; exchange сохраняется у каждой стороны. Группы с >2 строками не разделяются искусственно и не дедуплицируются.
2. Структурная пара: ровно две строки, одна BID_ONLY и одна ASK_ONLY, положительные prices/sizes, непустые venues, condition hex 1, без suspicious/fill-forward; bid < ask. Эта regular-only политика — **консервативный audit subset**, не точная копия QC bar-building filters и не правило Герчика. Другие случаи выводятся отдельными причинами; locked/crossed не повышаются до пригодной пары.
3. Для каждой действительной сделки: NO_PRIOR_QUOTE_GROUP, QUOTE_TRADE_TIME_TIE, LATEST_GROUP_<причина> или PAIR_METADATA_ONLY. Рассматривается только последняя группа **строго раньше** сделки. Если последняя группа плохая, более ранняя хорошая не используется. Quote на том же timestamp блокирует вывод о порядке, даже если есть более ранняя пара.
4. Счётчики и unsigned volume по причинам, min/max возраста **публикации пары**, количества <=0.1/1/5s как описательная чувствительность, **без порога PASS**. Этот возраст не является last-change age каждой стороны.
5. До шести примеров реальных групп с prices/sizes/venues/time. Future rows исключаются; cutoff включён. Никаких знаков buy/sell, CVD, положительного absorption и source completeness сертификата.

Без pre-window snapshot ранние сделки честно попадают в NO_PRIOR_QUOTE_GROUP; неизвестное состояние не достраивается. Итог всегда ORDER_FLOW_UNAVAILABLE / CVD_UNAVAILABLE, **весь наблюдавшийся trade volume остаётся unknown_aggressor_volume**. available_at=null, receive_time/side_last_change_times UNKNOWN. Структурный pair — metadata, не факт наличия активного крупного участника.

## 4. Критерий решения после output

| Реальный output | Следующее решение |
|---|---|
| Большинство групп содержит одну однозначную строгую пару; время до trades разумно | Это основание продолжить проверку mapping/публикации и классификационной ошибки; **не** разрешение TRUE_CVD |
| Много многозначных/одиночных/нулевых групп или ties | Не придумывать pairing/order; оценка по текущему subset BLOCKED |
| Нет prior groups/много старых report timestamps | Не считать последнюю cached цену свежей; отдельный source/snapshot вопрос |
| Ошибка History/schema/row cap | Сохранить причину; не ослаблять cap/фильтры ради положительного результата |

Даже идеальные пары не дают exchange aggressor. После подтверждения источника price-vs-quote может быть только **ESTIMATED**, с unknown volume и independent validation. Tick rule по цене сделки — другая оценка; нет silent fallback. CVD из OHLCV запрещена.

## 5. Валидация и действия

**CODE / UNIT:** 20 новых тестов на structural tuples (не candles/fills): crossed/locked, flags/condition/zero sizes, multiple rows, timestamps/ties, future exclusions, invalid latest group без fallback, сохранение повторных trades/volume denominator и отсутствие production imports/orders/bar generation. **CLOUD 5.7 PENDING**, никакие показатели 5.6 не переименованы в результат 5.7. Источники прочитаны; source verification не заменяет deployed runtime proof. Новых dependencies/подписок/платных данных нет.

**Единственное действие для пользователя:** в существующем `Qwct-M5-Cohort-Research/research.ipynb` заменить код диагностической cell 5.6 **целиком** кодом [cell 5.7](QWCT_5_7_NATIVE_QUOTE_PAIR_AUDIT_ONE_CELL.py), выполнить один раз и передать строки QWCT 5.7. main.py и остальные файлы не менять. Предыдущий результат 5.6 сохранён в GitHub.
