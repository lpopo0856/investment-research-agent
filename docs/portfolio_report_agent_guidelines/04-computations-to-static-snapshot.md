## 9. Computations & missing-value glyphs

### 9.0 Currency canonicalization — base-currency basis (HARD)

Base currency = `SETTINGS.md` `Base currency:`; default `USD`. Every aggregate/chart axis is base-denominated; native trade currency is display-only. No manual FX in `SETTINGS.md` or `report_context.json`. `scripts/fetch_prices.py` populates `prices.json["_fx"]`.

| Surface | Currency rule |
|---|---|
| Base required | KPI strip; holdings `Value` / `P&L` / weights; P&L ranking; theme/sector exposure; risk heatmap weights; recommended-adjustment current weight; hold-period cost-weighted aggregates; Price popover footer. |
| Native allowed only | Holdings `Price`; Price popover lot `成本`; cash-line popover; Sources/data-gaps raw feed explanation; masthead FX meta. |
| FX JSON | `{"base":"USD","rates":{"USD/TWD":32.5},"details":{...source/as_of/fallback...}}`; non-base currencies require fetched pair + source/as_of/fallback audit. Missing pair → affected aggregate `n/a`. Never parity-assume. |

| What | Conversion |
|---|---|
| Non-base cash | `base_value = native_amount / FX(base/native)`. |
| Latest price × qty | `base_market_value = latest_price × qty × FX(trade_currency→base)`; trade currency from quote metadata, then `[MARKET]` fallback (`TW` TWD, `JP` JPY, `LSE` GBP unless verified otherwise, `HK` HKD, `US`/crypto/FX USD). |
| Cost basis | Use acquisition-date FX when available; else current FX + `cost_fx_approximation` audit note. Popover row keeps original native cost; footer base-converted. |
| P&L | `base_pnl = base_market_value − Σ_lots(base_cost)`; FX swing implicit. |
| Move % | Ratio only; no FX conversion. |

Appendix A.5 checks: base prefix on `Value`, `P&L`, KPIs, popover footer; native prefixes only in allowed surfaces; masthead lists all FX pairs + as_of; source audit lists each FX source/fallback.

### 9.1 Required metrics

- Total assets, invested value, cash/cash-equivalent value, cash ratio.
- Per-holding weight (% total assets), theme weight, sector weight.
- Per-holding P&L from `HOLDINGS.md`; cost `?` → P&L `n/a`.
- Per-lot P&L for Price popover: `(latest_price − lot_cost) × lot_qty`; skip `?` cost.
- Per-ticker weighted-average cost over known-cost lots.
- Per-ticker §8.8 freshness fields.

### 9.2 Hold period

Per ticker = oldest lot acquisition date. Format `Xy Ym` if ≥1y, else `Nm` / `Nd`; any `?` date → `n/a`.

### 9.3 Latest price & move

Latest price = newest credible generation-time value passing §8.7. Record `price_source`, `price_as_of`, `price_freshness`, `market_state_basis`; no session-state badges; unresolved after exhaustive source walk → price `n/a`. Move % / 24h move derives from chosen latest + prior close/24h ref; missing move renders subline `n/a`, not price `n/a`.

### 9.4 IRR forbidden

No IRR / annualized-return columns. Use hold period + per-lot P&L.

### 9.5 Book-wide pacing aggregates

Surface in §10.3: cost-weighted avg hold ex-cash; oldest lot ticker/date/duration; newest lot ticker/date/duration; % risk-asset value held >1y; bucket distribution `<1m`, `1–6m`, `6–12m`, `1–3y`, `3y+`.

### 9.6 Missing-value glyphs

| Glyph | Meaning | Use |
|---|---|---|
| `—` | Not applicable; metric structurally meaningless. | Cash / cash-equivalent P&L; any structurally undefined row+column. |
| `n/a` | Missing; metric should exist but input/source missing. | Cost/date `?`; unresolved market data; missing FX pair. |

Cell-level only. Never blank cells; never write "missing/unknown/data gap" inside cells. Sources & data gaps enumerates every `n/a` reason and `HOLDINGS.md` line or URL needed.

---

## 10. Required report sections

### 10.1 HTML section order

1. Today's summary
2. Portfolio dashboard (KPIs)
3. Holdings P&L and weights table (§10.2)
4. Holding period & pacing (§10.3)
5. Theme / sector exposure: agent-authored deterministic HTML in `context["theme_sector_html"]`; renderer placeholder if missing; not auto-classified by renderer.
6. Latest material news
7. Forward 30-day event calendar
8. High-risk and high-opportunity list
9. Recommended adjustments
10. Today's action list (translated buckets per §15.3)
11. Sources and data gaps

HTML is sole deliverable; no companion Markdown/files.

### 10.2 Holdings table columns

Visible cells stay short; details live in Symbol/Price popovers.

| # | Column | Rule |
|---|---|---|
| 1 | Symbol | Ticker only, weight 680, monospace-friendly. No company/since/lot subline; those live in Symbol popover. |
| 2 | Category | Asset class + one translated tag chip (`High vol`, `Long`, `Mid`, `Short`, `Rich val`, `Overheated`, `High risk`, `Cash`, etc.). |
| 3 | Price | Static latest price, large; day/24h move subline if available; whole cell is popover trigger; no runtime refresh/session badge. |
| 4 | Weight | % of total assets. |
| 5 | Value | Current market value, base-currency basis. |
| 6 | P&L | `±<base-prefix>X / ±Y%`; cash `—`; missing cost `n/a`; lot detail in Price popover. |
| 7 | Action | Recommendation with verb, price band, trigger. |

Removed columns: `Held`, `Move`. Hold period appears in Symbol popover and §10.3.

### 10.3 Holding period & pacing block

Must contain: 4 KPI cells (Avg hold cost-weighted; Oldest lot ticker+date+duration; Newest lot ticker+date+duration; % risk assets >1y); `period-strip` with `<1m`, `1–6m`, `6–12m`, `1–3y`, `3y+` + legend; zero+ `bucket-note` callouts for Short Term >12m, 3+ adds in 30d, latest add >1.1× older avg cost, open cost/date gaps.

### 10.4 Required charts (inline SVG/CSS only)

Asset allocation donut; holdings weight bars; P&L ranking bars; sector/theme exposure bars; hold-duration strip; 30-day event timeline; high-risk heatmap; cash vs risk-asset ratio bar. Each has title, readable labels, tabular numerals. No external chart libraries.

### 10.4.1 High-risk heatmap rubric (HARD)

Score every non-cash holding 0-10, cap at 10, band `0–2 low`, `3–5 mid`, `6–10 high`; sort `score desc`, `weight desc`, ticker; show rubric version (`Stable rubric v1` / translated). Placeholder if insufficient data.

| Factor | Rule | Pts |
|---|---|---|
| Asset class | Crypto | +3 |
| Bucket | Mid Term / Short Term | +1 / +2 |
| Concentration | Weight ≥0.5× / 1.0× / 1.5× single-name cap | +1 / +2 / +3 |
| Price shock | `abs(move_pct)` ≥ alert threshold / ≥1.5× threshold | +1 / +2 |
| Quote quality | `price_freshness=delayed` / `stale_after_exhaustive_search` or missing current quote | +1 / +2 |

### 10.4.2 Theme & Sector exposure contract (HARD)

Renderer does not classify. Agent injects exact `<div class="cols-2">` with two `.bars` lists; each bucket row is `.bar-row` matching `_sample_redesign.html` lines 1267-1300.

| Column | Label | Domain |
|---|---|---|
| Left | `主題` / translated `Themes` | Cross-cutting; holdings may map to multiple themes. |
| Right | `行業` / translated `Sectors` | Mutually exclusive; each non-cash/non-FX holding maps to exactly one sector. |

Sector closed list, choose from issuer GICS/equivalent disclosure (Wikipedia / Reuters / 10-K / annual report): `半導體`, `軟體 / 雲端`, `通信 / 光電`, `硬體 / 網通`, `汽車 / 電動車`, `能源 / 資源`, `航太 / 國防`, `金融`, `醫療 / 生技`, `消費`, `工業`, `公用事業`, `房地產`, `加密資產`, `多元 ETF / 指數`, `其他`. Pure index ETFs → `多元 ETF / 指數`; sector ETFs → matching sector; cash/FX excluded; unclear → `其他` + Sources gap.

Theme algorithm: seed fixed master list `AI 算力`, `雲端 / 資料中心`, `半導體設備`, `先進封裝`, `新能源 / 核能`, `光電 / OCS`, `航太 / 國防`, `加密資產`, `去美元化 / 黃金`, `防禦資產 / 現金代理`, `通膨保護`, `Mega-cap Tech`; drop zero; merge near-duplicates (document once in bucket-note); visible ≤7 buckets, fold smallest into `其他`; order by master-list clusters then `pct desc`. Theme contribution = `holding_weight_pct × theme_membership_share`, share ∈ `{0,0.25,0.5,0.75,1.0}`, documented per ticker in source audit.

ETF look-through mandatory for index ETFs using latest issuer/index composition; document as-of. If unavailable: sectors 100% `多元 ETF / 指數`; themes most-applicable single theme; flag Sources gap.

Bar class first-match wins:

| Class | Trigger |
|---|---|
| `bar warn` | `pct >= theme_concentration_warn` default 25% OR any top-3 bucket `pct >= 12.5%`. |
| `bar info` | Themes only: bucket cuts across multiple sectors and `pct >= 7.5%`. |
| `bar pos` | Rare explicit thesis-aligned editorial callout. |
| `bar neg` | Rare explicit thesis-broken editorial callout. |
| none | Default. |

Sort each column by `pct desc` (themes observe master clusters first); precision 1 decimal; bar width relative to largest bucket in same column.

Bucket-note callouts immediately after `cols-2`, multiple allowed, omit if none:

- Top-3 correlated themes sum > `theme_concentration_warn` default 30% → `<b>集中度警示：</b>{theme_a} {pct}% ＋ {theme_b} {pct}% ＋ {theme_c} {pct}% ＝ <b>{sum}%</b>，超過 {threshold}% 相關性主題上限。`
- Single sector > `sector_concentration_warn` default 30% → `<b>行業集中：</b>{sector} 佔 {pct}%，超過 {threshold}% 單一行業上限。`
- ETF fallback → `<b>ETF 穿透不可得：</b>{ticker} ({pct}%) 暫以「多元 ETF / 指數」整塊計入；待補底層權重後重算。`

Self-check: sectors sum exactly 100% cash/FX excluded; every non-cash/non-FX ticker exactly one sector; top theme ≤100%; visible themes ≤7; order/color rules followed; bucket-note wording token-for-token. Items 1-3 hard fail; 4-7 flag in Sources if imperfect.

### 10.5 News & event coverage (HARD; agent owns web)

Renderer only formats `context["news"]` / `context["events"]`; `scripts/fetch_prices.py` is prices only. Empty news/events without search audit is violation.

Workflow:

1. Cover universe = every `HOLDINGS.md` position except cash/pure cash-equivalents, de-duped, plus extra tickers surfaced in §10.6/§10.9.
2. Per ticker run ≥1 WebSearch: `"<ticker> <company name>" earnings OR guidance OR downgrade OR upgrade OR catalyst <YYYY-MM>` using current and previous report month. TW also query 繁中: `"<code> <公司名>" 法說 OR 營收 OR 財報 OR 重大訊息`. Fetch/read promising URLs; no SERP-only items.
3. Collect 1-3 material 14-calendar-day items per ticker; older only if thesis-relevant/follow-up. Material = earnings/guidance/M&A/regulator/customer/product/analyst action/capital raise/lawsuit/supply-chain. Skip routine target nudges, recap-only, sponsored. Zero material → audit `news_search:<ticker>:no_material_within_14d` or extended-window reason.
4. Per ticker identify 30-day dated catalysts from issuer IR, exchange filing/calendar, Yahoo, Nasdaq, MarketWatch, TWSE/TPEx. Verify dates on issuer/exchange/official source; unverifiable → `date:TBD` + tried source in data gaps.
5. Macro events (FOMC/CPI/PCE/NFP/BoJ/ECB/NBS) from official central bank/statistics calendars only.

Records:

- News: `ticker`, ISO `date`, `source`, resolving `url` actually read, `headline`, `impact ∈ {pos,neu,neg}`.
- Events: `date`, `topic`, `event`, `impact_label`, `impact_class ∈ {warn,info,pos,neg}`, `watch`; hedge `(待…公告)` only after issuer page tried and missing.

Prioritise into §10.6/§10.8/§10.9/§10.10 by materiality, not weight. Materiality drivers: regulator/legal/going-concern, guidance cut/preannouncement, M&A/take-private/spin, major customer win/loss, approval/recall, dilution, debt maturity/covenant, insider anomaly, halt, peer datapoint. Weight is tie-breaker only.

Render gate: every cover-universe ticker has ≥1 news item or explicit `news_search` audit, and ≥1 30-day dated catalyst or explicit `event_search:<ticker>:no_dated_catalyst_within_30d`. No model-memory catalyst dates. If search missing, recommendation degrades to `Need data`. Every holding must either get evidence-backed §10.9/§10.10 recommendation, explicit `hold — no material news in search window` + audit, or `Need data`.

#### 10.5.1 Final reply audit

Reply must name searched tickers and material-item count per ticker, including zero-count tickers.

### 10.6 High-priority alerts

Render top alert block if any: single asset >20%; correlated theme >30%; high-vol bucket >30%; short-term position one-day move >8%; earnings within 7d and weight >5%; below 50dma plus negative news; price >20% above analyst consensus target; material negative news/guidance/regulatory/liquidity/dilution/debt risk regardless of weight; any §10.9 recommendation that breaches a SETTINGS rail and uses §15.6 path (c) conviction-reduced escalation.

---

## 11. Per-run special checks

Explicitly answer all 10; clean pass still stated: single asset >15%; correlated theme >25%; high-vol bucket >30% (crypto, small-cap growth, unprofitable, abnormal vol); short-term overheated/rich/imminent event; losing positions price pullback vs fundamental/news/estimate deterioration; cash enough for 1-3m drawdown/adds; Short Term lot held >12m; ticker with 3+ new lots in 30d; latest lot cost >1.1× older weighted-average cost; any cost/date `?` gaps.

---

## 12. Static latest-price snapshot rules

Price column is generation-time static; no runtime refresh.

### 12.1 Generation-time retrieval

Delegate first to §8 market-native order: Stooq listed + Yahoo currency verify → yfinance listed secondary; yfinance FX primary; Binance/CoinGecko crypto. Run §8.4 only for yfinance non-rate-limit failures. Use keyed APIs only after native pair fails. Use agent web pages before remaining no-token endpoints. Apply §8.7 to every candidate; opened markets require same-date latest/close until hierarchy exhausted; pre-open requires previous opened trading-day close minimum. Degraded delayed/EOD only after exhaustion and audit. Store §8.8 fields; HTML embeds static fields only.

### 12.2 Display

Price cell = large latest price + translated signed move subline (e.g. `較前收 +1.40%`, `24h +2.10%`). Price popover includes latest, source, timestamp/freshness, market-state basis, currency/exchange, per-lot P&L table. Do not show session-state chips, refresh UI, update animations, stale/offline badges.

### 12.3 Source audit

List provider for every holding; mark delayed/EOD/fallback; for degraded/`n/a` list attempted source categories and why no freshness-valid value; for yfinance failures list reason + up to 3 auto-corrections before fallback.
