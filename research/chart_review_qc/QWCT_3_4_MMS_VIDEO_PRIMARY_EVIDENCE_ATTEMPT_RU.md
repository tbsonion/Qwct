# QWCT 3.4 — Focused original-video verification attempt: Case 13 / MMS

**Дата:** 2026-10-15 (local), published-source date 2026-05-21. **Outcome: PARTIAL EVIDENCE; original YouTube scene and exact price re-anchor NOT VERIFIED.** Keep `author_BSU_price=UNKNOWN`. No strategy change, orders, or cloud backtest.

## Target identified unambiguously

- **Original Gerchik & Co livestream announced by the company's official Telegram channel:** https://youtube.com/live/U0xnrRrwE00 (aired **2026-05-20**). Telegram announcement: https://t.me/s/gerchikco_info?before=4579
- **Company's written recap:** https://gerchik.co/ru/analytics/tehnicheskiy-analiz/razbor-sdelok-s-aleksandrom-gerchikom-20-05-2026 — article dated **2026-05-21**, headed `Сделка 13`.
- **Attached original submitted trading screenshot:** https://gerchik.co/file/4937 . It shows **MMS / MAXIMUS Inc / NYSE** and multiple chart panels (including intraday view) with **existing hand-drawn horizontal markings and a risk/reward box**.
- **Observed from written official recap only:** existing reference was repeatedly crossed; commentary says redraw lower to where price actually held/stopped, suggesting old reference resulted in an excessive reported stop **~120 points**. The original editorial text says entry should have been lower. **The chart submission itself is NOT an independently verified video freeze-frame showing the author drawing a new line**, and the words in quotation marks in the recap are **editorial reproduction, not an authenticated audiovisual transcript**.

## Video access attempts and integrity

- Followed official article YouTube link and direct `watch?v=U0xnrRrwE00` / `youtube.com/live/U0xnrRrwE00`: external browser fetches **blocked/throttled** in this runtime.
- Checked public web search for this exact video ID plus transcript/captions/timecodes and for its republished recordings: **no reliable scene transcript/timecode obtained**.
- Tried publicly available transcript-page entry points, but they were **inaccessible**. Container outbound network DNS is blocked, hence no direct YouTube audio stream retrieval was possible.
- **No unverified timecode invented. No spoken answer or BEFORE/AFTER authored redraw claimed.**
- The trade screenshot is real enough to identify ticker and presence of prior marked levels. **It does NOT unambiguously identify an author-certified revised exact-price level, original BSU source bar, or its `confirmed_at` time**. Even the pattern type (Gerchik BSU/BPU bounce vs alternative short/level-based setup) is **NOT established by the recap**, so do not generalize it to BSU/BPU1.

## Engineering assessment

| Required for an implementable Gerchik fixed BSU | Evidence in MMS case 13 |
| --- | --- |
| Source market US equities | **YES** — screenshot identifies NYSE MMS |
| Original wrong level reference line | **Visually existing line(s), numeric/candle provenance unverified** |
| Revised author-drawn reference line exact price and source candle | **NO** |
| Rule explaining why that candle/high/low/close is chosen over other candidates | **NO** |
| Time when re-anchor first justified from then-known candles (PIT) | **NO** |
| Confirmed Gerchik BSU/BPU1 model applicability | **NO** |
| Exact tested objective selection algorithm and profitability | **NO** |

**Conclusion:** documented evidence supports **discretionary context-sensitive adjustment of frequently crossed levels**; it does not demonstrate the mathematical function `select_FIXED_BSU(D1)`. We should **not** reclassify MMS as a certified BSU, or assign FIRST/LAST/MEDIAN to AMAT/NFLX/SRPT based on the recap. All four 2024 cases stay **INDETERMINATE**.

## One narrowly defined remaining dependency

Access to the actual **MMS Case 13 segment** of https://youtube.com/live/U0xnrRrwE00 containing **the chart and author's correction**, preferably MP4 or exact subtitles **PLUS visible chart frames**. With only the current recap no further algorithm research/test can resolve whether the revised price was anchored to original high/low, close, a second exact repeat, a false breakout, or something else. When supplied, record BEFORE/AFTER screenshot, author-spoken rule (or clearly transcription uncertainty), episode timecode, OHLC source candle, and `available_at`. Without that primary evidence, **STOP**, rather than manufacturing signals/backtests.

**Do not infer from the 2026-05-20 broadcast date that the user-submitted historical MMS trade screenshot depicts that same day's trading session.**
