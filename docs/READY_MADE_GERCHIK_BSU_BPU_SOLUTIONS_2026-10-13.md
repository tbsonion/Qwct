# Qwct — готовые решения для BSU → BPU1 → BPU2 → TVX (13.10.2026)

**Решение: research-first, без изменения сигнального кода, без торговли.** Проверены первичные страницы Gerchik, MetaTrader Market, TradingView и QuantConnect, плюс публичный GitHub code/repository search. Полного открытого drop-in модуля **точного** Gerchik BSU/BPU/TVX для LEAN Python не обнаружено в проверенных источниках. Это не доказательство отсутствия такого проекта повсюду.

## Точка отсчёта: настоящий Qwct Cloud

- LEAN Cloud v2.5.0.0.18179, 2024-01-01…2024-02-05; RESEARCH ONLY.
- На NVDA 2024-01-02 BSU observer **ARMED**, исходный RAW swing high 2023-08-24 **$502.66**, D1 screening cluster **$502.57439794**. В 76 native M5 свечах максимум high **$493.00**, разрыв **$9.66**, точных касаний **0**. Это **правильное отсутствие** BPU1, а не баг BSU.
- 6 принятых D1 setup, 456 M5 checks, BPU1=0, BPU2=0, intent=0, ERROR=0. Второе подтверждение и TVX не верифицированы.
- **Исходный авторский стандарт:** BSU — исходный бар уровня; BPU1 касается **точно** того же экстремума (между BSU и BPU1 возможны промежуточные бары); BPU2 **следующая** свеча, на той же стороне уровня, не пробивает BPU1 и может недобрать уровень в пределах **20% Stop Loss**; TVX — лимитный ордер за **30 секунд до завершения BPU2**. [Gerchik.com, БСУ и БПУ](https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya).

## 1. РЕАЛЬНО существующие сторонние индикаторы

| Решение / ссылка | Что реально заявлено | Что отсутствует или отличается | Код для прямой интеграции Qwct | Вывод |
|---|---|---|---|---|
| **[Trade by levels — MetaTrader 4](https://www.mql5.com/ru/market/product/36442)**, Dmitriy Tyunin, версия 2.3, **FREE** (2019) | Детектор BSU/BPU1/BPU2; BSU и BPU1 high/low совпадают до пункта, произвольный интервал до BPU1, BPU2 непосредственно за BPU1, допускается люфт; описание содержит TVX -30s | Страница также описывает **вход на четвёртом баре**, таймфрейм **H1** и стоп 0.2–0.5% цены — **не** автоматическая эквивалентность Qwct M5/авторскому TVX. В код проекта LEAN нельзя вставить MT4 индикатор. Поведение не испытано. | **Нет подтверждённого доступного исходного кода / Python API** | **Лучший бесплатный внешний визуальный comparator** |
| **[TBL for mt5 — MetaTrader 5](https://www.mql5.com/en/market/product/39529)**, тот же автор, версия 1.0, **FREE** (2019) | Та же BSU→BPU1→BPU2 схема, BPU1 совпадает до пункта, соседний BPU2, люфт **2–3 points**, -30s limit описан | 2–3 points ≠ авторские **20% Stop Loss** для всех тикеров; описание H1/четвёртого бара может отличаться от проекта; нет проверки US equity RAW history/делистингов. Есть пользовательские жалобы про ATR в комментариях, но не наш объективный тест. | **Нет подтверждённого доступного исходного кода / LEAN API** | **Лучший MT5 бесплатный comparator**, но не production signal engine |
| **[VibeFox BSU BPU — MetaTrader 5](https://www.mql5.com/en/market/product/183947)**, 1.0, **$30** (июль 2026) | BSU = fractal swing (Wing), BPU = последующие касания зоны/отбой, уровни/пометки bounce и breakout | ТОЛЕРАНС — зона и даже автоподбор; не доказаны строгий BPU1 exact tick, следующий BPU2, оригинальный -30s TVX. По концепции это **другая** модель. | Нет подтверждения открытого исходника или LEAN интеграции | **Не покупать для Qwct** без side-by-side доказательства |
| **[GERCHIK + SMC God Mode, TradingView](https://www.tradingview.com/script/epyXTsv4-SMC-God-Mode-PREMIUM-v13-0/)**, group0403, **invite-only** | Автор заявляет автоматическое BSU/BPU, ложные пробои, ATR, кластеризацию | Сильные рекламные утверждения не подтверждены независимым точечным тестом; смешивает Gerchik с SMC и 0.20% tolerance. Исходник закрыт, нет официального LEAN port. | Нет | **Не использовать как замену Qwct** |
| **[Talbor BSU/BPU demo](https://rutube.ru/video/ebb2c9cffbe8803b8489121548a4509b/)** (2023) | В описании видео указан автоматический индикатор BSU/BPU1/BPU2, ссылка на `talbor.com/bsu-bpu` | Страница продукта сейчас не открылась при проверке, доступность, исходники и актуальная версия неизвестны | Не подтверждён | Только архивный lead |

**Важно:** Цена FREE означает бесплатный индикатор для MetaTrader, **не** open-source и **не** лицензия на перенос алгоритма. Ни один из перечисленных продуктов не является кодом Python для LEAN. У обоих Trade by levels полезна *проверка визуальных паттернов*, но MQL5 данные котировок могут отличаться от QuantConnect, поэтому одинаковые тикеры и даты — не автоматическая data parity.

## 2. Что уже существует в НАТИВНОМ LEAN и нужно переиспользовать

| Компонент | Официальная готовая реализация | Польза/ограничение |
|---|---|---|
| **Confirmed D1 swing pivot** | [`pphl(symbol,10,10,100)` — PivotPointsHighLow](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/pivot-points-high-low) | Готовая reference-линия свингов. Не называет Gerchik BSU и не гарантирует происхождение native RAW pivot/его cluster/зеркальность. |
| **Хранение последних закрытых M5 свечей** | [LEAN `RollingWindow[TradeBar]`](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/rolling-window); у consolidator **есть встроенное окно** | Нет нужды писать собственный window/history engine. В Qwct уже есть M5 consolidator и observer; **не дублировать**. |
| **Native M5 из minute/second** | [TradeBar/time-period consolidators](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators) | У Qwct уже есть; сохранять native `Time/EndTime`, regular-hours alignment, отсутствие fill-forward. |
| **Исторический поиск кандидатов** | [QuantBook Research + native US Equities Minute History](https://www.quantconnect.com/docs/v2/research-environment/datasets/us-equity) | Использовать существующую историю и независимую ручную/пакетную проверку. При запуске в research **все будущие бары доступны**: строго эмулировать as-of 09:29 D1 и BPU1→BPU2 без future leakage. |
| **Секундный cutoff** | [US Equity SECOND data](https://www.quantconnect.com/docs/v2/lean-engine/data-format/us-equity) и native `OnData` | Feed доступен в движке, но **само -30s правило Герчика не встроено**. В Qwct уже есть `native_second_tvx.py` и `second_runtime.py`; подтверждения Cloud в `tvx_seconds=true` пока нет. |
| **Свечные паттерны** | [LEAN Candlestick Patterns](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/candlestick-patterns) | Hammer/Engulfing и т.д. — отдельные паттерны, **не** BPU2/exact-touch. Не применять как drop-in. |

Первоисточник QuantConnect отдельно отмечает, что **нет встроенного готового метода именно для support/resistance touch detection**, а pivots/min-max лишь строительные блоки: [Support & Resistance Touch Detection, QuantConnect forum](https://www.quantconnect.com/forum/discussion/16677/support-amp-resistance-quot-touch-detection-quot/). Значит, не следует ожидать встроенной команды `gerchik_bpu2()`.

## 3. Самый дешёвый и проверяемый путь, ПРЕЖДЕ чем новый код

1. **Нулевое новое ядро:** оставить текущие `strategy/patterns_bsu.py`, `strategy/bsu_bridge.py`, `strategy/native_second_tvx.py` и LEAN subscription/consolidation. Не разрабатывать собственный pivot/feed/OMS.
2. **Бесплатный comparator:** если доступен MT5 с данными нужной акции, запустить **TBL for mt5** и вручную сравнить несколько бесспорных положительных/отрицательных примеров; не принимать значения TBL как «правду Герчика». Проверять точные RAW хай/лоу по отдельно полученным LEAN барам.
3. **Поиск реального Qwct примера:** сначала расширять native LEAN **signal-only** Cloud период умеренными порциями, сохраняя точный BSU pivot и закрытые M5; искать *дни, когда M5 high/low действительно достигает оригинального D1 BSU*. На NVDA 2024-01-02 это невозможно, так как разрыв $9.66. Если повторяющихся кейсов недостаточно, **QuantBook** как отдельная offline-проверка по *point-in-time universe* и закрытым D1/M5, не как замена событийному Cloud validation.
4. Для каждого реально достигнутого BSU сохранить **symbol, date, native RAW D1 pivot date/price, 09:29 accepted decision, M5 EndTime, exact/under/over touch, следующий M5 EndTime, причина invalidation**. Только затем считать BPU1→BPU2. Все `0` остаются нулями, если правила не выполняются.
5. **TVX отдельный этап**: опциональный native SEC backtest с реальным -30s cutoff; проверить 270 последовательных торгуемых секунд, отсутствующие секунды и post-close reconciliation. Не выводить -30s из итогового M5 бара (lookahead).
6. Полную модель Герчика/доходность **не утверждать** без независимого размеченного набора графиков, реальных native data parity и статистики на длинном периоде. Все orders **OFF**.

## 4. Решение «покупать/портировать/писать»

- **Не покупать** платный индикатор только ради Qwct. Есть бесплатный внешне близкий comparator (Trade by levels/TBL).
- **Не портировать** MT4/MT5/TradingView закрытые решения: нет подтверждённого переносимого кода и воспроизводимой кросс-платформенной эквивалентности.
- **Не строить с нуля** новые indicators, feed, rolling-window, M5 consolidator, risk/OMS.
- **Единственный возможный узкий новый код позже** — read-only диагностика/case-finder поверх текущих Qwct observer и *готовых* LEAN `History`, `PPHL`, `RollingWindow`; сначала проверить более длинный native Cloud smoke. Ни новых торговых ордеров, ни искусственных touch.
- Вопросы для проверок: наличие валидных цен на MT5 для **американских акций** (а не CFD); совпадение corporate actions/tick grid; exact touch vs zone; временная доступность D1 pivot; -30s SEC цена vs full BPU2; ложные сигналы и удобство экспорта исторических сигналов.

## Ссылки на первичные источники (проверены 2026-10-13)

1. [Gerchik.com — БСУ и БПУ](https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya).
2. [MQL5 Trade by levels MT4 FREE](https://www.mql5.com/ru/market/product/36442).
3. [MQL5 TBL for mt5 FREE](https://www.mql5.com/en/market/product/39529).
4. [MQL5 VibeFox BSU BPU $30](https://www.mql5.com/en/market/product/183947).
5. [TradingView invite-only GERCHIK+SMC](https://www.tradingview.com/script/epyXTsv4-SMC-God-Mode-PREMIUM-v13-0/).
6. [QuantConnect PPHL](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/pivot-points-high-low).
7. [QuantConnect RollingWindow](https://www.quantconnect.com/docs/v2/writing-algorithms/historical-data/rolling-window).
8. [QuantConnect native consolidators](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators).
9. [QuantConnect US Equity minute Research](https://www.quantconnect.com/docs/v2/research-environment/datasets/us-equity).
10. [QuantConnect research lookahead](https://www.quantconnect.com/docs/v2/research-environment/datasets/key-concepts).
11. [QuantConnect S/R touch forum](https://www.quantconnect.com/forum/discussion/16677/support-amp-resistance-quot-touch-detection-quot/).
