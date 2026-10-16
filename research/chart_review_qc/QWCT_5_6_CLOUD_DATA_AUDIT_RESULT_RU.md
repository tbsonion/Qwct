# QWCT 5.6 — результат реального Cloud audit, полученный 16.10.2026

**Provenance:** пользователь выполнил неизменённую [одну cell 5.6](QWCT_5_6_ORDER_FLOW_DATA_AUDIT_ONE_CELL.py) в QuantConnect и прислал полный stdout в чат. Это USER_SUPPLIED_CLOUD_OUTPUT, не независимо запущенный агентом runtime. ID проекта/запуска и время фактического исполнения не предоставлены. Проверяемый historical window: **SRPT/SPY, 2024-06-03 14:35:00–14:39:30 America/New_York**, RAW, native History, no orders.

## Наблюдения

| Метрика | SRPT | SPY |
|---|---:|---:|
| Raw rows (включая outside-window) | 833 | 39471 |
| Outside-window исключено | 0 | 20 |
| TRADE / valid_trades | 193 | 2875 |
| QUOTE | 640 | 36576 |
| BID_ONLY | 320 | 18288 |
| ASK_ONLY | 320 | 18288 |
| Quote updates с нулевым size другой стороны | 640 | 36576 |
| Observed trade volume за всё окно | 6973 | 218787 |
| Секунды с реальными сделками | 54 | 267 |
| Max event silence, секунд | 17.245623 | 1.910983 |
| Последняя сделка ET | 14:39:26.104930 | 14:39:29.856803 |
| Возраст последней сделки на cutoff, секунд | 3.895070 | 0.143197 |
| Последний QUOTE ET | 14:39:26.152284 | 14:39:29.561285 |
| Повторяющиеся trade timestamps | 13 | 296 |
| Число уникальных trade/quote timestamp ties | 3 | 45 |

193 + 640 = 833; 2875 + 36576 + 20 = 39471. В stdout нет suspicious/fill-forward/wrong-symbol reject counts, quote_shapes содержит только BID_ONLY/ASK_ONLY. Повторяющиеся trade timestamps не удалялись: это не доказательство дублирования сделок. Timestamp ties не задают порядок quote относительно trade.

## Сверка native M1 объёма

Это четыре полностью закрытых интервала [start,end), до cutoff. Данные одной QC vendor pipeline: parity — полезная внутренняя сверка, **не независимое доказательство полноты SIP**.

| Интервал ET | SRPT tick sum | SRPT native M1 | SPY tick sum | SPY native M1 |
|---|---:|---:|---:|---:|
| 14:35–14:36 | 1990 | 1990 | 31652 | 31652 |
| 14:36–14:37 | 209 | 209 | 39451 | 39451 |
| 14:37–14:38 | 2250 | 2250 | 69582 | 69582 |
| 14:38–14:39 | 674 | 674 | 28713 | 28713 |

**8/8 совпадений**, все tick_minus_native_minute = 0. Полуинтервал 14:39–14:39:30 входит в observed_volume, но не в эту полную M1 сверку. Нельзя сравнивать весь observed_volume только с четырьмя минутами.

QUOTE venues SRPT: ARCA/CSE/EDGX/IEX/NASDAQ/NASDAQ_BX/NASDAQ_PSX. SPY имеет также AMEX/BATS/BATS_Y/EDGA/MEMX/MIAX_PEARL/NYSE. TRADE включает FINRA: 63 SRPT, 869 SPY. Ни одно exchange name само по себе не подтверждает consolidated NBBO semantics.

## Что теперь подтверждено

- Текущая сессия пользователя действительно вернула native TRADE **и QUOTE** для обоих символов и этого окна. Предположение «quotes отсутствуют» опровергнуто.
- Все полученные quote updates односторонние. Нулевое поле другой стороны — не основание отбрасывать сам update. Диагностическое ограничение 4.9 подтверждено фактическим output.
- Покрытие API/данных и eight-bucket volume parity пройдены в этом ограниченном эксперименте. Это не универсальные права Free tier/всех лет/всех тикеров.
- Отсутствие события на конкретной секунде нельзя объявлять потерей feed. 54 секунды с trade ticks и прежние 22 SECOND bars относятся к разным представлениям/окнам и фильтрам; это не новая ошибка TVX и не повод ослаблять gate.

## Что НЕ подтверждено

- EXCHANGE_CLASSIFIED aggressor side, синхронный пригодный BBO/NBBO на каждой сделке, начальное состояние сторон, cancel/zero-size semantics, порядок equal-time событий.
- Полнота первичного потока, cross-vendor coverage, receive-time availability/OnData latency, история корректировок.
- Настоящая CVD, лимитное поглощение, набор/защита позиции одного участника, FIXED BSU и авторская точность.
- Новая стоимость/тип подписки аккаунта; новая покупка не требуется только на основании этого результата.

Результаты обоих символов корректно остались:
`coverage=NOT_CERTIFIED`, `availability=HISTORICAL_EVENT_TIME_ONLY_RECEIVE_TIME_UNKNOWN`,
`CVD_UNAVAILABLE`, `ORDER_FLOW_UNAVAILABLE`, `can_trade=false`.

**SRPT TVX остаётся BLOCKED**: этот audit не заменяет SECOND cutoff, 10-second gate и своевременную доставку. Последняя сделка совпадает с прежним 4.9 результатом.

## Следующий технический шаг

Проверить в официальном LEAN reader/готовых native quote mechanisms: что означает venue на одностороннем update, являются ли bid/ask строки частями одной snapshot, как представлены withdrawal и равные времена; возможно ли получать причинный BBO без собственной системы стакана. После этого решить, допустим ли **явно оценочный** trade classification, с unknown-volume denominator, quote age и abstention. Пока не реализовывать CVD и положительный Observer; не повторять cell 5.6 и не менять production.

Авторское видео/аудио и ground truth — отдельный открытый блокер; данный data audit их не подтверждает.

## Проверка готового native механизма после получения результата

Прочитан [TickQuoteBarConsolidator.cs](https://github.com/QuantConnect/Lean/blob/master/Common/Data/Consolidators/TickQuoteBarConsolidator.cs), метод AggregateBar: при создании нового workingBar после Consolidated он копирует previous Bid/Ask Close и LastBidSize/LastAskSize, затем обновляет поля текущим tick. В коде прямо оговорено, что такой бар не является fill-forward bar. Поэтому **is_fill_forward=false не доказывает freshness обеих сторон**. Метод также не проверяет venue/NBBO scope; этот consolidator нельзя объявлять готовым синхронным NBBO-классификатором.

[Tick.cs](https://github.com/QuantConnect/Lean/blob/master/Common/Data/Market/Tick.cs) читает equity quote поля и exchange из исходной записи; отсутствующую сторону в полный BBO сам reader не восстанавливает. Это подтверждает выбор raw inventory вместо интерпретации нулей как отсутствия quote feed. Оба прочитанных исходника — текущий upstream master; версия deployed Cloud engine не предоставлена, runtime parity не заявляется.

Решение остаётся BLOCKED для signed flow: native bar carry не решает individual side age/availability и не даёт exchange aggressor. Следующее исследование — источник начального BBO, side update time, venue scope/withdrawal semantics, а не написание CVD по свечам.
