
### 9.0 Currency canonicalization — base-currency basis (HARD REQUIREMENT)

**Every numeric value rendered in the report is denominated in the configured base currency.** The base currency is chosen once via `SETTINGS.md`'s `Base currency:` line — default `USD` when the line is omitted. Whatever value is set there is the canonical unit for every aggregate: a 2330.TW lot bought at NT$2,300 and an NVDA lot bought at $185 must contribute to the same base-denominated `Σ` before any aggregation.

This is a structural rule, not a stylistic one — totals, weights, P&L ranking, theme/sector exposure, holding-period pacing aggregates all collapse incorrectly when source currencies are summed naïvely. Treat any aggregate cell rendered in a currency other than the configured base as a defect.

The remainder of this section uses **USD** in every example (the default base). When `SETTINGS.md` selects a different base currency, mentally substitute that code for `USD` everywhere below: prefixes (`$` → `NT$` for TWD, `¥` for JPY, etc.), FX dict keys (`USD/TWD` → `<BASE>/TWD`), and all aggregate units. The `scripts/generate_report.py` renderer handles the prefix and key swaps automatically once the SETTINGS line is set.

#### Where USD is mandatory (every aggregate, every chart axis)

- §10.1 #2 KPI strip: 總資產 / 投資部位 / 現金與類現金 / 已知損益 — all USD.
- §10.1 #3 Holdings table — `市值` (Value) column, `損益` (P&L) column, all weights — all USD-derived. The `最新價` (Price) column shows the **native trade currency** (e.g. `NT$2,300`, `£123.45`) because that is the user-facing market price; everything that aggregates *with* that price is USD.
- §10.4 P&L ranking bar chart, §10.1 #5 theme/sector exposure bars, §10.1 #8 risk heatmap weight rows, §10.1 #9 Recommended adjustments `目前` weight column — USD-derived.
- §10.4 Holding period & pacing — the cost-weighted aggregates use USD cost basis, even when the original lot was acquired in a non-USD currency.

#### Where the **native trade currency** is preserved (display only — never re-aggregated)

- Symbol popover: prose / metadata only, no native-currency math.
- **Price popover** lot-detail rows: each lot's `成本` (cost) shows the **original** acquisition currency with its prefix (`NT$2,300`, `¥3,150`, `£12.34`) so the user can recognize the trade as they entered it. The popover footer (`平均成本 / 總成本 / 總損益`) is rendered in **USD** with `$` prefix.
- The `最新價` cell in the Holdings table shows the live native price as quoted by the source (TWSE returns TWD, JPX returns JPY, etc.).
- **Sources & data gaps** audit row may quote raw native-currency feed values when explaining a fallback.
- Masthead meta row: list every active FX pair as `USD/TWD 32.5`, `USD/JPY 156.0`, etc.

#### Required FX inputs

The agent must supply USD-quoted rates for every non-USD currency in the book, via `SETTINGS.md` (or the editorial context JSON consumed by `scripts/generate_report.py`):

```jsonc
"fx": {
  "USD/TWD": 32.5,    // 1 USD = 32.5 TWD  → divide TWD amount by 32.5
  "USD/JPY": 156.0,
  "USD/HKD": 7.85,
  "USD/GBP": 0.78
}
```

If a non-USD currency appears in the book and no FX rate is configured, the agent **must** fetch a credible rate at generation time using §8 (yfinance `=X` symbols, ECB / central-bank reference, or any §8.5 fallback tier) and:

1. Add the rate to the working `fx` dict for the run.
2. Surface every fetched rate in the masthead meta row alongside any user-supplied rates.
3. Record the rate's source and `as_of` timestamp in **Sources & data gaps**.

**Never silently assume parity** (treating TWD or JPY as if it were USD). That produces multi-thousand-percent weight errors in the dashboard.

#### Conversion rules

| What | Conversion |
|---|---|
| Cash line in non-USD (`USD: 35600 [cash]`, `TWD: 1200000 [cash]`) | `USD_value = native_amount / FX(USD/native)`. The Price popover may show the original cash amount; the aggregate cash KPI is USD. |
| Latest price × quantity | `USD_market_value = latest_price × quantity × FX(trade_currency → USD)`. The trade currency is determined by the `[<MARKET>]` tag (`TW` → TWD, `JP` → JPY, `LSE` → GBP, `HK` → HKD, `US` / `crypto` / `FX` → USD). |
| Cost basis (per lot) | Same as price-side conversion. **Use the lot's acquisition-date FX rate** when the agent has it; otherwise fall back to the current rate and add a `cost_fx_approximation` note to the audit. The popover shows the per-lot original-currency cost as captured in `HOLDINGS.md`; the popover footer is USD-converted. |
| Per-holding P&L | `USD_pnl = USD_market_value − Σ_lots(USD_cost)`. FX-swing P&L is implicit in this calculation; the spec does not separately decompose it. |
| Move % / day move % | Pure ratios — no FX conversion needed. Stays in the native price's currency-relative terms. |

#### Self-check items (run as part of Appendix A.5)

- Every cell in the `市值` (Value) column starts with `$`.
- Every cell in the `損益` (P&L) column starts with `+$` / `−$` (or `—` for cash, `n/a` for missing cost).
- KPI strip's four big numbers all start with `$`.
- Price popover footer (`總成本 / 總損益`) starts with `$`.
- Price popover lot rows show **native currency** prefixes for `成本` (e.g. `NT$2,300` for a `[TW]` lot bought via `2330` at `NT$2300`).
- Masthead meta row enumerates every FX pair used; each pair has a value and an `as_of` (or `(SETTINGS)` if user-supplied).
- Source audit lists each FX rate's source for any rate not user-supplied.

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
5. Theme / sector exposure — **agent-authored, deterministic**. See **§10.4.2** for the full authoring contract: closed-list sectors, fixed-order theme master list, ETF look-through, bar color rules, bucket-note thresholds, and self-check items. The agent injects pre-rendered HTML via `context["theme_sector_html"]`. Following §10.4.2 produces identical output across runs given the same `HOLDINGS.md` + `prices.json`. If the field is missing, the section renders a placeholder — it is NOT computed automatically.
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

### 10.4.1 High-risk heatmap scoring rubric (HARD REQUIREMENT)

The heatmap must use a **stable deterministic rubric**, not free-form model judgment. Score every non-cash position on a **0–10** scale using the same factors every run:

| Factor | Rule | Points |
|---|---|---|
| Asset-class volatility | Crypto asset | `+3` |
| Bucket horizon | Mid Term | `+1` |
| Bucket horizon | Short Term | `+2` |
| Concentration | Weight ≥ 0.5 × single-name cap | `+1` |
| Concentration | Weight ≥ 1.0 × single-name cap | `+2` |
| Concentration | Weight ≥ 1.5 × single-name cap | `+3` |
| Price shock | `abs(move_pct)` ≥ single-day alert threshold | `+1` |
| Price shock | `abs(move_pct)` ≥ 1.5 × single-day alert threshold | `+2` |
| Quote quality | `price_freshness = delayed` | `+1` |
| Quote quality | `price_freshness = stale_after_exhaustive_search` or missing current quote | `+2` |

Rules:

- Cap the total score at `10`.
- Banding is fixed: `0–2 = low`, `3–5 = mid`, `6–10 = high`.
- Sort by `score desc`, then `weight desc`, then ticker.
- Show the rubric version in the section subtitle or eyebrow (for example `Stable rubric v1` / `固定規則 v1`) so the scoring standard remains explicit across runs.
- If no position has enough data to compute a score, render an explicit placeholder rather than leaving the grid blank.

### 10.4.2 Theme & Sector exposure — deterministic authoring contract (HARD REQUIREMENT)

The renderer does not classify holdings — the agent authors this section's HTML and injects it as `context["theme_sector_html"]`. To produce identical output across runs given the same `HOLDINGS.md` + `prices.json`, follow these rules **literally**, no free-form judgment.

#### A. Two parallel taxonomies (left + right column)

Render exactly two `.bars` lists side by side inside `<div class="cols-2">`:

| Column | Label (eyebrow) | Domain |
|---|---|---|
| Left | `主題` / `Themes` | Cross-cutting narrative buckets (e.g. AI 算力, 雲端 / 資料中心, 新能源 / 核能, 半導體設備, 加密資產, 防禦資產). May overlap — one ticker can belong to multiple themes |
| Right | `行業` / `Sectors` | Mutually exclusive primary industry per holding. Each ticker maps to exactly one sector |

Each column must be a `<div class="bars">` block with one `<div class="bar-row">` per bucket. Match the markup at `_sample_redesign.html` lines 1267-1300 exactly.

#### B. Sector taxonomy (closed list — pick from these only)

Sectors are deterministic. Map every non-cash, non-FX holding to **exactly one** of the following buckets using the issuer's most recent GICS or equivalent self-disclosure (Wikipedia / Reuters company page / 10-K / annual report):

`半導體` · `軟體 / 雲端` · `通信 / 光電` · `硬體 / 網通` · `汽車 / 電動車` · `能源 / 資源` · `航太 / 國防` · `金融` · `醫療 / 生技` · `消費` · `工業` · `公用事業` · `房地產` · `加密資產` · `多元 ETF / 指數` · `其他`

Rules:
- A holding's sector is its **primary** industry — never split a single stock across two sectors.
- Pure index ETFs (VWRA, QQQ, SPY, etc.) go to `多元 ETF / 指數`. Sector ETFs (XLF, SMH) go to the corresponding sector.
- Cash and FX positions are excluded from this column entirely (they have no sector).
- Tickers without a clear classification go to `其他`. Document the reason in **Sources & data gaps**.

#### C. Theme taxonomy (open list — derived per portfolio, but stable)

Themes are agent-derived but must be deterministic given the holdings. Apply this algorithm:

1. **Seed candidates** from a fixed master list: `AI 算力` · `雲端 / 資料中心` · `半導體設備` · `先進封裝` · `新能源 / 核能` · `光電 / OCS` · `航太 / 國防` · `加密資產` · `去美元化 / 黃金` · `防禦資產 / 現金代理` · `通膨保護` · `Mega-cap Tech`.
2. **Drop themes with zero exposure** (no holding maps to them this run).
3. **Merge near-duplicates** before rendering (e.g. `光電` ⊃ `OCS` if both apply to the same set of tickers). Document the merge rule once in the bucket-note.
4. **Cap the visible list at 7 buckets**. If more themes are non-zero, fold the smallest into `其他`.
5. **Theme order is fixed by the master list above**, then sorted by % within sequential clusters — meaning the same portfolio always produces the same theme order across runs.

A holding may belong to multiple themes. Compute a holding's contribution to a theme as `holding_weight_pct × theme_membership_share`, where `theme_membership_share ∈ {0, 0.25, 0.5, 0.75, 1.0}` is documented per ticker in the run's source-audit notes.

#### D. ETF look-through (mandatory)

Index ETFs (VWRA, QQQ, etc.) must be allocated through to their underlying sector / theme weights using the most recent published index composition (issuer fact sheet or index provider). Document the as-of date in the bucket-note. If the look-through data is unavailable for an ETF, allocate 100% of its weight to `多元 ETF / 指數` (sectors) and to the most-applicable single theme (themes) and flag in Sources & data gaps.

#### E. Bar color rules (HARD REQUIREMENT)

Each bar gets exactly **one** modifier class. Apply in this order — first match wins:

| Class | Trigger | Meaning |
|---|---|---|
| `bar warn` | `pct >= theme_concentration_warn` (default 25%, see SETTINGS.md) **OR** any bucket in the top-3 with `pct >= 12.5%` | Concentration alert |
| `bar info` | The bucket cuts across multiple sectors AND `pct >= 7.5%` (themes column only — sectors never use `info`) | Cross-cutting / notable |
| `bar pos` | Reserved for explicit "thesis-aligned" callouts (rare) | Used only when noted in editorial commentary |
| `bar neg` | Reserved for explicit "thesis-broken" callouts (rare) | Used only when noted in editorial commentary |
| (no modifier) | Everything else | Default |

#### F. Sort, precision, bar widths

- Within each column, sort by `pct desc` (themes obey the master-list cluster order from C.5 first, then `pct desc` inside each cluster).
- Weights to **1 decimal place**.
- Bar width is **relative to the largest bucket in the same column** — the largest renders at `100%`, others scale proportionally. This matches the holdings-weight chart in `§10.4 #2` and the sample's lines 1277-1294.

#### G. Bucket-note callouts (concentration warnings)

Render a `<div class="bucket-note" style="margin-top:18px">` immediately after the `cols-2` block when **any** of these fire:

- **Top-3 correlated themes** sum > `theme_concentration_warn` (default 30%) → `<b>集中度警示：</b>{theme_a} {pct}% ＋ {theme_b} {pct}% ＋ {theme_c} {pct}% ＝ <b>{sum}%</b>，超過 {threshold}% 相關性主題上限。`
- **Single sector** > `sector_concentration_warn` (default 30%, separate from theme threshold) → `<b>行業集中：</b>{sector} 佔 {pct}%，超過 {threshold}% 單一行業上限。`
- **ETF look-through fallback** used → `<b>ETF 穿透不可得：</b>{ticker} ({pct}%) 暫以「多元 ETF / 指數」整塊計入；待補底層權重後重算。`

If multiple conditions fire, render multiple `bucket-note` divs back-to-back. If none fire, omit the note entirely.

#### H. Self-check (per run, before generating the report)

The agent must verify:

1. Sectors sum to **exactly 100%** (cash/FX excluded).
2. Every non-cash, non-FX ticker appears in **exactly one** sector.
3. Top theme `pct` ≤ 100%.
4. Visible theme count ≤ 7.
5. Bar order matches the rules in F.
6. Bar colors match the order rules in E.
7. Bucket-notes follow G's exact wording template (token-for-token).

A failure on any of items 1-3 is a hard error — fix the classification, do not generate the report. Items 4-7 are softer (the report still renders) but should be flagged in **Sources & data gaps**.

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

- First delegate latest-price retrieval to the market-native primary source: `yfinance` for listed securities / FX, Binance / CoinGecko-first routing for crypto (§8.2, §8.3).
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
