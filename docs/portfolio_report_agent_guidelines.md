# Portfolio Report Output Guidelines

For future agents: the portfolio report in this repo is the *final deliverable*, not a frontend project. Do not break the user-facing report into multiple executable scripts or external resources.

This spec is the single source of truth for any "portfolio health check" / "portfolio report" run. When invoked, follow it end-to-end.

## When this spec applies

- Trigger phrases: "portfolio health check", "pre-market battle report", "run my portfolio report", or any explicit request for a portfolio risk / exposure / action report.
- Default framing: **Portfolio report**. Even if the agent is executed mid-day or after-hours, still produce the full analysis and write the local files. Do not skip sections because the market is closed.

## Output language (HARD REQUIREMENT)

`SETTINGS.md` declares the output language. **Every** user-facing string in both the HTML and the Markdown must be in that language — no bilingual mixing, no untranslated headers, no English fallbacks because "the term has no good translation".

- The `<html lang="…">` attribute must match (`zh-TW`, `en`, `ja`, etc.).
- Every section title, table header, KPI label, badge, tag, callout text, action label, tooltip / popover content, and prose paragraph must be in the SETTINGS language.
- The only allowed non-language tokens are: ticker symbols (`NVDA`, `2330.TW`, `BTC`), currency codes (`USD`, `TWD`), unit symbols (`%`, `$`, `NT$`), ISO dates (`2026-04-27`), URL hostnames in citations, and bracketed source names that are inherently English (`Reuters`, `StockAnalysis`).
- Bilingual headers like `代號 Symbol` or `損益 P&L` are **not** acceptable. Pick one — the SETTINGS language.
- State badges (the chips next to the latest price): translate them. For Traditional Chinese: `盤前` / `盤中` / `盤後` / `收盤` instead of `pre` / `open` / `after` / `close`.
- Tag chips (`High vol`, `Long`, `Mid`, `Rich val`): translate every label. Default English class names stay (the CSS hooks); the visible text is translated.
- The HTML `<title>` and the Markdown filename header line must also be in the SETTINGS language (filenames themselves stay ASCII per the file-output rule).
- Self-check before delivery: search the rendered HTML and Markdown for stray English words; every hit that is not in the allow-list above must be translated or removed.

If `SETTINGS.md` is missing or unparseable, default to **English** and surface the missing setting as a `n/a` in the masthead meta row.

## File output

- Both files must be written to `reports/`.
- HTML filename: `YYYY-MM-DD_HHMM_portfolio_report.html`
- Markdown summary filename: `YYYY-MM-DD_HHMM_portfolio_report.md`
- Use the local clock at execution time for the timestamp prefix; both files share the same prefix.

## Hard rules

- The HTML must be a single self-contained file directly openable in the browser: all CSS, charts, data, and any required interactive logic must be inlined in the same HTML.
- Do not leave external generator scripts, external CSS, CDN dependencies, build artifacts, or frontend project structure in the repo.
- If you need a temporary script to wrangle data, keep it in `/tmp` or use it once. Do not check it in as a deliverable.
- The final delivery should contain only the requested HTML, the Markdown summary, and any necessary updates to the spec docs.
- The HTML must not depend on local relative paths, `file://` images, external fonts, external chart libraries, or any service that requires login or payment.
- External URLs are allowed *only* as data-source citations and as runtime fetch endpoints for the **Live price refresh** mechanism (see below — strict whitelist). Never as runtime style, generic script source, or chart-library dependency.
- If a value cannot be retrieved, render it as `n/a` and list it under the Sources & data gaps audit section — do not fill in by guesswork. A value you derived (e.g. P&L from your own cost basis) is fine; a guess at a market data point you could not source is `n/a`. See **Missing-value glyphs** for the two-glyph convention.

### Inline JavaScript — two permitted use cases

Inline `<script>` is allowed **only** for these two purposes. Anything else must use SVG / CSS.

1. **Live price refresh** — polls a whitelisted public price API every 60 seconds (with ±5s jitter and per-ticker stagger) and animates the price cell on change. Detail in **Live price column**.
2. **Cell popovers** — opens a hover/tap popover with per-lot detail on the Symbol and Price cells. May use the native HTML `popover` attribute (no JS needed for that pattern) or a tiny inline script if the `popover` API is not viable in the target browser.

Constraints that apply in both cases:

- All script must be **inline** (`<script>...</script>`); no `<script src=...>`.
- No third-party libraries, no bundlers, no transpiled output. Hand-written ES2020 only.
- The HTML must remain valid and visually complete when JavaScript is disabled or the network is offline. Snapshot prices written into the HTML at generation time stay visible; the live mechanism merely overlays.
- No API keys, no auth tokens, no user-identifying headers. The whitelist endpoints below are all key-free.
- All fetches must include a 5-second timeout and a graceful-failure path (keep the snapshot value, do not blank the cell).
- Polling must pause when `document.hidden === true` and resume on `visibilitychange`.

## HTML self-containment check

After producing the report, verify the HTML:

- No `<script src=...>`.
- No `<link rel="stylesheet"...>`.
- No `<script>` or `<link>` that pulls a chart library from a CDN.
- Inline `<style>`, inline SVG, inline tables, inline data, and the two permitted inline-JS use cases are allowed.
- For static-only reports (no live refresh requested), prefer SVG / CSS over JavaScript.

Suggested check:

```sh
rg -n "<script\\s+src=|<link[^>]+stylesheet|href=.*\\.css" reports/*.html
```

For each hit, confirm it is purely a citation link; if it is anything else, inline it.

## Data freshness

- Always search the web for the latest market data at generation time. Never rely on stale model memory.
- Each holding must be refreshed for: latest price, pre / after-market price, day and recent move, market cap, valuation multiples (PE, Forward PE, PS, EV/EBITDA where relevant), volume, next earnings date, and any imminent material event.
- Source priority: company IR, SEC / exchange filings, official press releases, then StockAnalysis, Nasdaq, Yahoo Finance, Reuters, CNBC, MarketWatch; for crypto, CoinMarketCap and CoinGecko.
- If a credible source cannot be found, render the field as `n/a` (per **Missing-value glyphs**). If a number is your own derivation, label it `estimate`. Never silently guess.

## Reading inputs

- Auto-read all positions from `HOLDINGS.md` at run time. Do not hard-code holdings, do not assume any specific ticker is present, and re-classify on every run.
- Auto-classify each holding by asset class, sector, and theme based on current data. Buckets are not fixed — examples include ETF, single stock, crypto, cash, semiconductor, AI, energy, aerospace, financials, healthcare, consumer, industrial, optical / data center, defense, other. Use whatever fits the actual book.
- Read `SETTINGS.md` for output language, tone, and (if present) position-sizing rails. Settings rails override the defaults in this spec when in conflict. Language is enforced per **Output language**.

### Lot format

Every lot in `HOLDINGS.md` follows:

```
<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD>
```

- `on YYYY-MM-DD` is the **acquisition date** for that lot. It powers per-lot tooltips and hold-period analytics.
- Crypto / FX use `<SYMBOL> <quantity> @ <cost> on <YYYY-MM-DD>` (no "shares").
- `?` is allowed in place of cost or date when truly unknown — render the affected metric as `n/a` in the report (see **Missing-value glyphs**). Never invent a value.
- A ticker may have multiple lots across the four buckets (Long Term, Mid Term, Short Term, Cash Holdings). Aggregate per ticker for the holdings table; keep the lot-level array embedded in the page so the per-lot popover can render without a re-fetch.

## Computations the report must produce

- Total assets, invested position, cash & cash-equivalent value, cash ratio.
- Per-holding weight (% of total assets), theme weight, sector weight.
- Per-holding P&L using the cost basis in `HOLDINGS.md`. For lots with `?` cost, render P&L as `n/a`.
- Per-lot P&L (used by the Price popover) — `(latest_price − lot_cost) × lot_qty`. Skip lots with `?` cost.
- Per-ticker weighted-average cost (used by the Price popover) — `Σ(lot_cost × lot_qty) ÷ Σ(lot_qty)` over lots with known cost.
- For each holding, the freshness fields listed under **Data freshness**.
- **Hold period (per ticker)** = duration since the *oldest* lot's acquisition date. Display in `Xy Ym` for ≥ 1 year, otherwise `Nm` or `Nd`. If any lot has a `?` date, render as `n/a`.
- **Latest price (per ticker)** = the most current observable price. Apply this fallback chain in order, take the first that returns a value:
  1. **Pre-market** quote, when the pre-market session is in progress for the ticker's market (badge `pre`).
  2. **Intraday / regular-session** quote, when the regular market is open (badge `open`).
  3. **After-hours / extended-session** quote, when the after-hours session is in progress (badge `after`).
  4. **Prior session close** (badge `close`, the explicit fallback marker — outside trading hours, holidays, or when no live source returned a value).
  Each cell records the value plus which step was used. If even close is missing, the cell shows `n/a` with a `close` badge so the empty fallback chain is obvious.
- **Today's move %** is derived from the latest price — `(latest − prior_close) / prior_close`. Render as a small subline under the price.
- **IRR is intentionally not computed.** A previous version of this spec annualized P&L; that produced misleading 4-digit % numbers for short-window high-volatility names. Hold period plus per-lot P&L (in the Price popover) carries the same context without the bad math. Do not reintroduce IRR.
- **Book-wide pacing aggregates**:
  - Cost-weighted average hold period across all risk assets (ex-cash).
  - Oldest lot in the book (ticker + date + duration).
  - Newest lot in the book (ticker + date + duration).
  - % of risk-asset value held > 1 year.
  - Distribution of risk-asset value across the buckets `< 1m`, `1–6m`, `6–12m`, `1–3y`, `3y+`.

### Missing-value glyphs

Two glyphs cover every "no value" case in the report. Pick one per cell — never leave a cell empty, never write the words "data gap" / "missing" / "unknown" inside a cell.

| Glyph | Meaning | Use for |
|---|---|---|
| `—` (em-dash, `.na` style, muted-gray) | **Not applicable** — the metric never makes sense for this row | Cash and pure cash-equivalent rows in the P&L column; any row + column combination where the metric is structurally undefined |
| `n/a` (lowercase, muted-gray) | **Missing** — the metric *should* exist but the input is `?` in `HOLDINGS.md` or could not be sourced | Cost-basis-derived metrics when cost is `?`; date-derived metrics when date is `?`; market data fields when no credible public source returned a value |

The semantic split lets the user scan the table once: every `—` is expected, every `n/a` is something to fix in `HOLDINGS.md` or trace back to a missing data source. The audit section ("Sources & data gaps") at the bottom of the report enumerates each `n/a` with the reason and the `HOLDINGS.md` line or URL needed to close it.

`n/a` applies per cell, not per row. If cost is missing but the price feed is fine, only `P&L` renders `n/a`; the latest price still shows.

## Required report sections

### HTML — must contain, in order

1. Today's summary
2. Portfolio dashboard (KPIs)
3. Holdings P&L and weights (table)
4. Holding period & pacing
5. Theme / sector exposure
6. Latest material news
7. Forward 30-day event calendar
8. High-risk and high-opportunity list
9. Recommended adjustments
10. Today's action list
11. Sources and data gaps

### Holdings table — required columns

The holdings table in section 3 uses these columns, left to right. **Default to scan-light, hover-to-reveal**: visible cells stay short; full detail lives in popovers attached to the Symbol and Price columns.

1. **Symbol** — ticker only, weight 680, monospace-friendly. **No** company subline, **no** since-line, **no** lot count visible by default. All of that lives in the Symbol popover (see **Cell popovers**).
2. **Category** — asset class plus a single tag chip (`High vol`, `Long`, `Mid`, `Short`, `Rich val`, `Overheated`, `High risk`, `Cash`, etc.). Translate to SETTINGS language.
3. **Price** — latest price, large; a small move % subline below with the state badge (`pre` / `open` / `after` / `close` translated). The whole cell is the popover trigger (see **Cell popovers**) and the live-refresh target (see **Live price column**).
4. **Weight** (num) — % of total assets.
5. **Value** (num) — current market value (USD basis).
6. **P&L** (num) — `±$X / ±Y%`. Cash → `—`. Cost missing → `n/a`. (Detail per lot lives in the Price popover; this column is the at-a-glance aggregate.)
7. **Action** — recommendation with action verb, price band, and trigger.

The `Held` and `Move` columns from earlier specs are removed. Hold period stays available in the Symbol popover and aggregated in **Holding period & pacing**.

### Live price column

The Price column refreshes itself every **60 seconds** and animates on change. Implementation must be inline-only, gracefully degrade, and behave like a polite browser tab — not a scraper.

**Refresh mechanism**

- One inline `<script>` block at the bottom of `<body>`. The block embeds a JSON payload with the holdings (ticker, market, lot list) and a per-ticker snapshot price written at generation time.
- Base interval `REFRESH_MS = 60_000` (1 minute), with **per-cycle jitter** of ±5 s (`Math.random() * 10_000 - 5_000`) so two browser tabs of the same report do not synchronize their requests.
- Within a cycle, **stagger** per-ticker requests by ~800 ms each (rather than firing N requests in the same tick). Batch endpoints (CoinGecko `simple/price?ids=a,b,c`) count as one request.
- `document.addEventListener('visibilitychange', ...)` pauses polling when the tab is hidden. On return, fire an immediate refresh, then resume the cycle.
- Each fetch uses `AbortController` with a 5-second timeout. On failure, retain the previous value and switch the `.live-ts` chip to `.stale` styling. Two consecutive failures → switch to `.offline`.

**Whitelisted endpoints**

| Asset class | Endpoint | CORS | Notes |
|---|---|---|---|
| Crypto | `https://api.coingecko.com/api/v3/simple/price?ids=<id>,<id>,…&vs_currencies=usd&include_24hr_change=true` | ✅ direct | Free, no key. **Always batch** — one call per cycle covering every crypto holding |
| US equities & ETFs | `https://query1.finance.yahoo.com/v8/finance/chart/<TICKER>?interval=1m` | ❌ blocked | Yahoo public chart endpoint. Includes `regularMarketPrice`, `preMarketPrice`, `postMarketPrice`, `previousClose`. Must route through a CORS proxy (see below) |
| Taiwan equities | Same Yahoo endpoint, use `2330.TW` form | ❌ blocked | Same proxy chain |

If a ticker has no working endpoint, the snapshot price stays visible with a `close` badge and a small `(static)` indicator in the popover.

**CORS proxy chain (for Yahoo only)**

Browsers strip / forbid setting `User-Agent`, `Origin`, and `Referer` from `fetch()` — there is no way to make a Yahoo request from inside an HTML report look like it came from `finance.yahoo.com`. The realistic workaround is to relay through a public CORS proxy. Maintain a short, rotating list and try in random order:

```js
const CORS_PROXIES = [
  (u) => 'https://corsproxy.io/?'                   + encodeURIComponent(u),
  (u) => 'https://api.allorigins.win/raw?url='      + encodeURIComponent(u),
  (u) => 'https://api.codetabs.com/v1/proxy?quest=' + encodeURIComponent(u),
];
```

For each Yahoo request, shuffle the list, try the first proxy, fall through on timeout / non-2xx. If every proxy fails, drop to snapshot for that ticker.

**Disguise & anti-blocking — what actually works in a browser**

Browsers strip these headers from `fetch()`, so do **not** waste effort:

- `User-Agent` (browser sets its own; ignored if you try)
- `Origin`, `Referer` (browser-managed)
- `Cookie` (cross-origin restrictions)
- `mode: 'no-cors'` (response becomes opaque, can't read JSON)

What does work and is **mandatory**:

1. **Polite headers** the browser allows you to set:
   ```js
   headers: {
     'Accept': 'application/json, text/plain, */*',
     'Accept-Language': 'en-US,en;q=0.9',
   }
   ```
2. **In-memory cache with TTL ≥ 50 s** — keyed by ticker, so a popover open / page focus / manual refresh doesn't re-hit the API. Use `Map<ticker, {t, value}>`.
3. **Per-cycle jitter** (above) — desynchronizes multiple tabs.
4. **Per-ticker stagger** — spread N requests across the minute instead of bursting.
5. **Batch where possible** — CoinGecko supports comma-separated `ids=`; Yahoo's `/v7/finance/quote?symbols=` works through proxies for batches up to ~10 symbols.
6. **Exponential backoff on 429 / 503** — double the cycle interval on failure (cap at 5 minutes), reset on first success. Honor `Retry-After` header if present (use `Math.max(currentBackoff, parseInt(retryAfter) * 1000)`).
7. **Concurrent request cap** — at most 3 in flight at once; queue the rest.
8. **Quiet on idle** — `document.hidden` pauses everything (already required above).
9. **Proxy rotation** — see chain above. Never hammer a single proxy on consecutive cycles.
10. **No retry storms** — exactly one retry per ticker per cycle; if the cycle fails, wait for the next cycle (plus backoff).

If a public proxy in the chain starts blocking, **remove it from the spec list** rather than chaining ten unstable proxies. The list is intentionally short.

**Source-selection logic per refresh**

```
if response has preMarketPrice and current_time in pre-market window  → use preMarketPrice  + badge "pre"
elif response has regularMarketPrice and market is open                → use regularMarketPrice + badge "open"
elif response has postMarketPrice and current_time in after-hours      → use postMarketPrice + badge "after"
else                                                                   → use previousClose    + badge "close"
```

Market windows must be derived from each ticker's exchange (US: 09:30–16:00 ET regular, 04:00–09:30 pre, 16:00–20:00 after; TW: 09:00–13:30 TPE regular). Embed the windows in the page.

**Animation**

- On every refresh, compare the new price to the value currently in the cell.
- If new > old: add class `flash-up` to the cell.
- If new < old: add class `flash-down`.
- The class triggers a 1.2-second CSS transition that flashes the cell background with a low-alpha tint of `--pos` or `--neg`, then fades back to transparent. The price text simultaneously shifts color (full `--pos` / `--neg` for ~200ms, then back to `--ink`).
- After 1.2 seconds the JS removes the class so the next change can re-trigger the animation.
- A small `.pulse-dot` (8px circle) lives in the Price column header and pulses once per successful refresh as a heartbeat, so the user knows the live feed is alive even if no prices changed.
- Animation must respect `@media (prefers-reduced-motion: reduce)` — drop to a 1-frame highlight, no fade.

**Display extras**

- Last-refresh timestamp (`HH:MM:SS`) lives in a small `.live-ts` chip in the Price column header. Updated on every successful refresh.
- States: `.live-ts` (default, fresh) / `.stale` (one cycle missed, warn color) / `.offline` (two+ cycles missed or all proxies failing, neg color).
- The heartbeat dot pulses on every successful cycle. Suppress the pulse when stale/offline.

### Cell popovers (Symbol & Price)

Both the Symbol and Price cells expose a popover that **opens on hover** (desktop) and **slides up as a bottom sheet on tap** (touch / tablet). The popover fades in / out — no click required, no toggle state. The previous `<button popovertarget>` + native HTML `popover` pattern is **deprecated** because:

- It required a click to open, which conflicts with the hover-to-preview UX.
- The native top-layer rendering disabled fade-in animations and made the popover feel modal rather than ambient.

The new pattern is a CSS-driven `:hover` / `:focus-within` popover, structured as a *descendant* of the trigger so that hover propagates naturally and there is no JavaScript dependency for the show/hide.

#### HTML structure

```html
<td>
  <div class="sym-trigger" tabindex="0" role="button">
    NVDA
    <div class="pop pop-sym" role="tooltip">
      …translated: company name, asset class, since-line, lot count, rationale…
    </div>
  </div>
</td>

<td class="num price-cell" data-ticker="NVDA" data-price="…" data-prev="…">
  <div class="price-trigger" tabindex="0" role="button">
    <span class="price-num">$211.62</span>
    <span class="price-sub pos">+1.40%<span class="state pre">盤前</span></span>
    <div class="pop pop-px" role="tooltip">
      <h4>NVDA · 每批損益</h4>
      <div class="pop-sub">最新價 $211.62 <span class="state pre">盤前</span></div>
      <table>… per-lot rows + summary tfoot …</table>
    </div>
  </div>
</td>
```

The trigger is a `<div tabindex="0" role="button">` (not `<button>`) because the popover may contain a `<table>`, which is invalid inside a `<button>`. The `role="button"` keeps screen-reader semantics; `tabindex="0"` keeps keyboard focusability.

#### Visual style — light, paper-tinted, no reverse colors

The popover uses the same surface palette as the rest of the page. **Do not** use a dark background with light text — that breaks the editorial look and makes the popover feel like a different application surface.

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

Internal styling uses the same tokens as the page body — `--ink` text on `--surface`, `--muted` for sublines, `--hairline` for dividers, `--pos` / `--neg` for signed numbers. No custom dark-mode palette inside the popover. On desktop, popovers must expand to fit their content up to the viewport-aware max width; do not force table cells or short labels to wrap early. Long flex value cells such as `.pop-row .v` should use `min-width:0; text-align:right; overflow-wrap:break-word;` so only genuinely long prose wraps.

#### Symbol popover content

- Company / instrument full name (translated when natural).
- Asset class and theme tags.
- `since YYYY-MM · <duration> · N lot(s)` line.
- Optional one-line rationale (why the position is in Long / Mid / Short bucket, if non-obvious).

#### Price popover content

- A heading with the ticker + "每批損益" (translated per SETTINGS).
- A subline with the latest price plus the same state badge as the cell.
- A small table: one row per lot with columns `取得日 / 成本 / 數量 / 損益` (translated). Numeric columns right-aligned with tabular numerals.
- A `<tfoot class="summary">` row showing **平均成本 / 總成本 / 總損益**. Top-bordered, semibold.
- If cost is `?` for a lot, render that row's P&L as `n/a` and exclude it from the average-cost calculation.

#### RWA — popover on tablet, phone, and touch

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

#### Reduced motion

Honor `@media (prefers-reduced-motion: reduce)` — drop the fade and slide to an instant show / hide:

```css
@media (prefers-reduced-motion: reduce){
  .pop{transition:opacity .01s linear, visibility 0s !important;transform:none !important}
}
```

#### Anti-patterns

- **Reverse-color popovers** (dark background + light text). The popover is part of the page palette, not a separate surface.
- **Click-to-open popovers** on desktop. The user explicitly wants hover preview; clicking is reserved for nothing in this column.
- **Popovers anchored to the cell or the row** rather than to the trigger element — that pushes them away from the cursor and weakens the "next to mouse" feel.
- **`<button>` as the trigger when content includes block elements** (e.g. tables) — invalid HTML; use `<div tabindex="0" role="button">`.
- **`overflow:hidden` on `.tbl-wrap`** — silently clips popovers. Use `overflow-x:auto` only when needed (tablet + phone) and rely on the `position:fixed` bottom-sheet escape hatch.
- **Mobile bottom sheets without viewport bounds** — any mobile / touch popover must have safe-area-aware left/right/bottom, a `100dvh`-based max height, internal scrolling, long-text wrapping, and active-cell z-index promotion.

### Holding period & pacing section — must contain

- A 4-cell KPI strip: **Avg hold (cost-weighted)**, **Oldest lot** (ticker + since-date + duration), **Newest lot** (ticker + since-date + duration), **% of risk assets held > 1 year**.
- A horizontal stacked `period-strip` with five segments — `< 1m`, `1–6m`, `6–12m`, `1–3y`, `3y+` — and a matching legend showing the % in each bucket.
- Zero or more `bucket-note` callouts surfacing pacing issues: bucket misclassification (e.g. Short Term lot held > 12 months), recent buying spree (3+ adds in 30 days), averaging-up risk (latest add > 1.1× older avg cost), or open cost-basis gaps.

### Markdown summary — must contain

1. Today's verdict
2. High-priority alerts
3. Top 10 holdings by weight
4. Latest material news summary
5. Forward 30-day events
6. Holding period & pacing flags (one-liners — only items that triggered)
7. Recommended adjustments
8. Today's action list
9. Data gaps

The Markdown is static — no live refresh. Snapshot prices at generation time only.

## Required charts (inline SVG / CSS only)

- Asset allocation donut
- Holdings weight bar chart
- P&L ranking bar chart
- Sector / theme exposure bar chart
- Hold-duration stacked strip (the bar inside **Holding period & pacing**)
- Forward 30-day event timeline
- High-risk position heatmap
- Cash vs. risk-asset ratio bar

Every chart must have a clear title, readable labels, and tabular numerals. No external chart libraries; build with SVG `path` / `circle` / `rect` / `text` and CSS bars. See **Visual design standard** for color and weight rules.

## News & event coverage

- For each core position, surface 1–3 recent material news items.
- If the book is large, prioritize: highest weight, highest recent volatility, recent material events, largest losers.
- Each news item must include date, source name, link, and impact tag — `positive` / `neutral` / `negative` (translate per SETTINGS).
- Forward events to track: earnings, earnings calls, shareholder meetings, ex-dividend dates, product launches, regulatory decisions, industry policy, M&A, raises, debt maturities, lockup expiries, plus macro releases relevant to the book (FOMC, CPI, PCE, NFP, etc.).

## High-priority alerts (top of report)

Surface a **High-priority alerts** block at the very top of the HTML and at the top of the Markdown whenever any of the following triggers fire:

- Single asset weight > 20%.
- Any correlated theme bucket > 30%.
- Any high-volatility bucket > 30%.
- Any short-term position with single-day move > 8%.
- Any position with earnings within 7 days *and* weight > 5%.
- Any position breaking below 50-day MA *and* news flow turning negative.
- Any position trading > 20% above analyst consensus target.
- Any position with material negative news, guidance cut, regulatory risk, liquidity risk, dilution risk, or debt risk.

## Per-run special checks

In addition to the alert triggers above, every run must explicitly evaluate and answer:

- Any single asset > 15%?
- Any correlated theme > 25%?
- High-volatility bucket > 30%? High-vol includes crypto, small-cap growth, unprofitable companies, and names with abnormally high recent daily / weekly volatility.
- Are short-term positions overheated, trading rich vs. fair, or facing imminent earnings / events?
- For losing positions: is this just a price pullback, or have fundamentals / news / earnings expectations actually deteriorated?
- Is cash sufficient to cover a 1–3 month potential drawdown and add-on opportunities?
- **Bucket misclassification**: any lot in the **Short Term** bucket held > 12 months? Either reclassify or exit.
- **Recent buying spree**: any ticker with 3+ new lots added in the last 30 days? Confirm the thesis still holds — concentration may be building.
- **Averaging up**: any ticker where the most recent lot's cost is > 1.1× the older weighted-average cost? Flag the chase risk explicitly.
- **Open cost-basis or date gaps**: list every lot still using `?` for cost or date — these block per-lot tooltips and pacing analysis.

If a check passes cleanly, say so explicitly in the report — do not silently omit.

## Visual design standard

Overall direction is **editorial × research-desk note**: warm-paper background, ink-black text, hairline rules, generous whitespace, hierarchy via typography rather than color blocks / shadows / heavy borders. **Not** a generic blue SaaS dashboard, **not** a dark-gradient hero card, **not** stacked saturated color blocks. Priorities: scan efficiency, number clarity, risk visibility.

### Design tokens (declare via `:root` variables)

Color tokens:

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

  /* Animation tints (low-alpha) */
  --pos-flash:    rgba(21,112,61,.18);
  --neg-flash:    rgba(180,35,24,.18);
}
```

Typography tokens (**must use system stacks — do not load any external font / Google Fonts**):

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

### Required typography settings

- `body` must enable `-webkit-font-smoothing:antialiased` and `text-rendering:optimizeLegibility`.
- Globally enable `font-feature-settings: "ss01", "cv11", "tnum" 1, "lnum" 1`. Numeric classes (`.num`, `.kpi .v`, `.bar-value`, numeric table cells) must additionally force `font-variant-numeric: tabular-nums lining-nums`.
- Heading weights live in **620–680**, **never above 720**. Body 400–500. KPI numbers 620. Labels / eyebrows 700.
- Large headings get `letter-spacing:-.012em` (tight). Small-caps eyebrows / table headers get `letter-spacing:.12em–.22em` and `text-transform:uppercase`.
- Line-height: body 1.62, heading 1.18, KPI numbers 1.1.

### Fluid font-size scale (HARD floors)

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

### Layout & component rules

- **Page container**: `max-width:1180px`, side padding 40px, top 56px, bottom 80px. Do not go to 1480px+ wide layouts.
- **Masthead (replaces hero card)**: newspaper-style — 3px black top rule, 1px hairline bottom rule. Contains: eyebrow (small-caps category), headline, dek subhead (≤ 780px wide), and a meta row (generated time, FX rate, data source, next event). **Do not** use dark gradient blocks, glow circles, or box-shadow.
- **Warning callout**: `--surface-2` background + 3px `--neg` left rule + a small `badge` chip. Bullet list may use 2-column `columns`, each item ≤ 1.5 lines. **Do not** use a saturated red wash.
- **KPI strip**: horizontal 4-column strip. 1px hairline top and bottom; 1px hairline between columns. Do not use individual cards with box-shadow and colored top bars. Each cell contains: small-caps label, big number, small delta line.
- **Section heading (`section-head`)**: `h2` on the left, small `sub` on the right (`--muted`), 1px hairline below. **Do not** add gradient bars or color rails before `h2`.
- **Charts**:
  - Donut: SVG `circle` with `stroke-dasharray`. Center shows total. Radius 42, stroke-width 20. Slice colors come from `--accent`, `--pos`, `--accent-warm`, `--info`, `--warn`. **No** neon-blue / cyan gradients.
  - Bar chart: track 6px tall, `#ebe7da` background, `border-radius:2px`. Bar uses solid color (default `--ink`; for signed values use `--pos` / `--neg` / `--warn` / `--info`). **No** 18px-thick bars with linear-gradient fills.
- **Table**: 1px `--ink` top and bottom rule. Row dividers 1px `--hairline`. Header is sticky (`position:sticky; top:0`) with opaque `var(--paper)` background, `z-index:var(--table-header-z)`, small-caps `--muted`, and a 1px bottom shadow/rule so scrolling body rows cannot cover it. Hover row uses `--surface-2`. Numeric cells `text-align:right` + tabular-nums. Ticker weight 680. Category chip uses thin-bordered `tag`.
- **Symbol cell trigger** (`div.sym-trigger[tabindex="0"][role="button"]`): inherits font from cell, no background, no border, padding 0, `cursor:help`, dotted underline on hover or focus. Looks like plain text until probed.
- **Price cell trigger**: same chrome-free styling. The cell wraps `price + .sub move` inside the trigger so the whole price block is hoverable and the popover anchors correctly.
- **Popover (`.pop`)**: `--surface` background, `--ink` text, padding 12–14px, border-radius 4px, `box-shadow:0 6px 20px rgba(15,25,31,.10), 0 1px 2px rgba(0,0,0,.04)` on desktop and a stronger bottom-sheet shadow on mobile. Desktop uses `width:max-content`, `min-width:min(300px, calc(100vw - 64px))`, and `max-width:min(560px, calc(100vw - 64px))`; do not use a narrow fixed width that causes avoidable wrapping. Tablet / phone uses fixed bottom-sheet placement, safe-area insets, high z-index, `max-height:min(72vh, calc(100dvh - 32px))`, internal scrolling, and long-text wrapping. Inner table uses 11.5px tabular numerics; desktop lot-table cells stay `white-space:nowrap`, while mobile/touch sheets restore normal wrapping.
- **Risk heatmap**: 5-column grid. Cells separated by 1px hairline (not gap). Each cell carries a 3px left risk rule (low / mid / high = light blue / amber / red). Cell contents: ticker, `Risk N/10`, `weight · move`. **Do not** flood the cell with saturated background color.
- **Action list**: 84px label column on the left (translated per SETTINGS), description on the right. Rows separated by dotted hairline.
- **Border-radius**: keep page-wide radius in **2–4px**. Only chips / badges may go to 3–4px; bar tracks 2px. Popovers may go to 4px. **Never** use radius ≥ 8px. **Never** use `border-radius:999px` (pill) on cards, bars, or tracks.
- **Shadow**: as a rule, no box-shadow on the page. Popovers are the single exception. Hover hints cap at `0 1px 0 rgba(0,0,0,.04)`. **Never** ship `0 10px 28px rgba(...)` floating shadows on regular content.
- **Separation hierarchy**: prefer hairline (1px) + whitespace; then semantic color; only then a faint background tint.

### Price-cell live styling

```css
.price-cell{transition:background .9s ease-out;}
.price-cell.flash-up   {background:var(--pos-flash);animation:flash-up   1.2s ease-out;}
.price-cell.flash-down {background:var(--neg-flash);animation:flash-down 1.2s ease-out;}
@keyframes flash-up   {0%{background:rgba(21,112,61,.32);} 100%{background:transparent;}}
@keyframes flash-down {0%{background:rgba(180,35,24,.32);} 100%{background:transparent;}}

.price-cell .price-num{transition:color .25s ease;}
.price-cell.flash-up   .price-num{color:var(--pos);}
.price-cell.flash-down .price-num{color:var(--neg);}

.pulse-dot{
  width:8px;height:8px;border-radius:50%;display:inline-block;
  background:var(--pos);opacity:.5;
}
.pulse-dot.beat{animation:beat 1s ease-out;}
@keyframes beat{0%{transform:scale(1);opacity:1;} 100%{transform:scale(1.6);opacity:0;}}

.live-ts{font-size:11px;color:var(--muted);margin-left:8px;font-variant-numeric:tabular-nums;}
.live-ts.stale{color:var(--warn);}
.live-ts.offline{color:var(--neg);}

@media (prefers-reduced-motion: reduce){
  .price-cell.flash-up,.price-cell.flash-down{animation:none;}
  .pulse-dot.beat{animation:none;opacity:.5;}
}
```

### Responsive / mobile (RWA)

The HTML must include a `<meta name="viewport" content="width=device-width, initial-scale=1">` and three breakpoint tiers. Treat phone behavior as a first-class concern — most quick re-checks happen on a phone.

| Tier | Range | What changes |
|---|---|---|
| Desktop | ≥ 881px | Default layout — all multi-column grids active, no horizontal scroll. Body 14.5–15.5px, table 13–13.5px |
| Tablet | 601–880px | KPI strip → 2 cols. `cols-2` / `cols-3` → 1 col. Donut + bars stack. Risk heatmap → 2 cols. Body 14–14.5px, table 13px. Bar-row label width tightens |
| Phone | ≤ 600px | KPI strip → 1 col. Risk heatmap → 1 col. Holdings table is wrapped in `.tbl-wrap` with horizontal scroll. **First column (Symbol) is `position:sticky; left:0; z-index:1` with a 1px shadow** so the user never loses row context while scrolling; **the header's first cell must override back to `z-index:calc(var(--table-header-z) + 1)` and `background:var(--paper)`** so it stays above row cells. **Body 14px floor, table 12.5px floor, sublines 11px floor — never lower.** Footer / legend density tightens. Action labels narrow to a 64px column |

Required wrappers and patterns:

- The holdings table is always wrapped in `.tbl-wrap`:
  ```html
  <div class="tbl-wrap"><table>…</table></div>
  ```
  Desktop `.tbl-wrap` must not set `overflow-x:auto`; otherwise browsers may clip descendant popovers. Enable `overflow-x:auto` and `-webkit-overflow-scrolling:touch` only at tablet / phone breakpoints, where popovers switch to fixed bottom sheets. Keep a negative left/right margin equal to the page's side padding and a `min-width` on the inner table (≥ 680px on phone, ≥ 760px on tablet) so the layout doesn't collapse into illegibility.
- Sticky first column on phone: applies to both `th:first-child` and `td:first-child`, with `background:var(--surface)` so cells don't bleed through during scroll, and a 1px right shadow (`box-shadow:1px 0 0 var(--hairline)`) as the affordance edge. Add a later `thead th:first-child{z-index:calc(var(--table-header-z) + 1);background:var(--paper)}` override because the generic first-column rule otherwise lowers the sticky header's z-index.
- KPI strip on phone: collapse to 1 column with row borders. Numeric value font respects the `clamp()` floor.
- All cells that use `border-right` or `border-left` for column-style separation must have those properties **reset** under the phone breakpoint to avoid orphan rules.
- Touch targets (popover triggers, links inside tables) must remain ≥ 30px tall on phone.
- Test the report at 360px width before shipping. Open in iOS Safari and Chrome Mobile. Verify the popovers position correctly and never clip outside the viewport.

### Anti-patterns (must avoid)

- Dark gradient hero (`linear-gradient(135deg,#0b1220,...)`).
- Heavy box-shadow (`0 10px 28px rgba(...)` or stronger) on regular content (popovers excepted).
- Saturated background washes (red / blue / green flooding a region).
- Heading weights ≥ 800.
- Pill border-radius (999px) on cards, bars, tracks.
- Multiple `<style>` blocks overriding each other. The new spec allows **one** `<style>` block, ordered: tokens → base → layout → components.
- Loading any external font (Google Fonts, `@font-face` over the network).
- Reintroducing IRR or annualized-return columns (see **Computations**).
- Bilingual or English-fallback labels in any cell, header, or button when SETTINGS specifies a non-English language (see **Output language**).
- Visible font sizes below the floors in the **Fluid font-size scale** table.

### Reference implementation

`reports/_sample_redesign.html` is the canonical reference. New reports must align color, typography, layout, and component styling with this file. If it is missing, rebuild from the tokens and rules above.

## Investment content standard

Voice and stance:

- Output language follows `SETTINGS.md` strictly (see **Output language**). Default tone: professional research note, not casual chat. Be concise, direct, and data-driven.
- Do not be reflexively conservative. The user can absorb large drawdowns; aggressive calls are welcome — but every aggressive call must be supported by data and a clear trigger.
- Do not mechanically recommend selling on a short-term dip — judge whether fundamentals have actually deteriorated.
- Do not chase strength blindly — check valuation, growth, catalysts, and how much expectation is already in the price.

Position handling:

- Read holdings dynamically from `HOLDINGS.md`. Do not hard-code positions.
- Long-term core, mid-term growth, and short-term positions must be judged separately. The same ticker, in different buckets, can warrant different actions.
- For high-growth, high-volatility names, frame the call across **bull / base / bear** scenarios.
- Recommendations must include action, price band, and trigger — for example: "hold", "trim 20%", "stop below $X", "add above $Y", "do not add into earnings". Translate the verbs.
- When recommending a trim, name the **specific lot(s)** to sell using the lot's acquisition date — e.g. "trim the 2025-09 KAPA lot first (highest cost basis)". Default ordering is highest cost basis first; deviate only with an explicit reason.
- Use hold period and per-lot P&L (visible in the Price popover) to interpret raw aggregate P&L — a +30% gain over 3 months is not the same story as +30% over 3 years. Reflect that in the action.
- Data gaps, estimates, and source conflicts must be flagged explicitly.

Today's action list (must produce, in this order — translate the labels):

- **Must do** — actions to execute today.
- **May do** — opportunistic actions if a price / event condition fires.
- **Avoid** — explicit don'ts for today.
- **Need data** — open data gaps that, if closed, would sharpen the call.

## Reply format to user

When replying, give absolute paths to both the HTML and the Markdown summary, plus a brief list of the most important alerts and data gaps. Do not ask the user to assemble, install, or run anything. Reply in the SETTINGS language.
