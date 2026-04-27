# Portfolio Report Agent Guidelines

> The portfolio report in this repo is the **final deliverable**, not a frontend project.
> Do not break the user-facing report into multiple executable scripts or external resources.
> This spec is the single source of truth for any "portfolio health check" / "portfolio report" run.
> When invoked, follow it end-to-end, top-to-bottom.

---

## Table of contents

0. [Critical references — read first](#0-critical-references--read-first)
1. [Trigger phrases & scope](#1-trigger-phrases--scope)
2. [Execution procedure (canonical order)](#2-execution-procedure-canonical-order)
3. [Glossary](#3-glossary)
4. [Inputs](#4-inputs)
5. [Output language (HARD)](#5-output-language-hard)
6. [File output](#6-file-output)
7. [Self-containment rules](#7-self-containment-rules)
8. [Latest-price retrieval pipeline](#8-latest-price-retrieval-pipeline)
9. [Computations & missing-value glyphs](#9-computations--missing-value-glyphs)
10. [Required report sections](#10-required-report-sections)
11. [Per-run special checks](#11-per-run-special-checks)
12. [Static latest-price snapshot rules](#12-static-latest-price-snapshot-rules)
13. [Cell popovers (Symbol & Price)](#13-cell-popovers-symbol--price)
14. [Visual design standard](#14-visual-design-standard)
15. [Investment content standard](#15-investment-content-standard)
16. [Reply format to user](#16-reply-format-to-user)
17. [Appendix A — Pre-delivery self-check](#appendix-a--pre-delivery-self-check)

---

## 0. Critical references — read first

Before running the report, read these files. They are normative; this guidelines doc references them.

- `AGENTS.md` — repo-wide agent guidance.
- `README.md` — project overview.
- `/docs/*` — all docs in this directory.
- `HOLDINGS.md` — current positions (auto-read every run).
- `SETTINGS.md` — output language, tone, optional API keys, optional position-sizing rails.
- `reports/_sample_redesign.html` — **canonical visual reference**. New reports must align color, typography, layout, and component styling with this file. If missing, rebuild from the tokens in §14.

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

## 4. Inputs

### 4.1 HOLDINGS.md — lot format

Every lot follows:

```
<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD>
```

- `on YYYY-MM-DD` is the **acquisition date** for that lot. It powers per-lot tooltips and hold-period analytics.
- Crypto / FX use `<SYMBOL> <quantity> @ <cost> on <YYYY-MM-DD>` (no "shares").
- `?` is allowed in place of cost or date when truly unknown — render the affected metric as `n/a` in the report (see §9.6). **Never invent a value.**
- A ticker may have multiple lots across the four buckets (`Long Term`, `Mid Term`, `Short Term`, `Cash Holdings`). Aggregate per ticker for the holdings table; keep the lot-level array embedded in the page so the per-lot popover can render without a re-fetch.

### 4.2 SETTINGS.md

- Read for output language, tone, and (if present) position-sizing rails. Settings rails override defaults in this spec when in conflict.
- Language enforcement is in §5.
- Optional API keys are listed in §8.6.

### 4.3 Auto-classify on every run

- Auto-read all positions from `HOLDINGS.md` at run time. Do not hard-code holdings, do not assume any specific ticker is present, and re-classify on every run.
- Auto-classify each holding by asset class, sector, and theme based on current data. Buckets are not fixed — examples include `ETF`, single stock, crypto, cash, semiconductor, AI, energy, aerospace, financials, healthcare, consumer, industrial, optical / data center, defense, other. Use whatever fits the actual book.

---

## 5. Output language (HARD)

`SETTINGS.md` declares the output language. **Every** user-facing string in the HTML must be in that language — no bilingual mixing, no untranslated headers, no English fallbacks because "the term has no good translation".

### 5.1 Rules

- The `<html lang="…">` attribute must match (`zh-TW`, `en`, `ja`, etc.).
- Every section title, table header, KPI label, badge, tag, callout text, action label, tooltip / popover content, and prose paragraph must be in the SETTINGS language.
- Bilingual headers like `代號 Symbol` or `損益 P&L` are **not** acceptable. Pick one — the SETTINGS language.
- Latest-price source / freshness labels must be translated when they are natural-language labels. Provider names such as `Twelve Data`, `Finnhub`, `CoinGecko`, and `TWSE` may remain in English because they are source names. **Do not show session-state badges in any language.**
- Tag chips (`High vol`, `Long`, `Mid`, `Rich val`): translate every visible label. Default English class names stay (the CSS hooks); the visible text is translated.
- The HTML `<title>` must also be in the SETTINGS language (the filename itself stays ASCII per §6).
- If `SETTINGS.md` is missing or unparseable, default to **English** and surface the missing setting as a `n/a` in the masthead meta row.

### 5.2 Allowed non-language tokens (allow-list)

These tokens may remain as-is regardless of SETTINGS language:

- Ticker symbols (`NVDA`, `2330.TW`, `BTC`)
- Currency codes (`USD`, `TWD`)
- Unit symbols (`%`, `$`, `NT$`)
- ISO dates (`2026-04-27`)
- URL hostnames in citations
- Bracketed source names that are inherently English (`Reuters`, `StockAnalysis`)

### 5.3 Self-check before delivery

Search the rendered HTML for stray English (or non-SETTINGS-language) words. Every hit that is not in the §5.2 allow-list must be translated or removed.

---

## 6. File output

- The HTML must be written to `reports/`.
- HTML filename: `YYYY-MM-DD_HHMM_portfolio_report.html`
- Use the **local clock at execution time** for the timestamp prefix.
- **Only** the HTML is produced. No Markdown summary, no companion files. The HTML is the single deliverable.

---

## 7. Self-containment rules

### 7.1 Hard rules

- The HTML must be a single self-contained file directly openable in the browser: all CSS, charts, data, and any required interactive logic must be inlined in the same HTML.
- Do not leave external generator scripts, external CSS, CDN dependencies, build artifacts, or frontend project structure in the repo.
- If you need a temporary script to wrangle data, keep it in `/tmp` or use it once. **Do not** check it in as a deliverable.
- The final delivery should contain only the requested HTML and any necessary updates to the spec docs.
- The HTML must not depend on local relative paths, `file://` images, external fonts, external chart libraries, or any service that requires login or payment.
- External URLs are allowed *only* as data-source citations. Never as runtime style, generic script source, chart-library dependency, or market-data fetch endpoint.
- The generated HTML must not fetch market data at runtime. All latest-price retrieval happens at report generation time, and the HTML shows a static snapshot.
- If a value cannot be retrieved, render it as `n/a` and list it under **Sources & data gaps** — do not fill in by guesswork. A value you derived (e.g. P&L from your own cost basis) is fine; a guess at a market data point you could not source is `n/a`. See §9.6 for the two-glyph convention.

### 7.2 Inline JavaScript — restricted use

Inline `<script>` is allowed **only** for optional cell-popover ergonomics. Anything else must use SVG / CSS.

- **Cell popovers** — opens a hover/tap popover with per-lot detail on the Symbol and Price cells. Prefer the CSS-driven descendant popover pattern in §13.3; use a tiny inline script only if CSS cannot cover the target browser behavior.

Constraints:

- All script must be **inline** (`<script>...</script>`); no `<script src=...>`.
- No third-party libraries, no bundlers, no transpiled output. Hand-written ES2020 only.
- The HTML must remain valid and visually complete when JavaScript is disabled or the network is offline.
- No API keys, auth tokens, user-identifying headers, market-data endpoints, `fetch()`, `XMLHttpRequest`, polling timers, or runtime quote refresh logic in the generated HTML.
- API calls may be made only by the agent during report generation, using optional keys read from `SETTINGS.md`.

### 7.3 Self-containment grep

After producing the report, verify:

- No `<script src=...>`.
- No `<link rel="stylesheet"...>`.
- No `<script>` or `<link>` that pulls a chart library from a CDN.
- Inline `<style>`, inline SVG, inline tables, inline static data, and the optional popover-only inline JS are allowed.
- Prefer SVG / CSS over JavaScript. If `<script>` appears, confirm it does not contain `fetch`, `XMLHttpRequest`, API keys, or market-data endpoints.

Suggested check:

```sh
rg -n "<script\\s+src=|<link[^>]+stylesheet|href=.*\\.css" reports/*.html
```

For each hit, confirm it is purely a citation link; if it is anything else, inline it.

---

## 8. Latest-price retrieval pipeline

### 8.1 Source hierarchy

Use the highest-priority source that returns a credible value. **`yfinance` first**, then **configured keyed APIs**, then **agent web search / public quote pages**, then **free no-token APIs**. If a source is delayed, EOD-only, or stale relative to another credible source, use the fresher higher-quality value when available and record the fallback / freshness in the source audit.

1. **Latest-price subagent using `yfinance`** — before any other price-source work, delegate all holdings to a dedicated subagent that fetches latest data via `yfinance`, preferably in a single batched request. Accept only values that pass the **Freshness gate** (§8.7). Record `price_source` as `yfinance`, plus as-of timestamp, currency, exchange / market basis when available, and any ticker-level failure reason. If the subagent fails, it must diagnose the failure and attempt automatic correction up to three times before the main agent moves the affected ticker to fallback sources (§8.4).
2. **Configured keyed APIs** — if the `yfinance` subagent still fails, lacks coverage, or returns a value that fails the freshness gate after up to three correction attempts, use any relevant key / token present in `SETTINGS.md` according to the per-asset order in §8.5. Missing keys are not errors.
3. **Agent web search / public quote pages** — if no configured keyed API yields a credible current value, search the web directly and read public quote pages. Prefer official exchanges and widely used quote pages with visible price, timestamp, and prior-close / 24h reference. Record the page source and retrieval time.
4. **Free no-token APIs** — if web search / quote pages fail, use free public endpoints that require no token. These can be unofficial, delayed, rate-limited, or CORS-sensitive, so they are the last fallback. Record them explicitly as no-token fallback sources.

> **Conflict resolution:** When `yfinance` and another credible latest-price value conflict, prefer the source with the freshest timestamp and clearest market coverage; document the rejected source and reason in **Sources & data gaps**.

### 8.2 yfinance — primary source

- For latest price, first delegate to a dedicated latest-price subagent that uses `yfinance` to fetch all holdings in one batch where possible. The subagent must return: price, prior close / 24h reference, move %, timestamp / as-of, currency, exchange, and any failure reason **per ticker**.
- If `yfinance` fails or returns invalid data, follow §8.4 (3-attempt auto-correction) before moving to fallback.
- Always retrieve the latest market data at generation time. Never rely on stale model memory.
- Each holding must be refreshed for: latest price snapshot, day / 24h and recent move, market cap, valuation multiples (PE, Forward PE, PS, EV/EBITDA where relevant), volume, next earnings date, and any imminent material event.
- For company and event data, source priority remains: company IR, SEC / exchange filings, official press releases, then StockAnalysis, Nasdaq, Yahoo Finance, Reuters, CNBC, MarketWatch.

### 8.3 yfinance rate limiting & request pacing (HARD REQUIREMENT)

`yfinance` proxies Yahoo Finance's unofficial endpoints, which throttle aggressively and return `YFRateLimitError` / HTTP 429 / empty payloads when hit too fast. The latest-price subagent **must** pace requests to avoid the rate limiter — a tripped limiter typically blocks the IP for 15–60 minutes and forces the entire run onto fallback sources.

| Rule | Detail |
|---|---|
| Batch first | Use `yf.download(tickers="AAPL MSFT NVDA …", period="5d", interval="1d", group_by="ticker", threads=False, progress=False)` or iterate `yf.Tickers("AAPL MSFT …").tickers[t].fast_info` so a single HTTP round-trip covers the whole book |
| No internal threading | Set `threads=False` on `download`. Concurrent requests are the fastest way to trip the limiter |
| Min inter-call gap | **1.5–2.0s** between successive yfinance HTTP calls. For per-ticker iteration use `time.sleep(random.uniform(1.5, 2.5))`. **Never go below 1.0s** |
| Backoff on 429 / `YFRateLimitError` / empty `history()` | Exponential: 30s → 60s → 120s → 300s, **max 3 retries**. After the third failure, mark the ticker `yfinance_rate_limited` and move to fallback — do not keep hammering |
| Per-run volume cap | If holdings > ~30 tickers, split into batches of **≤ 25 tickers** with a **3s** gap between batches |
| Reuse session | Reuse a single `requests.Session` across calls (`yf.Ticker(t, session=session)`) so cookies / crumbs are not re-negotiated each request |
| HTTP timeout | 10–15s per request. A hung connection still consumes a rate-limit slot |
| Audit fields | Record per-ticker `yfinance_request_started_at`, `yfinance_request_latency_ms`, `yfinance_retry_count` in the source audit when retries fired |

The pacing/backoff retries are part of the §8.4 three-attempt budget — a 429 retry counts as one correction attempt, not a free retry. If a run still trips the limiter, surface the incident in **Sources & data gaps** with offending request count and inter-request gap, and include a **建議更新 agent spec** note proposing a tighter pacing constant.

### 8.4 yfinance failure recovery (3-attempt budget)

If the `yfinance` subagent returns an exception, empty data, stale data, invalid currency / exchange metadata, a symbol-not-found result, a rate-limit / timeout, or a value that fails the **Freshness gate** (§8.7), do not immediately fall back. First read the failure reason and attempt automatic correction.

- **Maximum attempts:** three correction attempts per failed ticker or batch failure class. Attempt count starts after the first failed `yfinance` call. Do not loop indefinitely.
- **Targeted corrections.** Match the attempt to the observed failure reason. Examples:
  - Normalize Yahoo symbols (`BRK.B` → `BRK-B`, crypto → `BTC-USD`, Taiwan / Japan suffixes).
  - Retry as per-ticker calls after a failed batch.
  - Switch between quote metadata and short interval history.
  - Request a shorter / longer period.
  - Repair timezone / calendar interpretation.
  - Back off briefly after timeout / rate-limit (uses §8.3 backoff schedule).
- **Re-gate after each attempt.** If the corrected value passes the Freshness gate, use it and record `price_source = yfinance`, `yfinance_auto_fix_applied = true`, attempt count, and the successful fix summary.
- **All 3 attempts fail.** Move that ticker to keyed APIs, then web search / quote pages, then no-token APIs. Record the original failure reason and all attempted fixes in **Sources & data gaps**.
- **Spec-update note.** If a new correction pattern succeeds during a run, do **not** silently treat it as permanent spec knowledge. In the final user reply, include a short **建議更新 agent spec** note with the failure pattern, the fix that worked, and concise wording that could be added to this spec.

### 8.5 Per-asset fallback order

| Asset / market | Latest-price fallback order |
|---|---|
| US equities / ETFs | **First:** `yfinance` subagent batch quote / history. **Keyed APIs:** Twelve Data → Finnhub → FMP → Tiingo → Alpha Vantage → Polygon. **Web search / pages:** Yahoo Finance → Google Finance → Nasdaq → MarketWatch / CNBC / TradingView / StockAnalysis → other credible quote pages. **No-token APIs:** Yahoo public quote/chart endpoints → Stooq CSV / other credible no-token endpoints |
| Crypto | **First:** `yfinance` subagent using Yahoo-style symbols where available (`BTC-USD`, `ETH-USD`, etc.). **Keyed APIs:** CoinGecko Demo → Alpha Vantage / FMP if configured. **Web search / pages:** CoinGecko → CoinMarketCap → Binance → Coinbase → TradingView. **No-token APIs:** Binance public spot ticker → Coinbase Exchange ticker → CoinGecko public simple price |
| Taiwan listed / OTC equities | **First:** `yfinance` subagent using exchange suffixes where available (`2330.TW`, OTC forms where supported). **Keyed APIs:** Twelve Data / Finnhub / FMP when coverage exists. **Web search / pages:** TWSE / TPEx quote pages → Yahoo Finance Taiwan → TradingView → other credible quote pages. **No-token APIs:** TWSE MIS public quote → TWSE OpenAPI daily / after-market data → TPEx official no-token data |
| Japan equities | **First:** `yfinance` subagent using exchange suffixes where available. **Keyed APIs:** Twelve Data → Finnhub → J-Quants when token is present. **Web search / pages:** Yahoo Finance Japan / Yahoo Finance global → JPX / issuer pages where price is visible → Google Finance → TradingView. **No-token APIs:** Stooq CSV / other credible no-token endpoints |
| FX / cash conversion | **First:** `yfinance` subagent using Yahoo FX symbols where available. **Keyed APIs:** Twelve Data FX → Alpha Vantage currency exchange rate. **Web search / pages:** Google Finance → Yahoo Finance → official central-bank / ECB / Fed reference pages. **No-token APIs:** official daily reference-rate feeds where available → other credible no-token FX endpoints |

### 8.6 Optional fallback API keys

All market-data keys in `SETTINGS.md` are **optional fallback sources**. Never block a report because a key is missing. If a key is present, use that keyed API for tickers where `yfinance` is missing, stale, unsupported, or invalid before web search; if the key is missing, quota-limited, or unusable for the ticker, skip that provider and continue to the next fallback. **Do not put API keys, tokens, request URLs containing keys, or authenticated response payloads in the generated HTML.**

| Setting key | Primary use | Notes |
|---|---|---|
| `TWELVE_DATA_API_KEY` | US equities / ETFs, global equities where covered, FX | Free tier is suitable for snapshots but rate-limited. Prefer `/price` or quote endpoints when available |
| `FINNHUB_API_KEY` | US equities / ETFs, some global equities | Free key required. Use quote endpoint for current / previous close fields |
| `COINGECKO_DEMO_API_KEY` | Crypto latest price and 24h move | Demo key is optional; public shared access may work but is less reliable |
| `ALPHA_VANTAGE_API_KEY` | US equities fallback, FX, crypto fallback | Free tier is low-quota; use after higher-priority sources |
| `FMP_API_KEY` | US equities fallback, valuation / fundamentals where free tier allows | Free plan can be delayed / EOD; mark freshness accordingly |
| `TIINGO_API_KEY` | US equities fallback | Free token is optional and rate-limited |
| `POLYGON_API_KEY` | US equities fallback | Free plan may be delayed / EOD; mark freshness accordingly |
| `JQUANTS_REFRESH_TOKEN` | Japan official delayed market data | Optional for Japanese equities; useful as official delayed data, not necessarily the latest trade. If an implementation uses email / password to obtain the token, those fields are also optional and must never be written into outputs |

### 8.7 Freshness gate

Before accepting any latest price, determine the ticker's market calendar, exchange timezone, current local market date, and whether the regular session has already opened. Apply this gate before the source is considered valid:

| Market state at generation time | Acceptable price | Rejection rule |
|---|---|---|
| Regular session is open today | Same trading date, current / intraday latest price from a credible source. Timestamp or page context must indicate it is not just the prior close | Reject prior-session close, EOD-only, or clearly delayed values and continue to the next source |
| Regular session already closed today | Same trading date latest / official close / closing auction value. If only intraday timestamp is available, it must be from today's session | Reject previous trading day's close unless every source has been exhausted |
| Today's regular session has not opened yet | Previous opened trading day's official / credible close at minimum | Reject prices older than the previous opened trading day |
| Weekend / holiday / exchange closed all day | Most recent opened trading day's official / credible close | Reject older closes unless every source has been exhausted; if even that cannot be verified, render `n/a` |
| 24/7 assets such as major crypto | Fresh spot price from a credible source, with retrieval time or source timestamp | Reject stale snapshots when another source can provide a fresher spot price |

**Strict rule for opened markets:** Once a market's regular session has opened for the current exchange trading date, do **not** accept a prior-session close or stale delayed value until the `yfinance` subagent result, up to three yfinance auto-correction attempts, and every configured API, web-search/page source, and no-token fallback has been exhausted. If the market has not opened yet, the minimum acceptable price is the previous opened trading day's official / credible close.

**Degraded fallback:** If the market has opened and all sources are exhausted without a same-date latest price, use the freshest credible value only as an explicit degraded fallback. Mark `price_freshness` as `stale_after_exhaustive_search`, list every attempted source category in **Sources & data gaps**, and make the stale-price condition visible in the report's data-gap / alert text. **Do not silently treat that fallback as current.** If even the previous opened trading day's close cannot be sourced, render the cell as `n/a`.

If a credible source cannot be found, render the field as `n/a` (per §9.6). If a number is your own derivation, label it `estimate`. **Never silently guess.**

### 8.8 Stored fields per ticker

Persist these fields for every ticker at generation time. The HTML embeds only the static fields below; it never embeds provider credentials, provider request URLs with keys, or retry / polling code.

- `latest_price`
- `prior_close` or 24h reference (when available)
- `move_pct`
- `price_source`
- `price_as_of`
- `price_freshness`
- `market_state_basis`
- `currency` (when available)
- `exchange` (when available)
- If `yfinance` auto-correction was attempted: failure reason, attempts, applied fix when successful, final outcome
- If pacing retries fired: `yfinance_request_started_at`, `yfinance_request_latency_ms`, `yfinance_retry_count`

---

## 9. Computations & missing-value glyphs

### 9.1 Required metrics

- Total assets, invested position, cash & cash-equivalent value, cash ratio.
- Per-holding weight (% of total assets), theme weight, sector weight.
- Per-holding P&L using the cost basis in `HOLDINGS.md`. For lots with `?` cost, render P&L as `n/a`.
- Per-lot P&L (used by the Price popover) — `(latest_price − lot_cost) × lot_qty`. Skip lots with `?` cost.
- Per-ticker weighted-average cost (used by the Price popover) — `Σ(lot_cost × lot_qty) ÷ Σ(lot_qty)` over lots with known cost.
- For each holding, the freshness fields listed in §8.8.

### 9.2 Hold period (per ticker)

- Definition: duration since the *oldest* lot's acquisition date.
- Display formats: `Xy Ym` for ≥ 1 year, otherwise `Nm` or `Nd`.
- If any lot has a `?` date, render as `n/a`.

### 9.3 Latest price & today's move (per ticker)

- **Latest price (per ticker)** = the newest credible source value at generation time that passes the **Freshness gate** (§8.7).
  - Follow the source hierarchy (§8.1).
  - Reject any source that fails the market-state freshness requirement.
  - Record `price_source`, `price_as_of`, `price_freshness`, and `market_state_basis` (§8.8).
  - Do **not** display session-state badges.
  - If even the required current-session latest price or previous-opened-trading-day's close cannot be sourced after exhaustion, render the cell as `n/a`.
- **Today's move % / 24h move %** is derived from the selected latest price and the best available prior close / 24h reference. Render as a small subline under the price when available; otherwise render `n/a` only for the move subline, **not** for the price.

### 9.4 IRR is intentionally NOT computed

A previous version of this spec annualized P&L; that produced misleading 4-digit % numbers for short-window high-volatility names. Hold period plus per-lot P&L (visible in the Price popover) carries the same context without the bad math. **Do not reintroduce IRR.**

### 9.5 Book-wide pacing aggregates

Compute and surface in the **Holding period & pacing** section (§10.3):

- Cost-weighted average hold period across all risk assets (ex-cash).
- Oldest lot in the book (ticker + date + duration).
- Newest lot in the book (ticker + date + duration).
- % of risk-asset value held > 1 year.
- Distribution of risk-asset value across the buckets `< 1m`, `1–6m`, `6–12m`, `1–3y`, `3y+`.

### 9.6 Missing-value glyphs

Two glyphs cover every "no value" case in the report. Pick one per cell — never leave a cell empty, never write "data gap" / "missing" / "unknown" inside a cell.

| Glyph | Meaning | Use for |
|---|---|---|
| `—` (em-dash, `.na` style, muted-gray) | **Not applicable** — the metric never makes sense for this row | Cash and pure cash-equivalent rows in the P&L column; any row+column where the metric is structurally undefined |
| `n/a` (lowercase, muted-gray) | **Missing** — the metric *should* exist but the input is `?` in `HOLDINGS.md` or could not be sourced | Cost-basis-derived metrics when cost is `?`; date-derived metrics when date is `?`; market data fields when no credible public source returned a value |

**Cell-level, not row-level.** `n/a` applies per cell. If cost is missing but the price feed is fine, only `P&L` renders `n/a`; the latest price still shows.

The semantic split lets the user scan the table once: every `—` is expected, every `n/a` is something to fix in `HOLDINGS.md` or trace back to a missing data source. The **Sources & data gaps** section at the bottom of the report enumerates each `n/a` with the reason and the `HOLDINGS.md` line or URL needed to close it.

---

## 10. Required report sections

### 10.1 HTML — section order (must contain, in this order)

1. Today's summary
2. Portfolio dashboard (KPIs)
3. Holdings P&L and weights (table) — see §10.2
4. Holding period & pacing — see §10.3
5. Theme / sector exposure
6. Latest material news
7. Forward 30-day event calendar
8. High-risk and high-opportunity list
9. Recommended adjustments
10. Today's action list (translated buckets per §15.3)
11. Sources and data gaps

The HTML is the only deliverable — there is no Markdown summary or companion file (§6).

### 10.2 Holdings table — required columns

Section 3 of the HTML uses these columns, left to right. **Default to scan-light, hover-to-reveal**: visible cells stay short; full detail lives in popovers attached to the Symbol and Price columns (§13).

| # | Column | Rule |
|---|---|---|
| 1 | **Symbol** | Ticker only, weight 680, monospace-friendly. **No** company subline, **no** since-line, **no** lot count visible by default. All of that lives in the Symbol popover (§13.4) |
| 2 | **Category** | Asset class plus a single tag chip (`High vol`, `Long`, `Mid`, `Short`, `Rich val`, `Overheated`, `High risk`, `Cash`, etc.). Translate to SETTINGS language |
| 3 | **Price** | Latest static snapshot price, large; small day / 24h move % subline below when available. The whole cell is the popover trigger (§13.5). No runtime refresh target and no session-state badge |
| 4 | **Weight** (num) | % of total assets |
| 5 | **Value** (num) | Current market value (USD basis) |
| 6 | **P&L** (num) | `±$X / ±Y%`. Cash → `—`. Cost missing → `n/a`. (Detail per lot lives in the Price popover; this column is the at-a-glance aggregate) |
| 7 | **Action** | Recommendation with action verb, price band, and trigger |

The `Held` and `Move` columns from earlier specs are **removed**. Hold period stays available in the Symbol popover and aggregated in **Holding period & pacing**.

### 10.3 Holding period & pacing block (must contain)

- A **4-cell KPI strip**: **Avg hold (cost-weighted)**, **Oldest lot** (ticker + since-date + duration), **Newest lot** (ticker + since-date + duration), **% of risk assets held > 1 year**.
- A horizontal stacked **`period-strip`** with five segments — `< 1m`, `1–6m`, `6–12m`, `1–3y`, `3y+` — and a matching legend showing the % in each bucket.
- Zero or more **`bucket-note`** callouts surfacing pacing issues:
  - Bucket misclassification (e.g. Short Term lot held > 12 months).
  - Recent buying spree (3+ adds in 30 days).
  - Averaging-up risk (latest add > 1.1× older avg cost).
  - Open cost-basis gaps.

### 10.4 Required charts (inline SVG / CSS only)

| # | Chart |
|---|---|
| 1 | Asset allocation donut |
| 2 | Holdings weight bar chart |
| 3 | P&L ranking bar chart |
| 4 | Sector / theme exposure bar chart |
| 5 | Hold-duration stacked strip (the bar inside §10.3) |
| 6 | Forward 30-day event timeline |
| 7 | High-risk position heatmap |
| 8 | Cash vs. risk-asset ratio bar |

Every chart must have a clear title, readable labels, and tabular numerals. **No external chart libraries**; build with SVG `path` / `circle` / `rect` / `text` and CSS bars. See §14.5 for color and weight rules.

### 10.5 News & event coverage

- For each core position, surface **1–3 recent material news items**.
- If the book is large, prioritize: highest weight, highest recent volatility, recent material events, largest losers.
- Each news item must include: **date, source name, link, and impact tag** — `positive` / `neutral` / `negative` (translate per SETTINGS).
- **Forward events to track:** earnings, earnings calls, shareholder meetings, ex-dividend dates, product launches, regulatory decisions, industry policy, M&A, raises, debt maturities, lockup expiries, plus macro releases relevant to the book (FOMC, CPI, PCE, NFP, etc.).

### 10.6 High-priority alerts (top of report)

Surface a **High-priority alerts** block at the very top of the HTML whenever any of the following triggers fire:

- Single asset weight > 20%.
- Any correlated theme bucket > 30%.
- Any high-volatility bucket > 30%.
- Any short-term position with single-day move > 8%.
- Any position with earnings within 7 days *and* weight > 5%.
- Any position breaking below 50-day MA *and* news flow turning negative.
- Any position trading > 20% above analyst consensus target.
- Any position with material negative news, guidance cut, regulatory risk, liquidity risk, dilution risk, or debt risk.

---

## 11. Per-run special checks

Every run must explicitly evaluate and answer all of these. **If a check passes cleanly, say so explicitly in the report — do not silently omit.**

1. Any single asset > 15%?
2. Any correlated theme > 25%?
3. **High-volatility bucket > 30%?** High-vol includes crypto, small-cap growth, unprofitable companies, and names with abnormally high recent daily / weekly volatility.
4. Are short-term positions overheated, trading rich vs. fair, or facing imminent earnings / events?
5. For losing positions: is this just a price pullback, or have fundamentals / news / earnings expectations actually deteriorated?
6. Is cash sufficient to cover a 1–3 month potential drawdown and add-on opportunities?
7. **Bucket misclassification.** Any lot in the **Short Term** bucket held > 12 months? Either reclassify or exit.
8. **Recent buying spree.** Any ticker with 3+ new lots added in the last 30 days? Confirm the thesis still holds — concentration may be building.
9. **Averaging up.** Any ticker where the most recent lot's cost is > 1.1× the older weighted-average cost? Flag the chase risk explicitly.
10. **Open cost-basis or date gaps.** List every lot still using `?` for cost or date — these block per-lot tooltips and pacing analysis.

---

## 12. Static latest-price snapshot rules

The Price column is a **static snapshot** produced by the agent at report generation time. It must not refresh itself after the HTML opens.

### 12.1 Generation-time retrieval

- First delegate latest-price retrieval to the `yfinance` subagent for all tickers (§8.2, §8.3).
- If the `yfinance` subagent returns missing, stale, unsupported, or invalid data, run §8.4 (3-attempt auto-correction) before moving that ticker to fallback sources.
- Use configured keyed APIs only for tickers where `yfinance` remains missing, stale, unsupported, or invalid after the allowed correction attempts.
- Use agent web search and public quote pages **before** no-token API endpoints.
- Use free no-token APIs only after `yfinance`, keyed APIs, and web search / quote pages fail or return stale / conflicting data.
- Apply the **Freshness gate** to every candidate (§8.7). If the market has opened today, keep searching until a same-date latest / close value is found or the entire hierarchy is exhausted. If the market has not opened today, keep searching until at least the previous opened trading day's close is found.
- Prefer the freshest credible value with a clear timestamp. If only delayed / EOD data is available after the market has opened, use it only after every source has been exhausted and label the freshness as degraded in the source audit.
- Store, per ticker, the §8.8 fields. The generated HTML embeds only those static fields.

### 12.2 Display rules

- **Price cell:** large latest price plus a small signed move subline such as `較前收 +1.40%` or `24h +2.10%`, translated per SETTINGS.
- **Price popover** (§13.5): include latest price, selected source, timestamp / freshness, market-state basis, currency / exchange when available, and per-lot P&L table.
- **Do not** show session-state chips, refresh-status UI, update animations, or stale / offline badges.

### 12.3 Source audit content

- List the provider used for every holding and call out delayed / EOD / fallback sources.
- For stale degraded fallbacks or `n/a`, list each attempted source category and why no freshness-valid value was used.
- For `yfinance` failures, include the failure reason and up to three automatic correction attempts before fallback.

---

## 13. Cell popovers (Symbol & Price)

### 13.1 Behavior summary

Both the Symbol and Price cells expose a popover that:

- **Opens on hover** (desktop).
- **Slides up as a bottom sheet on tap** (touch / tablet).
- Fades in / out — no click required, no toggle state.

The previous `<button popovertarget>` + native HTML `popover` pattern is **deprecated** because:
- It required a click to open, conflicting with hover-to-preview UX.
- Native top-layer rendering disabled fade-in animations and made the popover feel modal.

The new pattern is a **CSS-driven `:hover` / `:focus-within` popover, structured as a *descendant* of the trigger** so hover propagates naturally and there is no JavaScript dependency for show/hide.

### 13.2 HTML structure

```html
<td>
  <div class="sym-trigger" tabindex="0" role="button">
    NVDA
    <div class="pop pop-sym" role="tooltip">
      …translated: company name, asset class, since-line, lot count, rationale…
    </div>
  </div>
</td>

<td class="num price-cell">
  <div class="price-trigger" tabindex="0" role="button">
    <span class="price-num">$211.62</span>
    <span class="price-sub pos">較前收 +1.40%</span>
    <div class="pop pop-px" role="tooltip">
      <h4>NVDA · 每批損益</h4>
      <div class="pop-sub">最新價 $211.62 · 來源：Twelve Data · 2026-04-27 09:00</div>
      <table>… per-lot rows + summary tfoot …</table>
    </div>
  </div>
</td>
```

**Trigger element rules:**
- The trigger is a `<div tabindex="0" role="button">` (not `<button>`) because the popover may contain a `<table>`, which is invalid inside a `<button>`.
- `role="button"` keeps screen-reader semantics; `tabindex="0"` keeps keyboard focusability.

### 13.3 CSS pattern (desktop)

Use the same surface palette as the rest of the page. **Do not** use a dark background with light text — that breaks the editorial look and makes the popover feel like a different application surface.

```css
:root{
  --table-header-z:70;
  --popover-host-z:40;
  --popover-z:50;
}

thead th{
  position:sticky;
  top:0;
  z-index:var(--table-header-z);
  background:var(--paper);
  box-shadow:0 1px 0 var(--hairline-2);
}

.pop{
  position:absolute;
  top:calc(100% + 8px);              /* anchored just below the trigger, near the cursor */
  left:0;
  z-index:var(--popover-z);

  background:var(--surface);          /* light paper surface */
  color:var(--ink);                   /* primary ink */
  border:1px solid var(--hairline-2);
  border-radius:4px;
  padding:12px 14px;

  /* The single allowed elevated shadow on the page */
  box-shadow:0 6px 20px rgba(15,25,31,.10), 0 1px 2px rgba(0,0,0,.04);

  width:max-content;
  min-width:min(300px, calc(100vw - 64px));
  max-width:min(560px, calc(100vw - 64px));
  font-size:clamp(12px, 0.25vw + 11.4px, 13px);
  line-height:1.55;
  text-align:left;
  overflow-wrap:normal;

  /* Hidden by default; fade in via opacity + small lift */
  opacity:0;
  visibility:hidden;
  transform:translateY(-4px);
  transition:opacity .18s ease, transform .18s ease, visibility 0s linear .18s;
  pointer-events:none;
}

/* Cells in the right portion of the table anchor right so popovers don't overflow */
.tbl-wrap td:nth-last-child(-n+3) .pop{left:auto;right:0}

/* Raise the active table cell so descendant popovers are not trapped below sticky cells. */
tbody td:has(.sym-trigger:is(:hover,:focus-within)),
tbody td:has(.price-trigger:is(:hover,:focus-within)){
  position:relative;
  z-index:var(--popover-host-z);
}

/* Show on hover or focus — descendant popover keeps :hover state while pointed at */
.sym-trigger:hover > .pop,
.sym-trigger:focus-within > .pop,
.price-trigger:hover > .pop,
.price-trigger:focus-within > .pop{
  opacity:1;visibility:visible;transform:translateY(0);
  transition:opacity .18s ease, transform .18s ease, visibility 0s;
  pointer-events:auto;
}

.pop table{
  width:100%;
  min-width:0;
  table-layout:auto;
}
.pop table th,.pop table td{
  white-space:nowrap;
  overflow-wrap:normal;
}
.pop thead th{
  position:static;
  z-index:auto;
  background:transparent;
  box-shadow:none;
}
```

Internal styling uses the same tokens as the page body — `--ink` text on `--surface`, `--muted` for sublines, `--hairline` for dividers, `--pos` / `--neg` for signed numbers. **No custom dark-mode palette inside the popover.** On desktop, popovers must expand to fit their content up to the viewport-aware max width; do not force table cells or short labels to wrap early. Long flex value cells such as `.pop-row .v` should use `min-width:0; text-align:right; overflow-wrap:break-word;` so only genuinely long prose wraps.

### 13.4 Symbol popover content

- Company / instrument full name (translated when natural).
- Asset class and theme tags.
- `since YYYY-MM · <duration> · N lot(s)` line.
- Optional one-line rationale (why the position is in Long / Mid / Short bucket, if non-obvious).

### 13.5 Price popover content

- A heading with the ticker + "每批損益" (translated per SETTINGS).
- A subline with the latest price, selected source, and timestamp / freshness.
- A small table: one row per lot with columns `取得日 / 成本 / 數量 / 損益` (translated). Numeric columns right-aligned with tabular numerals.
- A `<tfoot class="summary">` row showing **平均成本 / 總成本 / 總損益**. Top-bordered, semibold.
- If cost is `?` for a lot, render that row's P&L as `n/a` and exclude it from the average-cost calculation.

### 13.6 Responsive (RWA) — popover on tablet, phone, and touch

A subtle but critical detail: `.tbl-wrap` activates `overflow-x:auto` on tablet (≤ 880px) and phone (≤ 600px) to allow horizontal scrolling of the wide table. Browsers coerce `overflow-y` to `auto` whenever `overflow-x` is non-visible, which would clip any popover that extends below its cell. The fix:

- **Desktop ≥ 881px** — `.tbl-wrap` has *no* overflow constraint (the table fits within the page container at its `min-width:760px`). Popover is `position:absolute`, anchored to the trigger, fades in below the cell.
- **Tablet 601–880px** and **Phone ≤ 600px** — `.tbl-wrap` enables `overflow-x:auto`. To escape the resulting overflow context, the popover switches to a fixed bottom sheet using safe-area insets: `position:fixed; left:max(12px, env(safe-area-inset-left)); right:max(12px, env(safe-area-inset-right)); bottom:max(12px, env(safe-area-inset-bottom));`. It must also set `max-height:min(72vh, calc(100dvh - 32px)); overflow:auto; overscroll-behavior:contain;` so long text or lot tables scroll inside the sheet instead of exceeding the viewport.
- **Touch (`@media (hover:none)`)** — hover does not fire reliably; suppress the hover trigger and only respond to `:focus-within` (i.e. tap). Tap outside the trigger blurs the focus and dismisses the sheet automatically.
- **Layering** — because this pattern intentionally does not use native HTML top-layer popovers, the CSS must explicitly separate layers: sticky table headers use `z-index:var(--table-header-z)` and an opaque `var(--paper)` background so scrolling rows never cover the header; `.pop` uses `z-index:var(--popover-z)` and the active table cell uses `z-index:var(--popover-host-z)` via `:has(...)`.

```css
@media (max-width:880px), (hover:none){
  .pop{
    position:fixed;
    left:max(12px, env(safe-area-inset-left));
    right:max(12px, env(safe-area-inset-right));
    bottom:max(12px, env(safe-area-inset-bottom));
    top:auto;
    width:auto;max-width:none;
    max-height:calc(100vh - 32px);
    max-height:min(72vh, calc(100dvh - 32px));
    overflow:auto;
    overscroll-behavior:contain;
    -webkit-overflow-scrolling:touch;
    transform:translateY(20px);
    box-shadow:0 10px 30px rgba(15,25,31,.18), 0 2px 6px rgba(0,0,0,.08);
  }
  .pop table{table-layout:fixed}
  .pop table th,.pop table td{white-space:normal;overflow-wrap:anywhere}
  .sym-trigger:hover > .pop,
  .sym-trigger:focus-within > .pop,
  .price-trigger:hover > .pop,
  .price-trigger:focus-within > .pop{
    opacity:1;visibility:visible;transform:translateY(0);pointer-events:auto;
  }
}
@media (hover:none){
  /* Tap-only: suppress hover, require focus */
  .sym-trigger:hover > .pop,
  .price-trigger:hover > .pop{opacity:0;visibility:hidden;transform:translateY(20px);pointer-events:none}
}
```

### 13.7 Reduced motion

Honor `@media (prefers-reduced-motion: reduce)` — drop the fade and slide to an instant show / hide:

```css
@media (prefers-reduced-motion: reduce){
  .pop{transition:opacity .01s linear, visibility 0s !important;transform:none !important}
}
```

### 13.8 Anti-patterns (must avoid)

- **Reverse-color popovers** (dark background + light text). The popover is part of the page palette, not a separate surface.
- **Click-to-open popovers** on desktop. The user explicitly wants hover preview; clicking is reserved for nothing in this column.
- **Popovers anchored to the cell or the row** rather than to the trigger element — that pushes them away from the cursor and weakens the "next to mouse" feel.
- **`<button>` as the trigger when content includes block elements** (e.g. tables) — invalid HTML; use `<div tabindex="0" role="button">`.
- **`overflow:hidden` on `.tbl-wrap`** — silently clips popovers. Use `overflow-x:auto` only when needed (tablet + phone) and rely on the `position:fixed` bottom-sheet escape hatch.
- **Mobile bottom sheets without viewport bounds** — any mobile / touch popover must have safe-area-aware left/right/bottom, a `100dvh`-based max height, internal scrolling, long-text wrapping, and active-cell z-index promotion.

---

## 14. Visual design standard

### 14.1 Direction

Overall direction is **editorial × research-desk note**: warm-paper background, ink-black text, hairline rules, generous whitespace, hierarchy via typography rather than color blocks / shadows / heavy borders.

**Not** a generic blue SaaS dashboard, **not** a dark-gradient hero card, **not** stacked saturated color blocks.

Priorities: scan efficiency, number clarity, risk visibility.

### 14.2 Design tokens (declare via `:root` variables)

```css
:root{
  /* Surface */
  --paper:        #f7f5ef;     /* warm paper body background — never pure white or cool gray */
  --surface:      #ffffff;
  --surface-2:    #fbfaf6;
  --hairline:     #e7e3d8;     /* primary divider */
  --hairline-2:   #d8d3c6;     /* heavier divider (table top/bottom rule, region frame) */

  /* Ink */
  --ink:          #15191f;     /* primary text — never pure #000 */
  --ink-soft:     #2c333d;
  --muted:        #6b7280;
  --muted-2:      #8a8f99;

  /* Semantic */
  --pos:          #15703d;     /* positive return, positive news */
  --neg:          #b42318;     /* negative return, alerts */
  --warn:         #b15309;     /* rich valuation, overheated */
  --info:         #1d4690;
  --accent:       #1f2937;
  --accent-warm:  #8a5a1c;     /* editorial warm accent */
}
```

### 14.3 Typography

**Must use system stacks — do not load any external font / Google Fonts.**

```css
/* Body / Text */
font-family:
  "SF Pro Text", -apple-system, BlinkMacSystemFont,
  "Segoe UI Variable Text", "Segoe UI",
  "PingFang TC", "Microsoft JhengHei UI", "Microsoft JhengHei",
  "Noto Sans CJK TC", system-ui, sans-serif;

/* Display / Headings */
font-family:
  "SF Pro Display", -apple-system, BlinkMacSystemFont,
  "Segoe UI Variable Display", "Segoe UI",
  "PingFang TC", "Microsoft JhengHei UI", system-ui, sans-serif;
```

**Required typography settings:**

- `body` must enable `-webkit-font-smoothing:antialiased` and `text-rendering:optimizeLegibility`.
- Globally enable `font-feature-settings: "ss01", "cv11", "tnum" 1, "lnum" 1`.
- Numeric classes (`.num`, `.kpi .v`, `.bar-value`, numeric table cells) must additionally force `font-variant-numeric: tabular-nums lining-nums`.
- Heading weights live in **620–680**, **never above 720**. Body 400–500. KPI numbers 620. Labels / eyebrows 700.
- Large headings get `letter-spacing:-.012em` (tight). Small-caps eyebrows / table headers get `letter-spacing:.12em–.22em` and `text-transform:uppercase`.
- Line-height: body **1.62**, heading **1.18**, KPI numbers **1.1**.

### 14.4 Fluid font-size scale (HARD floors)

The page must remain readable on a 360px-wide phone *and* a 27" monitor. Use `clamp()` for elements that scale, hard-coded sizes for elements that should not. **Never** ship a viewport-only rule that pushes any user-facing text below the floor.

| Element | `clamp(min, fluid, max)` | Floor |
|---|---|---|
| `body` (base) | `clamp(14px, 0.85vw + 11.6px, 15.5px)` | 14px on phone |
| Masthead `h1` | `clamp(22px, 3vw + 10px, 36px)` | 22px |
| Section `h2` | `clamp(15px, 0.6vw + 13px, 19px)` | 15px |
| KPI value `.kpi .v` | `clamp(22px, 1.5vw + 16px, 30px)` | 22px |
| Table cell (default) | `clamp(12.5px, 0.3vw + 11.6px, 13.5px)` | 12.5px |
| Table cell (Price headline) | `clamp(15px, 0.6vw + 13px, 17px)` | 15px |
| Subline / `.sub` / `.subnum` | `clamp(11px, 0.2vw + 10.4px, 12px)` | 11px |
| Small-caps eyebrow / `.k` / table `<th>` | `clamp(10px, 0.15vw + 9.5px, 11.5px)` | 10px |
| Tooltip / popover body | `clamp(12px, 0.25vw + 11.4px, 13px)` | 12px |
| Footer / fine print | `clamp(11px, 0.15vw + 10.6px, 12px)` | 11px |

These floors override any media query. The phone breakpoint may *fix* a value at the floor (e.g. body 14px) but must never go lower.

### 14.5 Layout & component rules

- **Page container:** `max-width:1180px`, side padding 40px, top 56px, bottom 80px. Do not go to 1480px+ wide layouts.
- **Masthead** (replaces hero card): newspaper-style — 3px black top rule, 1px hairline bottom rule. Contains: eyebrow (small-caps category), headline, dek subhead (≤ 780px wide), and a meta row (generated time, FX rate, data source, next event). **Do not** use dark gradient blocks, glow circles, or box-shadow.
- **Warning callout:** `--surface-2` background + 3px `--neg` left rule + a small `badge` chip. Bullet list may use 2-column `columns`, each item ≤ 1.5 lines. **Do not** use a saturated red wash.
- **KPI strip:** horizontal 4-column strip. 1px hairline top and bottom; 1px hairline between columns. Do not use individual cards with box-shadow and colored top bars. Each cell contains: small-caps label, big number, small delta line.
- **Section heading (`section-head`):** `h2` on the left, small `sub` on the right (`--muted`), 1px hairline below. **Do not** add gradient bars or color rails before `h2`.
- **Charts:**
  - Donut: SVG `circle` with `stroke-dasharray`. Center shows total. Radius 42, stroke-width 20. Slice colors come from `--accent`, `--pos`, `--accent-warm`, `--info`, `--warn`. **No** neon-blue / cyan gradients.
  - Bar chart: track 6px tall, `#ebe7da` background, `border-radius:2px`. Bar uses solid color (default `--ink`; for signed values use `--pos` / `--neg` / `--warn` / `--info`). **No** 18px-thick bars with linear-gradient fills.
- **Table:** 1px `--ink` top and bottom rule. Row dividers 1px `--hairline`. Header is sticky (`position:sticky; top:0`) with opaque `var(--paper)` background, `z-index:var(--table-header-z)`, small-caps `--muted`, and a 1px bottom shadow/rule so scrolling body rows cannot cover it. Hover row uses `--surface-2`. Numeric cells `text-align:right` + tabular-nums. Ticker weight 680. Category chip uses thin-bordered `tag`.
- **Symbol cell trigger** (`div.sym-trigger[tabindex="0"][role="button"]`): inherits font from cell, no background, no border, padding 0, `cursor:help`, dotted underline on hover or focus. Looks like plain text until probed.
- **Price cell trigger:** same chrome-free styling. The cell wraps `price + .sub move` inside the trigger so the whole price block is hoverable and the popover anchors correctly.
- **Popover (`.pop`):** `--surface` background, `--ink` text, padding 12–14px, border-radius 4px, `box-shadow:0 6px 20px rgba(15,25,31,.10), 0 1px 2px rgba(0,0,0,.04)` on desktop and a stronger bottom-sheet shadow on mobile. Desktop uses `width:max-content`, `min-width:min(300px, calc(100vw - 64px))`, and `max-width:min(560px, calc(100vw - 64px))`; do not use a narrow fixed width that causes avoidable wrapping. Tablet / phone uses fixed bottom-sheet placement, safe-area insets, high z-index, `max-height:min(72vh, calc(100dvh - 32px))`, internal scrolling, and long-text wrapping. Inner table uses 11.5px tabular numerics; desktop lot-table cells stay `white-space:nowrap`, while mobile/touch sheets restore normal wrapping.
- **Risk heatmap:** 5-column grid. Cells separated by 1px hairline (not gap). Each cell carries a 3px left risk rule (low / mid / high = light blue / amber / red). Cell contents: ticker, `Risk N/10`, `weight · move`. **Do not** flood the cell with saturated background color.
- **Action list:** 84px label column on the left (translated per SETTINGS), description on the right. Rows separated by dotted hairline.
- **Border-radius:** keep page-wide radius in **2–4px**. Only chips / badges may go to 3–4px; bar tracks 2px. Popovers may go to 4px. **Never** use radius ≥ 8px. **Never** use `border-radius:999px` (pill) on cards, bars, or tracks.
- **Shadow:** as a rule, no box-shadow on the page. Popovers are the single exception. Hover hints cap at `0 1px 0 rgba(0,0,0,.04)`. **Never** ship `0 10px 28px rgba(...)` floating shadows on regular content.
- **Separation hierarchy:** prefer hairline (1px) + whitespace; then semantic color; only then a faint background tint.

### 14.6 Price-cell static styling

```css
.price-cell{position:relative;}
.price-trigger{
  display:inline-flex;
  flex-direction:column;
  align-items:flex-end;
  gap:2px;
  cursor:help;
}
.price-num{
  color:var(--ink);
  font-size:clamp(15px, 0.6vw + 13px, 17px);
  font-weight:650;
  line-height:1.12;
  font-variant-numeric:tabular-nums lining-nums;
}
.price-sub{
  color:var(--muted);
  font-size:clamp(11px, 0.2vw + 10.4px, 12px);
  font-variant-numeric:tabular-nums lining-nums;
}
.price-sub.pos{color:var(--pos);}
.price-sub.neg{color:var(--neg);}
```

### 14.7 Responsive / mobile (RWA) breakpoints

The HTML must include `<meta name="viewport" content="width=device-width, initial-scale=1">` and three breakpoint tiers. **Treat phone behavior as a first-class concern — most quick re-checks happen on a phone.**

| Tier | Range | What changes |
|---|---|---|
| Desktop | ≥ 881px | Default layout — all multi-column grids active, no horizontal scroll. Body 14.5–15.5px, table 13–13.5px |
| Tablet | 601–880px | KPI strip → 2 cols. `cols-2` / `cols-3` → 1 col. Donut + bars stack. Risk heatmap → 2 cols. Body 14–14.5px, table 13px. Bar-row label width tightens |
| Phone | ≤ 600px | KPI strip → 1 col. Risk heatmap → 1 col. Holdings table is wrapped in `.tbl-wrap` with horizontal scroll. **First column (Symbol) is `position:sticky; left:0; z-index:1` with a 1px shadow** so the user never loses row context while scrolling; **the header's first cell must override back to `z-index:calc(var(--table-header-z) + 1)` and `background:var(--paper)`** so it stays above row cells. **Body 14px floor, table 12.5px floor, sublines 11px floor — never lower.** Footer / legend density tightens. Action labels narrow to a 64px column |

**Required wrappers and patterns:**

- The holdings table is always wrapped in `.tbl-wrap`:
  ```html
  <div class="tbl-wrap"><table>…</table></div>
  ```
  Desktop `.tbl-wrap` must **not** set `overflow-x:auto`; otherwise browsers may clip descendant popovers. Enable `overflow-x:auto` and `-webkit-overflow-scrolling:touch` only at tablet / phone breakpoints, where popovers switch to fixed bottom sheets. Keep a negative left/right margin equal to the page's side padding and a `min-width` on the inner table (≥ 680px on phone, ≥ 760px on tablet) so the layout doesn't collapse into illegibility.
- **Sticky first column on phone:** applies to both `th:first-child` and `td:first-child`, with `background:var(--surface)` so cells don't bleed through during scroll, and a 1px right shadow (`box-shadow:1px 0 0 var(--hairline)`) as the affordance edge. Add a later `thead th:first-child{z-index:calc(var(--table-header-z) + 1);background:var(--paper)}` override because the generic first-column rule otherwise lowers the sticky header's z-index.
- **KPI strip on phone:** collapse to 1 column with row borders. Numeric value font respects the `clamp()` floor.
- All cells that use `border-right` or `border-left` for column-style separation must have those properties **reset** under the phone breakpoint to avoid orphan rules.
- **Touch targets** (popover triggers, links inside tables) must remain **≥ 30px tall** on phone.
- **Test the report at 360px width before shipping.** Open in iOS Safari and Chrome Mobile. Verify the popovers position correctly and never clip outside the viewport.

### 14.8 Anti-patterns (must avoid)

- Dark gradient hero (`linear-gradient(135deg,#0b1220,...)`).
- Heavy box-shadow (`0 10px 28px rgba(...)` or stronger) on regular content (popovers excepted).
- Saturated background washes (red / blue / green flooding a region).
- Heading weights ≥ 800.
- Pill border-radius (999px) on cards, bars, tracks.
- Multiple `<style>` blocks overriding each other. The new spec allows **one** `<style>` block, ordered: tokens → base → layout → components.
- Loading any external font (Google Fonts, `@font-face` over the network).
- Reintroducing IRR or annualized-return columns (see §9.4).
- Bilingual or English-fallback labels in any cell, header, or button when SETTINGS specifies a non-English language (see §5).
- Visible font sizes below the floors in §14.4.

### 14.9 Reference implementation

`reports/_sample_redesign.html` **CRITICAL — MUST READ** is the canonical reference. New reports must align color, typography, layout, and component styling with this file. If it is missing, rebuild from the tokens and rules in this section.

---

## 15. Investment content standard

### 15.1 Voice and stance

- Output language follows `SETTINGS.md` strictly (see §5). Default tone: **professional research note**, not casual chat. Be concise, direct, and data-driven.
- Do not be reflexively conservative. The user can absorb large drawdowns; aggressive calls are welcome — but every aggressive call must be supported by data and a clear trigger.
- Do not mechanically recommend selling on a short-term dip — judge whether fundamentals have actually deteriorated.
- Do not chase strength blindly — check valuation, growth, catalysts, and how much expectation is already in the price.

### 15.2 Position handling

- Read holdings dynamically from `HOLDINGS.md`. **Do not** hard-code positions.
- Long-term core, mid-term growth, and short-term positions must be judged separately. The same ticker, in different buckets, can warrant different actions.
- For high-growth, high-volatility names, frame the call across **bull / base / bear** scenarios.
- Recommendations must include **action, price band, and trigger** — for example: "hold", "trim 20%", "stop below $X", "add above $Y", "do not add into earnings". Translate the verbs.
- When recommending a trim, name the **specific lot(s)** to sell using the lot's acquisition date — e.g. "trim the 2025-09 KAPA lot first (highest cost basis)". **Default ordering is highest cost basis first**; deviate only with an explicit reason.
- Use hold period and per-lot P&L (visible in the Price popover) to interpret raw aggregate P&L — a +30% gain over 3 months is not the same story as +30% over 3 years. Reflect that in the action.
- Data gaps, estimates, and source conflicts must be flagged explicitly.

### 15.3 Today's action list (must produce, in this order — translate the labels)

1. **Must do** — actions to execute today.
2. **May do** — opportunistic actions if a price / event condition fires.
3. **Avoid** — explicit don'ts for today.
4. **Need data** — open data gaps that, if closed, would sharpen the call.

---

## 16. Reply format to user

When replying:

- Give the **absolute path** to the HTML.
- Include a brief list of the **most important alerts** and **data gaps**.
- If a `yfinance` automatic correction succeeded during the run, include a concise **建議更新 agent spec** note that states the observed failure pattern, the successful fix, and the exact wording worth adding to this spec.
- **Do not** ask the user to assemble, install, or run anything.
- Reply in the SETTINGS language.

---

## Appendix A — Pre-delivery self-check

Run every item before declaring the report complete. Each item maps back to its rule section.

### A.1 Inputs & language

- [ ] `HOLDINGS.md`, `SETTINGS.md`, and `/docs/*` were read fresh this run (§4, §0).
- [ ] Output language matches `SETTINGS.md`; `<html lang>` matches; no bilingual labels (§5).
- [ ] Stray non-language text grep clean except §5.2 allow-list (§5.3).

### A.2 File output

- [ ] HTML at `reports/YYYY-MM-DD_HHMM_portfolio_report.html` (§6).
- [ ] Timestamp prefix uses the local clock at execution time (§6).
- [ ] No companion Markdown / other files written (§6).

### A.3 Self-containment

- [ ] No `<script src=...>`, no `<link rel="stylesheet">`, no CDN chart libs (§7.1, §7.3).
- [ ] No runtime `fetch` / `XMLHttpRequest` / API key / market endpoint in the HTML (§7.2).
- [ ] HTML is valid and visually complete with JS disabled (§7.2).
- [ ] Self-containment grep ran clean (§7.3).
- [ ] Single `<style>` block, ordered tokens → base → layout → components (§14.8).

### A.4 Latest-price retrieval

- [ ] `yfinance` subagent ran first, batched where possible (§8.2).
- [ ] Pacing rules respected: `threads=False`, ≥ 1.5–2.0s gap, ≤ 25/batch, single session, 10–15s timeout (§8.3).
- [ ] Failures got up to 3 auto-corrections before fallback (§8.4).
- [ ] Per-asset fallback order followed (§8.5).
- [ ] Freshness gate applied; no stale value accepted before exhausting sources (§8.7).
- [ ] §8.8 fields stored per ticker; `n/a` rendered when nothing was credible (§8.7, §9.6).
- [ ] No API keys, tokens, or auth URLs leaked into HTML (§7.2, §8.6).

### A.5 Computations

- [ ] Totals, weights, P&L, per-lot P&L, weighted-avg cost (§9.1).
- [ ] Hold period rendered with `Xy Ym` / `Nm` / `Nd` / `n/a` rule (§9.2).
- [ ] Move % derived from selected price; subline-only `n/a` if missing (§9.3).
- [ ] **No IRR column** anywhere (§9.4).
- [ ] Book-wide pacing aggregates computed (§9.5).
- [ ] Glyphs: `—` for not-applicable, `n/a` for missing; cell-level not row-level (§9.6).

### A.6 Required sections

- [ ] HTML contains all 11 sections in order (§10.1).
- [ ] Holdings table has the 7 columns in order; `Held` / `Move` are removed (§10.2).
- [ ] Holding period & pacing has 4-cell KPI + 5-segment strip + bucket-notes (§10.3).
- [ ] All 8 inline charts present, no external chart lib (§10.4).
- [ ] News items have date, source, link, impact tag (§10.5).
- [ ] Forward events block covers earnings, calls, ex-div, launches, regulators, M&A, raises, debt maturities, lockup expiries, macro releases (§10.5).
- [ ] **High-priority alerts** block surfaced at top of HTML when any §10.6 trigger fired.

### A.7 Per-run special checks

- [ ] All 10 special checks evaluated and answered explicitly (§11). Clean passes are stated, not silently omitted.

### A.8 Static price snapshot

- [ ] Generation-time retrieval order followed (§12.1).
- [ ] Price cell + price popover display rules met (§12.2).
- [ ] Source audit lists every provider, with degraded / EOD / `n/a` reasons (§12.3).

### A.9 Cell popovers

- [ ] Symbol & Price cells use `<div tabindex="0" role="button">` triggers (§13.2).
- [ ] CSS uses descendant-popover `:hover` / `:focus-within` pattern (§13.3).
- [ ] Symbol popover contents present (§13.4).
- [ ] Price popover contents present, including `<tfoot class="summary">` row (§13.5).
- [ ] Tablet/phone bottom-sheet behavior verified at ≤ 880px and ≤ 600px (§13.6).
- [ ] `prefers-reduced-motion` honored (§13.7).
- [ ] No popover anti-patterns from §13.8 present.

### A.10 Visual design

- [ ] Design tokens declared on `:root` (§14.2).
- [ ] System font stacks only; no external font loaded (§14.3).
- [ ] Required typography settings (smoothing, font-feature-settings, weights, letter-spacing, line-height) applied (§14.3).
- [ ] All elements obey the `clamp()` floors in §14.4.
- [ ] Layout & component rules followed (§14.5).
- [ ] Price-cell static styling matches §14.6 reference.
- [ ] RWA: 3 breakpoints behave correctly; phone tested at 360px in iOS Safari and Chrome Mobile (§14.7).
- [ ] No visual anti-patterns from §14.8 present.
- [ ] Visual alignment with `reports/_sample_redesign.html` reviewed (§14.9).

### A.11 Investment content

- [ ] Voice is professional research-note (§15.1).
- [ ] Recommendations include action + price band + trigger (§15.2).
- [ ] Trims name specific lot(s) by acquisition date, default highest-cost-first (§15.2).
- [ ] Today's action list has the 4 buckets in order, translated (§15.3).

### A.12 Reply

- [ ] Absolute path to HTML given (§16).
- [ ] Most important alerts and data gaps listed (§16).
- [ ] **建議更新 agent spec** note included if any `yfinance` auto-correction or pacing tweak succeeded (§8.3, §8.4, §16).
- [ ] Reply written in the SETTINGS language (§16).
