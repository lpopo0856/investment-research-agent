## 9. Computations & missing-value glyphs

> **Pipeline note (HARD).** Every numeric / structural field below is computed
> by `scripts/portfolio_snapshot.py` (orchestrated by
> `python scripts/transactions.py snapshot`) and serialized into
> `report_snapshot.json`. The renderer (`scripts/generate_report.py`) reads
> the snapshot and projects it onto HTML — it does not aggregate, FX-convert,
> compute pacing, score risk, or run §11 checks itself. Authoring agents
> inspect the snapshot to see the prepared numbers before drafting editorial
> context; the renderer never re-derives them.
>
> **Token discipline (HARD; per `docs/context_drop_protocol.md`).** Authoring
> agents read `report_snapshot.json` and `report_context.json` **field-narrow
> via `jq`**, never whole-file. Examples: `jq '.profit_panel'`,
> `jq '.transaction_analytics.discipline_check.top_position_weights'`,
> `jq '.aggregates | keys'`. The full files routinely exceed 8K–25K tokens
> each; whole-file Reads load that into the parent agent's context for the
> rest of the session, with no editorial benefit (the renderer reads the
> files from disk and that path is unchanged). `transactions.py snapshot` /
> `analytics` / `pnl` are the canonical compact views — `db dump` is for
> backup, not for "give me transaction context."

**Path convention (HARD):** Unqualified filenames `report_snapshot.json`, `report_context.json`, and `prices.json` in this part file refer to those **basenames inside** `$REPORT_RUN_DIR` under `/tmp` for a normal report run (see `/docs/portfolio_report_agent_guidelines.md` — Intermediate files). Do not write these artifacts to the repository root.

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
- Per-holding P&L from `transactions.db.open_lots`; cost `?` → P&L `n/a`.
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

Cell-level only. Never blank cells; never write "missing/unknown/data gap" inside cells. Sources & data gaps enumerates every `n/a` reason and `transactions.db` row id or URL needed.

---

## 10. Required report sections

### 10.1 HTML section order

1. Today's summary
2. Portfolio dashboard (KPIs)
2.5. **Profit panel (§10.1.5)** — period P&L for 1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME. The numbers are produced upstream by `python scripts/transactions.py snapshot` (which calls `compute_profit_panel`) and embedded in `report_snapshot.json["profit_panel"]`. The renderer falls back to the snapshot value; `context["profit_panel"]` exists only as an explicit debugging override. The standalone `scripts/transactions.py profit-panel` subcommand is still available for one-off inspection.

2.6. **Transaction analytics (§10.1.6)** — performance attribution, trade quality, discipline check. Produced upstream by `python scripts/transactions.py snapshot` (which calls `compute_transaction_analytics`) and embedded in `report_snapshot.json["transaction_analytics"]`. The renderer reads `context["transaction_analytics"]` if the agent overrides, otherwise falls back to the snapshot. The standalone `scripts/transactions.py analytics` subcommand still exists for inspection. Pipeline-side computation failures surface as snapshot errors and become data-gap entries automatically.

   **Per-market profit tables:** `report_snapshot.json["profit_panel"]["rows"][*]` includes `per_market_detail` (per asset-class bucket: `pnl`, `realized`, `unrealized_delta`, `return_pct`, `starting_position_value`, `ending_position_value`, `net_flows` always `null` until cash/flow attribution exists). The performance-attribution HTML section renders one profit-panel–shaped table per bucket plus an optional residual block; see `docs/per_market_profit_panel_design.md`.

2.7. **Trading-psychology evaluation (§10.1.7) (HARD REQUIRED)** — agent-authored editorial section that reads as the user's own self-coaching note. Renders between transaction analytics and the holdings table so the flow is `evidence → reflection → positions`. The renderer is deterministic; content comes only from `context["trading_psychology"]`. Missing `context["trading_psychology"]` is a render-blocking error, not a placeholder state.

   **Authoring is judgment, not compute (HARD)**. Pure rules cannot match the user's strategy-specific framing — the same averaging-up pattern is "discipline drift" for one user and "right-sided conviction" for another. The agent operating the pipeline (whatever LLM — Claude, Codex, Gemini, automated runner, human) reads the snapshot data + `SETTINGS.md ## Investment Style And Strategy` and authors the JSON during the report run, before invoking `generate_report.py`. There is no hardcoded LLM provider, no rule-based code generator, and no "auto-fill" script — the spec below is the contract; `scripts/validate_report_context.py` is only a pre-render gate that catches schema and coverage violations.

   **Pipeline placement (mandatory gate)**: between `python scripts/transactions.py snapshot` and `python scripts/generate_report.py`, the agent must:
   1. Read `report_snapshot.json` **field-narrow via `jq`** (not whole-file). Use the specific analytics paths listed under "Authoring rules" below — e.g. `jq '.transaction_analytics.discipline_check.latest_lot_cost_flags' "$REPORT_RUN_DIR/report_snapshot.json"`. Whole-file Reads of `report_snapshot.json` are forbidden in agent context per `docs/context_drop_protocol.md`; the renderer reads the file from disk and that path is unaffected.
   2. Read `SETTINGS.md ## Investment Style And Strategy` to anchor improvements.
   3. Synthesize patterns (not enumerate datapoints) into the schema below.
   4. Merge into `report_context.json` under `"trading_psychology"`.
   5. Run the full pre-render gate `python scripts/validate_report_context.py --snapshot "$REPORT_RUN_DIR/report_snapshot.json" --context "$REPORT_RUN_DIR/report_context.json"`; `generate_report.py` must not be invoked until this passes.

   Demo reports use the same authoring rule. `demo/` only supplies an alternate synthetic transaction DB; the agent generating the report still authors and validates this section during the normal report run.

   **Plain text & typography (HARD).** All `trading_psychology` headline / observation / improvement / strength strings are plain text — no HTML tags (`validate_report_context.py` rejects tag-like markup). Visual styling matches the report body: `generate_report.render_trading_psychology` uses `.psych-*` CSS appended with the canonical stylesheet so font size, line height, and ink colors align with `.prose` / §14.9 tokens.

   **Authoring contract** (HARD):

   ```jsonc
   "trading_psychology": {
     "headline":     "≤ 80 字 · 一句話總結你近期的交易心態",
     "observations": [                           // 2-4 items
       {
         "behavior":  "近 30 日對 NVDA 連續加碼 3 筆，成本逐次上升 +28%",
         "evidence":  "snapshot.transaction_analytics.discipline_check.latest_lot_cost_flags[NVDA]",
         "tone":      "warn"   // pos | neu | warn | neg
       }
     ],
     "improvements": [                           // 2-4 items
       {
         "issue":      "未在加碼前重新檢視變異觀點與錨點",
         "suggestion": "下次加碼前先寫一條 §15.4 變異觀點 + 錨點，否則僅以原 sized_pp 規模執行",
         "priority":   "high"  // high | medium | low
       }
     ],
     "strengths": [                              // optional 0-2 items
       "INTC 大跌後沒有恐慌停損，符合 SETTINGS 高承受度策略"
     ]
   }
   ```

   **Authoring rules:**

   - Every `observations[*].behavior` must cite a specific data point from `snapshot.transaction_analytics` (`discipline_check.latest_lot_cost_flags`, `discipline_check.short_bucket_over_1y`, `trade_quality.recent_activity`, `trade_quality.win_rate_pct`, `performance_attribution.periods[*].per_market`, `performance_attribution.periods[*].per_market_detail`, `performance_attribution.top_detractors`, etc.). Never fabricate behavior observations from memory. Cite the path in `evidence`.
   - Every `improvements[*].suggestion` must reference a `SETTINGS.md ## Investment Style And Strategy` bullet OR a §15 contract clause. The suggestion should be specific and actionable ("下次 NVDA 加碼前先擬一條變異觀點") not generic ("交易要更有紀律").
   - The `headline` is the same first-person voice as the Strategy readout — the user reflecting on their own behavior, not a third-party PM lecturing them.
   - Keep length tight: ≤ 80 chars headline, observations + improvements ≤ 80 chars each line. Use `length_budget_status()` to check.
   - The reviewer pass (Phase C) **must** flag any item that drifts from the strategy or lacks data anchor — append entries to `reviewer_pass.by_section.trading_psychology`.
   - Empty / missing `trading_psychology` is not acceptable. If the evidence shows no behavior problem, still write a valid block with at least one observation that states the clean read and cites the relevant `snapshot.transaction_analytics` path, plus at least one improvement or maintenance rule anchored to `SETTINGS.md`.
3. Holdings P&L and weights table (§10.2)
4. Holding period & pacing (§10.3)
5. Theme / sector exposure: agent-authored deterministic HTML in `context["theme_sector_html"]` plus `context["theme_sector_audit"]`; missing HTML or audit is a pre-render validation failure; not auto-classified by renderer.
6. Latest material news
7. Forward 30-day event calendar
8. High-risk and high-opportunity list
9. Recommended adjustments
10. Today's action list (translated buckets per §15.3)
11. Sources and data gaps

### 10.1.5 Profit panel (HARD)

A discrete period-P&L block placed between the Portfolio Dashboard and the
Holdings table. Sourced from `transactions.db` (the local SQLite event log;
see `docs/transactions_agent_guidelines.md`). `python scripts/transactions.py
snapshot --prices prices.json --output report_snapshot.json` computes and
embeds both `report_snapshot.json["profit_panel"]` and
`report_snapshot.json["realized_unrealized"]`; the renderer copies those values
into context when no explicit override is supplied. The standalone
`profit-panel` / `pnl` subcommands are inspection tools, not report-pipeline
steps.

Periods rendered (every period has a row, even when `n/a`):

| Key       | Boundary                                                   |
|-----------|------------------------------------------------------------|
| `1D`      | Most recent prior trading day                              |
| `7D`      | 7 calendar days back (closest preceding close per ticker)  |
| `MTD`     | Last close of previous calendar month                      |
| `1M`      | Same calendar day -1 month (clamped)                       |
| `YTD`     | Last close of previous calendar year                       |
| `1Y`      | Same calendar day -1 year                                  |
| `ALLTIME` | Earliest transaction date                                  |

Per-row metrics:

```
period_pnl   = ending_value − starting_value − net_external_flows
return_pct   = period_pnl / max(starting_value + 0.5 × net_external_flows, ε)
realized     = Σ realized events (SELL_LOT, DIVIDEND, FEE) in (boundary, today]
unrealized_Δ = ending open-lot unrealized P&L − boundary open-lot unrealized P&L
               where each side is mark price − lot cost, base-converted
net_flows    = Σ DEPOSIT − Σ WITHDRAW in (boundary, today]
```

The decomposition `period_pnl ≈ realized + unrealized_Δ + cash / FX drift`
is intentional. `realized` and `unrealized_Δ` are surfaced; the residual
lives implicitly in `period_pnl` itself and surfaces in Sources & data gaps
when material.

**§10.11 gap-list rendering contract (HARD).** Each audit note in
`profit_panel.rows[].audit`, `profit_panel.open_position_audit`,
`profit_panel.issues`, and `transaction_analytics.discipline_check.data_gaps`
is **its own row** in the §10.11 gaps `<ul>`. The renderer must group notes
under one labeled parent `<li>` (e.g. *Profit panel data gap*) plus a nested
`<ul class="gap-sublist">` containing one `<li>` per note — never concatenate
multiple notes into a single bullet with `；` / `; ` / `,` separators (that
overflows the section width and produces a broken layout). Group cap is 12
visible notes; a 13th+ note collapses into a single trailing `+N more` row in
the same sublist. CSS hardening (`overflow-wrap:anywhere`) is defense-in-depth,
not a substitute for the per-note row contract.

`starting_value` requires daily closes for every held ticker at the boundary
date plus FX as-of the boundary. The agent runs `scripts/fetch_history.py`
to populate `prices.json["_history"]` and `prices.json["_fx_history"]`.
`scripts/fetch_history.py` uses `market_data_cache.db` cache-first by default,
then fetches missing or stale ranges from the free API chain and upserts
successful rows. `transactions.db` remains the only canonical transaction
store; `market_data_cache.db` is derived and disposable. When history is
missing after cache + network fallback, the value falls back to the current latest price / FX
with an explicit `using current` audit note rendered under Sources & data gaps
(MVP `fx_approx` allowance). Missing data does **not** silently render as clean
data; it is surfaced as an auditable data gap.

For ALLTIME, `starting_value = 0`, `starting_unrealized = 0`, and
`net_flows` includes every DEPOSIT − WITHDRAW from the beginning of the DB.

`DIVIDEND` and `FEE` flow into `realized`, **not** `net_flows` — they are
P&L impacts, not external-cash flows.

Sign coloring uses the existing `pos-txt` / `neg-txt` CSS classes from the
canonical sample (no new tokens introduced). When the snapshot/context
`profit_panel` has no rows, the legacy profit-panel section is omitted; the
transaction analytics sections carry the primary performance view.

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

Renderer does not classify. Agent injects exact `<div class="cols-2">` with two `.bars` lists; each bucket row is `.bar-row` matching `_sample_redesign.html` lines 1267-1300. Agent also writes `context["theme_sector_audit"]`; `scripts/validate_report_context.py` blocks render if either the HTML or the audit is missing.

| Column | Label | Domain |
|---|---|---|
| Left | `主題` / translated `Themes` | Cross-cutting; holdings may map to multiple themes. |
| Right | `行業` / translated `Sectors` | Mutually exclusive; each non-cash/non-FX holding maps to exactly one sector. |

Sector closed list, choose from issuer GICS/equivalent disclosure (Wikipedia / Reuters / 10-K / annual report): `半導體`, `軟體 / 雲端`, `通信 / 光電`, `硬體 / 網通`, `汽車 / 電動車`, `能源 / 資源`, `航太 / 國防`, `金融`, `醫療 / 生技`, `消費`, `工業`, `公用事業`, `房地產`, `加密資產`, `多元 ETF / 指數`, `其他`. Pure index ETFs → `多元 ETF / 指數`; sector ETFs → matching sector; cash/FX excluded; unclear → `其他` + Sources gap.

Theme algorithm: seed fixed master list `AI 算力`, `雲端 / 資料中心`, `半導體設備`, `先進封裝`, `新能源 / 核能`, `光電 / OCS`, `航太 / 國防`, `加密資產`, `去美元化 / 黃金`, `防禦資產 / 現金代理`, `通膨保護`, `Mega-cap Tech`; drop zero; merge near-duplicates (document once in bucket-note); visible ≤7 buckets, fold smallest into `其他`; order by master-list clusters then `pct desc`. Theme contribution = `holding_weight_pct × theme_membership_share`, share ∈ `{0,0.25,0.5,0.75,1.0}`, documented per ticker in source audit.

Audit shape (required):

```jsonc
"theme_sector_audit": {
  "as_of": "YYYY-MM-DD",
  "tickers": {
    "NVDA": {
      "sector": "半導體",
      "themes": {"AI 算力": 1.0, "半導體設備": 0.5},
      "sources": ["10-K / issuer / Reuters / ETF factsheet URL actually read"]
    }
  }
}
```

Every non-cash ticker in `report_snapshot.json["aggregates"]` must have one audit entry, exactly one non-empty `sector`, at least one theme, and at least one source. ETF look-through fallback is still recorded in this audit with the factsheet/index source or the failed lookup source.

ETF look-through mandatory for index ETFs using latest issuer/index composition; document as-of. If unavailable: sectors 100% `多元 ETF / 指數`; themes most-applicable single theme; flag Sources gap.

Bar row markup (HARD; common failure mode). Each `.bar-row` MUST emit exactly three children, in this order, all `<div>`:

```html
<div class="bar-row">
  <div class="bar-label">AI 算力</div>
  <div class="bar-track"><div class="bar warn" style="width:100%"></div></div>
  <div class="bar-value">15.5%</div>
</div>
```

Two non-negotiable invariants the validator enforces:

1. Child order is `bar-label → bar-track → bar-value`. `.bar-row` is a CSS grid with columns `96px minmax(80px,1fr) 84px`; any other order puts `bar-track` into the 84px right gutter and the chart looks broken.
2. The colored fill is `<div class="bar ...">`, never `<span class="bar ...">`. The `.bar` CSS rule has no `display:block`, so an inline `<span>` collapses to zero width and the fill never paints.

Do not nest the percentage inside `bar-label`; `bar-value` is its own grid column. Do not omit `bar-value` (use an empty `<div class="bar-value"></div>` only if you also drop `bar-label`'s percentage — which the template doesn't).

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

Self-check: sectors sum exactly 100% cash/FX excluded; every non-cash/non-FX ticker exactly one sector; top theme ≤100%; visible themes ≤7; **every `.bar-row` has exactly three children in order `bar-label → bar-track → bar-value`, with the colored fill as `<div class="bar ...">` (never `<span>`)**; order/color rules followed; bucket-note wording token-for-token. Items 1-3 plus the bar-row markup item are hard fail (validator blocks render); remaining items flag in Sources if imperfect.

### 10.5 News & event coverage (HARD; agent owns web)

Renderer only formats `context["news"]` / `context["events"]`; `scripts/fetch_prices.py` is prices only. Agent must also write `context["research_coverage"]`. Empty news/events without search audit is violation and pre-render validation failure.

**Subagent isolation (HARD; per `docs/context_drop_protocol.md` and `docs/temp_researcher_contract.md`).** §10.5 + §10.6 research is the largest token sink in the pipeline (typically 30k–80k tokens of WebSearch/WebFetch results across the cover universe). It **must** be delegated to a temp-researcher per the brand-agnostic contract — using whatever isolation primitive the runtime provides (Claude Code subagent, Codex fresh session, Gemini CLI subagent, or equivalent). It must not run in the parent agent's context. The parent's brief includes: cover-universe ticker list (from `transactions.db.open_lots` minus cash/cash-equivalents, plus extras from §10.6/§10.9), this §10.5 + §10.6 spec text, and the path `$REPORT_RUN_DIR/report_context.json`. The temp-researcher runs the WebSearch / WebFetch / source-fetching workflow below in its own context, writes `context["news"]`, `context["events"]`, and `context["research_coverage"]` directly into the file, validates the JSON, and returns only `{result_file: <path>, summary: ≤200 words, audit: {bytes, sha256, record_count, sources_count, gaps}}` per the contract's §4 return shape. **The parent agent must not paste the temp-researcher's findings or search snippets back into its own response** — that defeats the protocol. The parent reads from `report_context.json` lazily (via `jq`) only when Phase B authoring needs a specific field. The `MEMORY.md` rule "agent owns live WebSearch/WebFetch for §10.5 — empty section without audit trail = workflow violation" is satisfied because the audit (sources, URLs, search reasoning) lives in `context["research_coverage"]` and the per-news/per-event records — exactly as before, just produced inside the isolated context.

Workflow (executed inside the temp-researcher's isolated context):

1. Cover universe = every `transactions.db.open_lots` position except cash/pure cash-equivalents, de-duped, plus extra tickers surfaced in §10.6/§10.9.
2. Per ticker run ≥1 WebSearch: `"<ticker> <company name>" earnings OR guidance OR downgrade OR upgrade OR catalyst <YYYY-MM>` using current and previous report month. TW also query 繁中: `"<code> <公司名>" 法說 OR 營收 OR 財報 OR 重大訊息`. Fetch/read promising URLs; no SERP-only items.
3. Collect 1-3 material 14-calendar-day items per ticker; older only if thesis-relevant/follow-up. Material = earnings/guidance/M&A/regulator/customer/product/analyst action/capital raise/lawsuit/supply-chain. Skip routine target nudges, recap-only, sponsored. Zero material → audit `news_search:<ticker>:no_material_within_14d` or extended-window reason.
4. Per ticker identify 30-day dated catalysts from issuer IR, exchange filing/calendar, Yahoo, Nasdaq, MarketWatch, TWSE/TPEx. Verify dates on issuer/exchange/official source; unverifiable → `date:TBD` + tried source in data gaps.
5. Macro events (FOMC/CPI/PCE/NFP/BoJ/ECB/NBS) from official central bank/statistics calendars only.

Records:

- News: `ticker`, ISO `date`, `source`, resolving `url` actually read, `headline`, `impact ∈ {pos,neu,neg}`.
- Events: `date`, `topic`, `event`, `impact_label`, `impact_class ∈ {warn,info,pos,neg}`, `watch`; hedge `(待…公告)` only after issuer page tried and missing.
- Research coverage audit:

```jsonc
"research_coverage": {
  "as_of": "YYYY-MM-DD",
  "tickers": {
    "NVDA": {
      "news": {"count": 1, "audit": "read issuer/Reuters; 1 material item"},
      "events": {"count": 0, "audit": "event_search:NVDA:no_dated_catalyst_within_30d after IR/Nasdaq/Yahoo"}
    }
  }
}
```

Every cover-universe ticker must appear under `research_coverage.tickers`. Count may be zero only when the matching audit string explains the exhausted search.

Prioritise into §10.6/§10.8/§10.9/§10.10 by materiality, not weight. Materiality drivers: regulator/legal/going-concern, guidance cut/preannouncement, M&A/take-private/spin, major customer win/loss, approval/recall, dilution, debt maturity/covenant, insider anomaly, halt, peer datapoint. Weight is tie-breaker only.

Render gate: every cover-universe ticker has ≥1 news item or explicit `news_search` audit, and ≥1 30-day dated catalyst or explicit `event_search:<ticker>:no_dated_catalyst_within_30d`, represented in `research_coverage`. No model-memory catalyst dates. If search missing, `scripts/validate_report_context.py` fails before render. Every holding must either get evidence-backed §10.9/§10.10 recommendation, explicit `hold — no material news in search window` + audit, or `Need data`.

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
