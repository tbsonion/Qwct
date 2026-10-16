# QWCT 5.11 — notebook хранит только короткий вызов

16.10.2026. NO_ORDERS / NOT_TVX_PASS.

## Фактический результат 5.10 от пользователя

[Сохранённая структурированная копия](QWCT_5_10_USER_RUNTIME_RESULT_2026_10_16.json). Это USER_SUPPLIED_CLOUD_STDOUT, не независимый запуск агента.

| Проверка | Результат |
|---|---|
| 14 feature results | **56/56** значений получены, errors=[] у четырёх акций. Это вычисление программных признаков, не авторская accuracy |
| Native M5 | AMAT/NFLX/MSFT 78/78; SRPT 77/78. Всего **311/312**, пропуск SRPT 13:10, одна missing-native-minute rejection |
| D1-сценарий | Все четыре строки имеют PREMARKET_PROBE_ONLY; принятое решение не обнаружено. **Причины отказов неизвестны:** все 4 D1-строки были удалены ограничителем вывода |
| 8 фильтров | **NOT EVALUATED**: четыре NO_CANONICAL_GATE_EVALUATION, все счётчики пустые. Не восемь PASS и не восемь FAIL |
| BSU/BPU/SECOND | BSU недоступен: нет принятого D1 bounce. SECOND queries=0; новый TVX не проверялся |
| FIXED/FLOATING и реакции | Их 4+4 строки OMITTED. Конкретные результаты неизвестны, нулями их не подменять |
| Сохранение notebook | Повторный реальный FAIL: **97 399 / 97 396** при лимите 64 000. Локальная оценка предыдущей упаковки не предсказала Cloud-сериализацию |

Build log сообщает Lean Engine 2.5.0.0.18188 и build ID ea2381-f7b5a2; это не независимый сертификат history/receive-time и не backtest run ID. Ордера выключены, Risk Gate не изменён, CVD отложена. Данных для изменения порогов или объявления полноценной торговой модели готовой нет.

## Исправление размера

Большой payload теперь находится **в одном отдельном Python-файле**, а не в source notebook:

| GitHub файл | Куда поместить в Cloud |
|---|---|
| [qwct_pipeline_runner.py](qwct_pipeline_runner.py) | **Новый файл в корне проекта: qwct_pipeline_runner.py** |
| [Короткая cell](QWCT_5_11_RUN_CELL.py) | **Единственная Code Cell существующего research.ipynb**, старые cells/outputs убрать |
| [Готовый notebook](QWCT_5_11_RESEARCH.ipynb) | Альтернативный полный notebook с той же одной cell; не вставлять JSON в Python |

Helper: **31 792** символа, ниже 32 000, в том числе с Windows CRLF. Notebook JSON: **533** символа, cell: **176**. Не нужны новые библиотеки или интернет-загрузка: используются стандартные Python-модули. SHA256 проверяет тот же исходный код; торговые правила и вычисления не переписаны.

Текст D1-отказов теперь имеет высший приоритет в журнале. Пропуск строки явно отмечается OUTPUT_OMITTED, не считается data PASS. Полный сырой лог остаётся в памяти helper как last_raw_output и не вставляется обратно в notebook. Загрузка helper не запускает исследование автоматически: запуск только через run().

Проверки охватывают **оба независимых лимита**: helper <32k и import-only notebook с запасом на outputs и многократное JSON-экранирование <64k. Новая Cloud-сохраняемость 5.11 пока **PENDING** — не выдавать unit tests за фактическое сохранение.

## Действие пользователя

В существующем **Qwct-M5-Cohort-Research** создать **один** файл **qwct_pipeline_runner.py** в корне и вставить в него весь одноимённый GitHub файл. Сохранить.

В **research.ipynb** оставить одну cell без старых outputs:

```python
import importlib
import qwct_pipeline_runner
importlib.reload(qwct_pipeline_runner)
qwct_pipeline_runner.run()
```

Запустить и вернуть D1-строки и END либо LOADER_ERROR. Не менять main.py или strategy-файлы. Большую/компактную cell 5.10 больше не вставлять. Это исправление доставки и журнала, а не новый широкий поиск акций или ослабление условий.
