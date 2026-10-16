# QWCT 3.3 — Проверка, какая цена является БСУ зеркального уровня

**Состояние: исследование первоисточников выполнено; конкретные сделки, BSU-цены и BPU1 на графиках QWCT НЕ сертифицированы.** Обновлено 2026-10-16. Цель — ответить на вопрос о фиксированном уровне **до** изменения production, без подгонки June-2024 результатов. Результат 3.2 native: **92** morning-ready mirror level×day наблюдений = **35** различных алгоритмических source-lineage ключей, **65** data-consistent level×day, но **ни одного автоматически подтверждённого вручную БСУ/входа**. [Подробный исходный лог](../source_census_cloud/NATIVE_JUNE_2024_COMPLETE_RESULT.md).

## 1. Что подтверждают источники, а что они НЕ утверждают

| Источник | Подтверждено конкретным текстом | Чего НЕ подтверждает |
| --- | --- | --- |
| [Герчик, официальный сайт «БСУ и БПУ»](https://gerchik.com/torgovye-patterny/bsu-bpu-teoriya), 9 мая 2024 | БСУ может быть историческим баром слева; **БПУ1 обязан точно попасть в БСУ**; БПУ2 непосредственно следует за БПУ1, может недобить на допустимый люфт; если БПУ2 перебил БПУ1 — модель сломана; ТВХ за 30 с до закрытия БПУ2. | Не говорит, что **медиана жадного ATR кластера из программы** — это БСУ. Не назначает уровни AMAT/NFLX/SRPT. |
| **А. Герчик «Курс активного трейдера»**, главы «Торговля отбоя от ценового уровня» и «Ценовые уровни», авторская книга на [публичной электронной копии](https://studylib.net/doc/27688195/gerchik-a.m.---kurs-aktivnogo-trejdera-pokupaj--prodavaj--...) (около строк 2673–2688, 2709–2717, 4656–4677, 4715–4719, 4740–4745) | Для модели отбоя на акциях **БПУ1 должен соответствовать выбранной цене БСУ точно**, люфт BPU1 относится к Forex; зеркальная конструкция допустима с БСУ и БПУ1 по разные стороны; **плавающая зона не равна фиксированному уровню**, источники читаются слева направо; ключевые экстремумы, переломы и контекст закрытия бара важны для цены уровня. | Нельзя из этой книги автоматически вывести, что **первый** `swing_k=3` RAW экстремум текущего QWCT — *всегда* фиксированный БСУ. Книга не определяет вычисление медианы `np.median` и `0.25*ATR`. |
| [gerchik.com/pdf/algoritm_forts.pdf](https://gerchik.com/pdf/algoritm_forts.pdf), официальный домен, «Модель А. Отбой от уровня», стр. 10–11 PDF (стр. 9–10 при нумерации с нуля) | **Зеркальный БСУ high → БПУ1 low, или БСУ low → БПУ1 high**, то есть подтверждающий бар с другой стороны цены; в описанной модели говорится об одинаковом точном ценовом значении; между БСУ и БПУ1 могут быть промежуточные бары, но БПУ2 должен быть следующим. | Файл относится к **FORTS**, а не к автоматизированным акциям США; его другие параметры/рыночные «пункты» **не** переносить автоматически. Цифровые цены наших акций этим документом не подтверждены. |

**Важное разделение:**
1. ***Software mirror proxy*** `kind='mirror'`: уровень кластера со старым support/resistance и последующим D1 пробоем/ретестом. Это алгоритмический отбор направления **только**, а не баровая модель БСУ/БПУ1.
2. ***Candidate fixed BSU price***: конкретная цена, проведённая из причинного/подтверждённого экстремума или авторски допустимой ключевой точки **до** исследуемого M5.
3. ***Author model BPU1***: именно подходящий противоположный wick (у `resistance→support long` это **M5 low** при историческом `BSU high`) **в ту же фиксированную цену**. Само пересечение `M5 low ≤ level ≤ M5 high` **не является точным БПУ1**.
4. ***Post-breach D1 retest***: подтверждает ПОСЛЕДУЮЩУЮ зеркальную роль как программный критерий, но **не автоматически БПУ1, и его low/high не назначен новой фиксированной ценой BSU самим фактом ретеста**.
5. ***ATR median***: кодовое арифметическое приближение группы исторических экстремумов; медиана может находиться между тиками и меняется при изменении состава группы. **НЕ означает доказанный авторский BSU**.

## 2. Отдельно проверяем четыре цены на одинаковых замороженных D1

Набор **выбран заранее** в QWCT 3.0 как первая биржевая сессия **2024-06-03**, без просмотра её будущего M5. Это **AMAT, NFLX, SRPT** (software LONG), **MSFT** (отрицательный контроль: `role_ok=0/trend_ok=0`). Историческая 3.1 M5 проверка уже была: ноль строгих совпадений original RAW extremum для всех четырёх; M5 НЕ надо заново качать для этой части исследования. [QWCT 3.1 native результаты](./NATIVE_JUNE03_RAW_SOURCE_M5_RESULT.md).

**Новый D1-only лист сравнения** (новая отдельная ячейка QuantConnect): [`GERCHIK_3_3_D1_LEVEL_EVIDENCE_ONE_CELL.py`](./GERCHIK_3_3_D1_LEVEL_EVIDENCE_ONE_CELL.py). Он не делает сделок и не перенастраивает уже использованный BPU1:
- **A — FIRST RAW source:** первая подтверждённая исходная D1 swing high/low и точная дата `first_idx` из старой стороны.
- **B — LAST RAW confirmed source:** последний подтверждённый исходный D1 swing high/low из этого software-кластера `last_idx`; это другой потенциальный ключевой бар, но НЕ автоматически выбранный правильный BSU.
- **C — software median:** текущая кластерная медиана — диагностическая линия, не цена для автоматически допустимого лимитного входа.
- **D — post-breach historical D1 retest low/high:** противоположный экстремум на том D1 баре, где алгоритм раньше подтвердил зеркальную роль; альтернативный **диагностический бар**, но не автоматически новый BSU, особенно если прошивает цену.

Все четыре цены формируются **только** из D1 до **09:29 ET** исследуемой сессии; однозначно выводятся даты source, last swing, breach, retest, valid_from, OHLC D1 ретеста, разница в текущих тиках, и их статус по tick-grid. Графики разделяют цены и выделяют даты. Эксперимент **не** сравнивает кандидатов с исходом следующего дня, чтобы не назначать «победителя» задним числом.

## 3. Уже известно из REAL QuantConnect (не переписывать в прибыльные сделки)

| 2024-06-03 | FIRST D1 RAW экстремум | Медиана ATR-кластера | Разница в нативных тиках | Источник / M5 |
| --- | ---: | ---: | ---: | --- |
| AMAT `old resistance → long mirror support` | **214.255** | **214.460** | **+20.5** | Original исторически **OFF_GRID/REBASED**; full 78 M5; exact RAW wick = 0; 8 nonexact OHLC spans |
| NFLX `old resistance → long mirror support` | **634.540** | **633.775** | **−76.5** | **ON_GRID/MATCH**; full 78 M5; exact RAW wick = 0; 10 spans |
| SRPT `old resistance → long mirror support` | **124.510** | **125.000** | **+49** | **ON_GRID/MATCH**; 77/78 full-source M5 (missing native source minute in 13:10 bin), exact RAW wick = 0 on verified bars; 16 spans |
| MSFT `negative control` | **415.320** | **415.590** | **+27** | **REBASED**, mirror direction failed original morning gates; full 78 M5; exact RAW relevant wick = 0; 4 spans |

All shown are **original historical-source prices**, not author-assigned levels. Count of 38 price-range crosses is not BPU1 count; no TF-30sec TVX and no orders. **Three examples are NOT a statistical test of profitability nor representative of all 35 software source-lineages.**

## 4. Manual labeling criteria — do not fill unknowns by guess

For **each** D1 case the reviewer fills:
- `author_BSU_fixed_price=` exact quoted chosen historical price **OR** `UNKNOWN`;
- `author_BSU_bar_date=` known date **OR** `UNKNOWN`;
- `author_BSU_source_type=` `break_of_trend / mirror / limit_player / consolidation / false_break / unknown`;
- `source_citation=` exact authored written page, video with **actually heard** spoken answer and screenshot/time, **OR** `NONE`;
- `price_reference=` `FIRST_SWING / LAST_SWING / D1_RETEST / CLUSTER_MEDIAN / OTHER / UNKNOWN`; this is **assessment**, not software selection by best M5 fit;
- `D1_fixed_or_float=` `FIXED / FLOATING / UNKNOWN` and textual why; `pre_09_29_support=` yes/no;
- `manual_status=` `AUTHOR_LEVEL_EVIDENCE / NEEDS_HUMAN_REVIEW / INDETERMINATE`.

**Default now: `price_reference=UNKNOWN, author_BSU_fixed_price=UNKNOWN, manual_status=INDETERMINATE` for AMAT/NFLX/SRPT/MSFT.** The sources state HOW to recognize levels, **not** which exact fixed line an expert must choose in 2024 retrospectively. Do not mark `AUTHOR_LEVEL_EVIDENCE` because one proposed price would have led to a M5 touch. Keep BPU1 strict half-tick **only** for a separately approved fixed BSU price; do not relax original rules, reinterpret nonexact crosses, substitute cluster median silently, or claim 92 trade opportunities.

## 5. Action and exit rule

1. The algorithmic **native 3.2 D1 census is complete**; don't repeat it.
2. Run **one short read-only D1-only Notebook cell** for four preselected cases to expose exact historical source, alternate D1 price candidates and breached/retested OHLC. Do not rerun M1/M5 for already checked cases.
3. Reviewer chooses **verified author-grounded BSU label or `INDETERMINATE`**, explicitly recording source and why. Until then, D1 software proxy ≠ authorized BPU1 source and no production modification.
4. Only if at least one genuinely author-grounded fixed price is labeled *before* post-event outcome inspection, progress to separate BPU1/BPU2/TVX research; avoid threshold search over 35 lineages. If manual labeling remains unclear, stop this branch rather than expanding M5 indiscriminately.

**External evidence limitation:** official site article and official-domain FORTS PDF were read directly; book statements checked against public hosted transcription, **not independently the original publisher-printed page numbers**. No full video audio/transcript verified. These restrictions are substantive, not administrative.
