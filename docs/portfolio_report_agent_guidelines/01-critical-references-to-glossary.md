## 0. Critical references — read first

Before running the report, read these files. They are normative; this guidelines doc references them.

**MAKE SURE YOU READ FULL CONTENT OF THIS FILE BY PARTIAL READING**
**DO NOT EDIT/DELETE SETTINGS.md, HOLDINGS.md UNLESS USER SPECIFICALLY ASK TO**
**DO NOT EDIT FILES WHILE GENERATING REPORT, YOU SHOULD ONLY ADD THE REPORT AND TEMP FILES**
**ALL THE TEMP FILES CREATED DURING THE PROCESS SHOULD BE REMOVED AFTER REPORT GENERATED**

- `AGENTS.md` — repo-wide agent guidance.
- `README.md` — project overview.
- `/docs/*` — all docs in this directory.
- `HOLDINGS.md` — current positions (auto-read every run).
- `SETTINGS.md` — output language, tone, optional API keys, optional position-sizing rails.
- `reports/_sample_redesign.html` — **canonical visual reference**. New reports must align color, typography, layout, and component styling with this file. If missing, rebuild from the tokens in §14.
- `scripts/fetch_prices.py` — **canonical price-retrieval template** implementing §8 (market-aware primary-source routing, yfinance pacing for listed securities / FX, crypto-native Binance / CoinGecko first, auto-correction, fallback chain). Run this rather than re-implementing the pipeline ad-hoc each report. Output: `prices.json`. **Before invoking it, the latest-price subagent must complete §8.0 (install `yfinance` and `requests`) for the yfinance branches.**
- `scripts/generate_report.py` — **canonical HTML rendering template** implementing §5/§10/§13/§14. Reads `HOLDINGS.md`, `prices.json`, and an editorial context JSON; emits the self-contained HTML. Reads CSS from `reports/_sample_redesign.html` so visual edits land in one place. Stable built-in UI dictionaries live as JSON files under `scripts/i18n/` for English / Traditional Chinese / Simplified Chinese.

---

## 1. Trigger phrases & scope

Run this spec end-to-end when the user says any of:

- "portfolio health check"
- "pre-market battle report"
- "run my portfolio report"
- any explicit request for a portfolio risk / exposure / action report

Default framing: **Portfolio report**. Even when executed mid-day or after-hours, still produce the full analysis and write the local files. **Do not skip sections because the market is closed.**

---

## 2. Execution procedure (canonical order)

Run these steps in order. Each step has a "see §X" pointer to the rules.

| # | Step | See |
|---|---|---|
| 1 | Read `HOLDINGS.md`, `SETTINGS.md`, and `/docs/*`. Resolve output language and any position-sizing rails | §4, §5 |
| 2 | Auto-classify each holding by asset class, sector, and theme based on current data | §4.3 |
| 3 | Delegate latest-price retrieval to the `yfinance` subagent (batch where possible). Apply pacing rules | §8.2, §8.3 |
| 4 | If `yfinance` fails for a ticker, run up to **3 auto-correction attempts** before fallback | §8.4 |
| 5 | For tickers still unresolved, walk the source hierarchy: keyed APIs → web search / public quote pages → no-token APIs | §8.1, §8.5, §8.6 |
| 6 | Apply the **Freshness gate** to every candidate price; reject stale values until all sources are exhausted | §8.7 |
| 7 | Compute all required metrics (totals, weights, P&L, hold period, book-wide pacing, etc.) | §9 |
| 8 | Run **per-run special checks**. Surface any **High-priority alerts** at the top of the HTML | §10.6, §11 |
| 9 | Fetch material news (1–3 items per core position) and forward 30-day events | §10.5 |
| 10 | Render the HTML (11 sections in order) with inline charts, popovers, RWA, and visual standard | §10.1, §10.2, §10.3, §10.4, §13, §14 |
| 11 | Run the **Pre-delivery self-check** (Appendix A) | Appendix A |
| 12 | Reply to the user with the absolute HTML path plus key alerts and data gaps. If `yfinance` auto-correction succeeded, include a **建議更新 agent spec** note | §16 |

---

## 3. Glossary

| Term | Meaning |
|---|---|
| **Lot** | A single line in `HOLDINGS.md` representing one acquisition: ticker, quantity, cost basis, acquisition date |
| **Bucket** | One of `Long Term`, `Mid Term`, `Short Term`, `Cash Holdings` — the four risk-horizon groups in `HOLDINGS.md` |
| **Hold period** | Duration since the *oldest* lot's acquisition date (per ticker) |
| **Freshness gate** | The rule set that rejects stale prices based on current market state; see §8.7 |
| **Source hierarchy** | The 4-tier fallback order for latest prices: `yfinance` → keyed APIs → web search / quote pages → no-token APIs |
| **— (em-dash)** | Glyph for "Not applicable" (the metric never makes sense for this row) |
| **n/a** | Glyph for "Missing" (the metric should exist but the input is `?` or could not be sourced) |
| **price_source / price_as_of / price_freshness / market_state_basis** | Mandatory per-ticker provenance fields stored at generation time |
| **建議更新 agent spec** | Final-reply note proposing spec wording when a `yfinance` auto-correction or pacing tweak succeeded |

---

