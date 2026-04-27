# Portfolio Report Output Guidelines

For future agents: the portfolio report in this repo is the *final deliverable*, not a frontend project. Do not break the user-facing report into multiple executable scripts or external resources.

This spec is the single source of truth for any "portfolio health check" / "pre-market battle report" run. When invoked, follow it end-to-end.

## When this spec applies

- Trigger phrases: "portfolio health check", "pre-market battle report", "run my portfolio report", or any explicit request for a portfolio risk / exposure / action report.
- Default framing: **Portfolio report**. Even if the agent is executed mid-day or after-hours, still produce the full analysis and write the local files. Do not skip sections because the market is closed.

## File output

- Both files must be written to `reports/`.
- HTML filename: `YYYY-MM-DD_HHMM_portfolio_report.html`
- Markdown summary filename: `YYYY-MM-DD_HHMM_portfolio_report.md`
- Use the local clock at execution time for the timestamp prefix; both files share the same prefix.

## Hard rules

- The HTML must be a single self-contained file directly openable in the browser: all CSS, charts, data, and any required interactive logic must be inlined in the same HTML.
- Do not leave external generator scripts, external JavaScript, external CSS, CDN dependencies, build artifacts, or frontend project structure in the repo.
- If you need a temporary script to wrangle data, keep it in `/tmp` or use it once. Do not check it in as a deliverable.
- The final delivery should contain only the requested HTML, the Markdown summary, and any necessary updates to the spec docs.
- The HTML must not depend on local relative paths, `file://` images, external fonts, external chart libraries, or any service that requires login or payment.
- External URLs are allowed *only* as data-source citations, never as runtime style, script, or chart dependencies.
- If a value cannot be retrieved, mark it explicitly as `data gap` — do not fill in by guesswork. If a value is derived (e.g. a P&L computed off your own cost basis), it is fine; if it is a guess at a market data point you could not source, it is a data gap.

## HTML self-containment check

After producing the report, verify the HTML:

- No `<script src=...>`.
- No `<link rel="stylesheet"...>`.
- No `<script>` or `<link>` that pulls a chart library from a CDN.
- Inline `<style>`, inline SVG, inline tables, and inline data are allowed.
- If you must use `<script>`, it must be inline-only and used only when interactivity is genuinely required by the user; for static reports prefer SVG / CSS over JavaScript.

Suggested check:

```sh
rg -n "<script\\s+src=|<link[^>]+stylesheet|src=|href=.*\\.css" reports/*.html
```

For each hit, confirm it is purely a citation link; if it is anything else, inline it.

## Data freshness

- Always search the web for the latest market data. Never rely on stale model memory.
- Each holding must be refreshed for: latest price, pre / after-market price, day and recent move, market cap, valuation multiples (PE, Forward PE, PS, EV/EBITDA where relevant), volume, next earnings date, and any imminent material event.
- Source priority: company IR, SEC / exchange filings, official press releases, then StockAnalysis, Nasdaq, Yahoo Finance, Reuters, CNBC, MarketWatch; for crypto, CoinMarketCap and CoinGecko.
- If a credible source cannot be found, mark the field `data gap`. If a number is your own derivation, label it `estimate`. Never silently guess.

## Reading inputs

- Auto-read all positions from `HOLDINGS.md` at run time. Do not hard-code holdings, do not assume any specific ticker is present, and re-classify on every run.
- Auto-classify each holding by asset class, sector, and theme based on current data. Buckets are not fixed — examples include ETF, single stock, crypto, cash, semiconductor, AI, energy, aerospace, financials, healthcare, consumer, industrial, optical / data center, defense, other. Use whatever fits the actual book.
- Read `SETTINGS.md` for output language, tone, and (if present) position-sizing rails. Settings rails override the defaults in this spec when in conflict.

### Lot format

Every lot in `HOLDINGS.md` follows:

```
<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD>
```

- `on YYYY-MM-DD` is the **acquisition date** for that lot. It enables hold-period and IRR computation.
- Crypto / FX use `<SYMBOL> <quantity> @ <cost> on <YYYY-MM-DD>` (no "shares").
- `?` is allowed in place of cost or date when truly unknown — treat the affected metric as a `data gap`. Never invent a value.
- A ticker may have multiple lots across the four buckets (Long Term, Mid Term, Short Term, Cash Holdings). Aggregate per ticker for the holdings table; keep lot detail available for IRR, hold period, and trim recommendations.

## Computations the report must produce

- Total assets, invested position, cash & cash-equivalent value, cash ratio.
- Per-holding weight (% of total assets), theme weight, sector weight.
- Per-holding P&L using the cost basis in `HOLDINGS.md`. For lots with `?` cost, mark P&L as data gap.
- For each holding, the freshness fields listed under **Data freshness**.
- **Hold period (per ticker)** = duration since the *oldest* lot's acquisition date. Display in `Xy Ym` for ≥ 1 year, otherwise `Nm` or `Nd`. If any lot has a `?` date, show the hold period as `data gap`.
- **Annualized return (IRR, per ticker)** = `(market_value / total_cost) ^ (365 / weighted_avg_days_held) − 1`, where `weighted_avg_days_held` is the cost-weighted average of each lot's days held.
  - Only compute IRR when **every** lot for the ticker has both cost and date. Otherwise mark `data gap`.
  - **Suppress** annualization (show `— recent`) when `weighted_avg_days_held < 90`. The raw P&L stays visible; just do not annualize a tiny window.
- **Book-wide pacing aggregates**:
  - Cost-weighted average hold period across all risk assets (ex-cash).
  - Oldest lot in the book (ticker + date + duration).
  - Newest lot in the book (ticker + date + duration).
  - % of risk-asset value held > 1 year.
  - Distribution of risk-asset value across the buckets `< 1m`, `1–6m`, `6–12m`, `1–3y`, `3y+`.

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

The holdings table in section 3 uses these columns, left to right:

1. **Symbol** — ticker (weight 680) + company subline (`--muted`).
2. **Category** — asset class plus a single tag chip (`High vol`, `Theme A`, `Rich val`, `Overheated`, `High risk`, etc.).
3. **Price** (num) — latest quote.
4. **Weight** (num) — % of total assets.
5. **Value** (num) — current market value.
6. **P&L · IRR** (num) — `±$X / ±Y%` on the headline line; IRR (or `— recent` / `data gap`) on a smaller `.irr` subline directly below.
7. **Held** (num, `.held` cell) — `Xy Ym` (or `Nm` / `Nd`) on the headline; `since YYYY-MM · N lots` on a smaller `.lots` subline.
8. **Action** — recommendation with action verb, price band, and trigger.

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
- Each news item must include date, source name, link, and impact tag — `positive` / `neutral` / `negative`.
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
- **Open cost-basis or date gaps**: list every lot still using `?` for cost or date — these block IRR and pacing analysis.

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

Required typography settings:

- `body` must enable `-webkit-font-smoothing:antialiased` and `text-rendering:optimizeLegibility`.
- Globally enable `font-feature-settings: "ss01", "cv11", "tnum" 1, "lnum" 1`. Numeric classes (`.num`, `.kpi .v`, `.bar-value`, numeric table cells) must additionally force `font-variant-numeric: tabular-nums lining-nums`.
- Heading weights live in **620–680**, **never above 720**. Body 400–500. KPI numbers 620. Labels / eyebrows 700.
- Large headings get `letter-spacing:-.012em` (tight). Small-caps eyebrows / table headers get `letter-spacing:.12em–.22em` and `text-transform:uppercase`.
- Line-height: body 1.62, heading 1.18, KPI numbers 1.1.
- Base font size 14.5px. Do not shrink the whole page to 12–13px.

### Layout & component rules

- **Page container**: `max-width:1180px`, side padding 40px, top 56px, bottom 80px. Do not go to 1480px+ wide layouts.
- **Masthead (replaces hero card)**: newspaper-style — 3px black top rule, 1px hairline bottom rule. Contains: eyebrow (small-caps category), headline, dek subhead (≤ 780px wide), and a meta row (generated time, FX rate, data source, next event). **Do not** use dark gradient blocks, glow circles, or box-shadow.
- **Warning callout**: `--surface-2` background + 3px `--neg` left rule + a small `badge` chip. Bullet list may use 2-column `columns`, each item ≤ 1.5 lines. **Do not** use a saturated red wash.
- **KPI strip**: horizontal 4-column strip. 1px hairline top and bottom; 1px hairline between columns. Do not use individual cards with box-shadow and colored top bars. Each cell contains: small-caps label, big number, small delta line.
- **Section heading (`section-head`)**: `h2` on the left (18px, weight 650), small `sub` on the right (12.5px, `--muted`), 1px hairline below. **Do not** add gradient bars or color rails before `h2`.
- **Charts**:
  - Donut: SVG `circle` with `stroke-dasharray`. Center shows total. Radius 42, stroke-width 20. Slice colors come from `--accent`, `--pos`, `--accent-warm`, `--info`, `--warn`. **No** neon-blue / cyan gradients.
  - Bar chart: track 6px tall, `#ebe7da` background, `border-radius:2px`. Bar uses solid color (default `--ink`; for signed values use `--pos` / `--neg` / `--warn` / `--info`). **No** 18px-thick bars with linear-gradient fills.
- **Table**: 1px `--ink` top and bottom rule. Row dividers 1px `--hairline`. Header is small-caps 11px `--muted` with no background. Hover row uses `--surface-2`. Numeric cells `text-align:right` + tabular-nums. Ticker weight 680. Subline 11.5px `--muted`. Category chip uses thin-bordered `tag` (default gray, `.pos` green, `.neg` red, `.warn` amber).
- **Risk heatmap**: 5-column grid. Cells separated by 1px hairline (not gap). Each cell carries a 3px left risk rule (low / mid / high = light blue / amber / red). Cell contents: ticker, `Risk N/10`, `weight · move`. **Do not** flood the cell with saturated background color.
- **Action list**: 84px label column on the left (Must / May / Avoid / Need data — small caps, semantic colors), description on the right. Rows separated by dotted hairline.
- **Border-radius**: keep page-wide radius in **2–4px**. Only chips / badges may go to 3–4px; bar tracks 2px. **Never** use radius ≥ 8px. **Never** use `border-radius:999px` (pill) on cards, bars, or tracks.
- **Shadow**: as a rule, no box-shadow on the page. If a hover hint is needed, cap it at `0 1px 0 rgba(0,0,0,.04)`. **Never** ship `0 10px 28px rgba(...)` floating shadows.
- **Separation hierarchy**: prefer hairline (1px) + whitespace; then semantic color; only then a faint background tint.

### Anti-patterns (must avoid)

- Dark gradient hero (`linear-gradient(135deg,#0b1220,...)`).
- Heavy box-shadow (`0 10px 28px rgba(...)` or stronger).
- Saturated background washes (red / blue / green flooding a region).
- Heading weights ≥ 800.
- Pill border-radius (999px) on cards, bars, tracks.
- Multiple `<style>` blocks overriding each other. The new spec allows **one** `<style>` block, ordered: tokens → base → layout → components.
- Loading any external font (Google Fonts, `@font-face` over the network).

### Reference implementation

`reports/_sample_redesign.html` is the canonical reference. New reports must align color, typography, layout, and component styling with this file. If it is missing, rebuild from the tokens and rules above.

## Investment content standard

Voice and stance:

- Output language follows `SETTINGS.md`. Default tone: professional research note, not casual chat. Be concise, direct, and data-driven.
- Do not be reflexively conservative. The user can absorb large drawdowns; aggressive calls are welcome — but every aggressive call must be supported by data and a clear trigger.
- Do not mechanically recommend selling on a short-term dip — judge whether fundamentals have actually deteriorated.
- Do not chase strength blindly — check valuation, growth, catalysts, and how much expectation is already in the price.

Position handling:

- Read holdings dynamically from `HOLDINGS.md`. Do not hard-code positions.
- Long-term core, mid-term growth, and short-term positions must be judged separately. The same ticker, in different buckets, can warrant different actions.
- For high-growth, high-volatility names, frame the call across **bull / base / bear** scenarios.
- Recommendations must include action, price band, and trigger — for example: "hold", "trim 20%", "stop below $X", "add above $Y", "do not add into earnings".
- When recommending a trim, name the **specific lot(s)** to sell using the lot's acquisition date — e.g. "trim the 2098-09 KAPA lot first (highest cost basis)". Default ordering is highest cost basis first; deviate only with an explicit reason.
- Use IRR and hold period to interpret raw P&L — a +30% gain over 3 months is not the same story as +30% over 3 years. Reflect that in the action.
- Data gaps, estimates, and source conflicts must be flagged explicitly.

Today's action list (must produce, in this order):

- **Must do** — actions to execute today.
- **May do** — opportunistic actions if a price / event condition fires.
- **Avoid** — explicit don'ts for today.
- **Need data** — open data gaps that, if closed, would sharpen the call.

## Reply format to user

When replying, give absolute paths to both the HTML and the Markdown summary, plus a brief list of the most important alerts and data gaps. Do not ask the user to assemble, install, or run anything.
