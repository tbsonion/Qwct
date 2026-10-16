# QWCT 5.7 — результат Cloud-проверки пар и решение по native order flow

**Дата получения:** 16.10.2026. **Источник:** полный stdout, присланный пользователем после выполнения [cell 5.7](QWCT_5_7_NATIVE_QUOTE_PAIR_AUDIT_ONE_CELL.py). USER_SUPPLIED_CLOUD_OUTPUT, не независимый запуск агента. Project/run ID, deployed LEAN version и время фактического исполнения не записаны. **Окно:** SRPT/SPY, 2024-06-03 14:35:00–14:39:30 America/New_York, native RAW ticks; no orders.

## 1. Что прошло

| Метрика | SRPT | SPY |
|---|---:|---:|
| Raw rows | 833 | 39471 |
| Quote rows внутри окна | 640 | 36576 |
| Exact-timestamp quote groups | 320 | 16964 |
| PAIR_METADATA_ONLY groups | 320 | 14993 |
| Cross-venue structural pairs | 230 | 11955 |
| Trade rows | 193 | 2875 |
| Наблюдавшийся trade volume | 6973 | 218787 |
| Сделки с preceding PAIR_METADATA_ONLY | 188 | 2369 |
| Их unsigned volume | 6662 | 176072 |
| Доля этого объёма в observed volume | **95.54%** | **80.48%** |
| Всего unknown aggressor volume | **6973** | **218787** |

**Знаменатели проверены:** сумма group counts равна quote_groups; сумма relationship counts равна valid_trades; сумма relationship volumes равна observed_trade_volume у каждого символа. Это арифметическая проверка присланного stdout, не дополнительный Cloud запуск.

У SRPT **320/320** групп прошли строгое структурное описание. У SPY есть **1971** групп, не вошедших в PAIR_METADATA_ONLY. Cross-venue пары не выброшены только из-за разных exchange: это допустимая структура NBBO publication, но сама пара не доказывает исходный message mapping.

## 2. Отказы и неоднозначности SPY

| Quote group status | Групп |
|---|---:|
| CROSSED_PAIR | 86 |
| LOCKED_PAIR | 699 |
| NON_REGULAR_CONDITION | 9 |
| NOT_EXACTLY_TWO_ROWS | 1177 |

NOT_EXACTLY_TWO_ROWS не является «битой записью»: один timestamp может содержать несколько реальных публикаций. Cell отказывается выбирать пару без доказанного порядка/связи. LOCKED/CROSSED также не доказывают потерю данных или ошибку LEAN; они исключены консервативной исследовательской политикой.

| Причина отношения trade к quote | SRPT count / volume | SPY count / volume |
|---|---:|---:|
| PAIR_METADATA_ONLY | 188 / 6662 | 2369 / 176072 |
| NO_PRIOR_QUOTE_GROUP | 1 / 2 | 0 / 0 |
| QUOTE_TRADE_TIME_TIE | 4 / 309 | 51 / 3058 |
| LATEST_GROUP_CROSSED_PAIR | 0 / 0 | 110 / 13158 |
| LATEST_GROUP_LOCKED_PAIR | 0 / 0 | 148 / 10439 |
| LATEST_GROUP_NON_REGULAR_CONDITION | 0 / 0 | 9 / 646 |
| LATEST_GROUP_NOT_EXACTLY_TWO_ROWS | 0 / 0 | 188 / 15414 |

**Исключённый из structural pair join объём:** SRPT 311 (4.46%); SPY 42715 (19.52%). Его нельзя тихо приравнивать к нулевой дельте, распределять пропорционально или подписывать tick rule fallback. Весь объём, включая удачный join, пока остаётся **unknown aggressor**, поскольку сторона сделки не определялась.

## 3. Возраст публикации пары — только для preceding PAIR_METADATA_ONLY trades

| Метрика | SRPT | SPY |
|---|---:|---:|
| Число trade rows с pair report age <=0.1s | 113 | 2035 |
| <=1s | 137 | 2369 |
| <=5s | 161 | 2369 |
| Min age, секунд | 0.000001 | 0.000001 |
| Max age, секунд | 15.776772 | 0.977296 |

Это **количества сделок**, не объёмные доли. Возраст публикации полной пары — не возраст последнего реального изменения каждой стороны и не receive-time latency. Пара могла повторять старую сторону. Положительный join SRPT включает 27 сделок с report age >5s (188−161), поэтому **95.54% нельзя называть долей свежих/пригодных для торговли котировок**. Произвольный свежестной PASS не вводился.

Примеры stdout SRPT: в 14:35:00.309165 bid 124.09×300 NASDAQ, ask 124.28×100 CSE; в 14:39:26.152284 bid 124.22×200 NASDAQ, ask 124.39×400 CSE. SPY: в 14:35:00.028195 **4 quote rows**, поэтому нельзя выбрать «удобные две». Это наблюдавшиеся native значения, не придуманные snapshots.

## 4. Решение — закончить availability/pairing audit, не запускать его снова

- **PASSED / observed:** доступность реальных trade/quote ticks (5.6), 8/8 M1 volume parity (5.6), структурная проверка exact-time quote groups и причинного temporal join (5.7).
- **НЕ доказано:** надёжное восстановление конкретного исходного NBBO message из native Tick, independent source completeness, receive-time/as-of corrections, отдельные side last-change ages, aggressor side.
- **TRUE CVD:** **BLOCKED**. Native schema и проведённые проверки не предоставили exchange-classified signed volume. Идеальная пара bid/ask тоже не сообщает, кто был агрессором.
- **Quote-relative ESTIMATE:** потенциально возможен отдельный исследовательский вывод по явно выбранному subset после source mapping/validation; он не является истинной CVD. Не реализован и не принят по результату 5.7. Нельзя выдавать 95.54%/80.48% за accuracy или за покрытие реального signed flow.
- **Limit Player Observer:** положительные ABSORPTION/CVD_DIVERGENCE/POSITION_BUILD/POSITION_DEFENSE не разрешены. Текущая корректная метка — ORDER_FLOW_UNAVAILABLE. Геометрические реакции и unsigned quote metadata не доказывают крупного участника.
- **TVX / BSU / Герчик / Risk Gate:** без изменений; этот результат их не валидирует. DIRECT author labels по-прежнему 0, accuracy UNKNOWN.

## 5. Точное оставшееся препятствие

Следующий источник доказательства должен дать **документированный native NBBO mapping или готовую историю с проверяемой стороной агрессора**, а не ещё один пересчёт тех же SRPT/SPY тиков. Сравнение готовых источников, их venue/side=None semantics и лицензий уже начато в [5.6 capability matrix](QWCT_5_6_READY_ORDER_FLOW_CAPABILITIES_RU.md); ни покупка, ни новая инфраструктура не разрешаются этим результатом автоматически. До подходящего источника native true-CVD ветка считается **исследованной и заблокированной**, а не бесконечной серией диагностических cells.

От пользователя сейчас **ничего заменять или повторно запускать не требуется**. Код 5.7 остаётся воспроизводимым экспериментом; положительный торговый observer не добавляется ради видимости прогресса. Авторская проверка оригинального видео остаётся независимой незакрытой задачей.
