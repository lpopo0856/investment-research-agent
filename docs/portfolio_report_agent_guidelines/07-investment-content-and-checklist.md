## 15. Investment content standard

> **Canonical math lives in `scripts/generate_report.py`.** The PM-grade calculations introduced by §§15.4–15.7 (R:R, lever bands, rail check, Style readout, length budget, A.11 validation) have authoritative implementations in the renderer module — see the `# PM-grade indicators & style binding` section. The agent must pass raw inputs (entry / target / stop / sized_pp_delta / consensus / variant / anchor / kill_trigger / kill_action / failure_mode / variant_tag) through `report_context.json["adjustments"][i]` and let the renderer compute the canonical strings. Never recompute these locally — that's how silent drift creeps in. Run `python scripts/generate_report.py --self-check` to validate the math before relying on it.
>
> **Helper inventory** (importable from `scripts.generate_report`):
> - `StyleLevers` (data type) + `validate_style_levers(levers) → list[str]` — the **agent** resolves levers via natural-language reading of `## Investment Style` bullets in SETTINGS.md; the script only validates allowed values. Optionally pass the resolved levers through `context["style_levers"]` for documentation.
> - `compute_rr_ratio(target, entry, stop)` and `format_rr_string(...)` (§15.4)
> - `suggest_stop_pct_band(drawdown_tolerance)` (§15.5 lever-driven stop width)
> - `suggest_size_pp_band(conviction_sizing)` (§15.6 sizing band)
> - `check_rails(config, current_pct, delta_pp, ...) → RailReport` and `format_portfolio_fit_line(...)` (§15.6)
> - `length_budget_status(text, max_words, max_chars)` (§15.6.2)
> - `validate_recommendation_block(adj) → list[str]` (Appendix A.11 self-check)
>
> **Lever resolution policy:** the script does NOT infer levers from bullet text. The agent reads `## Investment Style` semantically (LLM judgment) and produces lever values + sources directly.
>
> **Style readout policy:** the agent composes the Style readout **prose** itself (in the SETTINGS `Language`, in its own voice) and passes it as a string via `context["style_readout"]`. The renderer slots the string verbatim as the first item under §10.11 Sources & data gaps — it does not template-format a readout from lever values, because the prose belongs to the agent.

### 15.1 Voice and stance

- Output language follows `SETTINGS.md` strictly (see §5). Default tone: **professional research note**, not casual chat. Be concise, direct, and data-driven.
- The agent's persona is a **professional portfolio manager** (see `AGENTS.md`), not a sell-side researcher. The deliverable is a sized, time-bound, kill-criteria-bearing call — not balanced coverage.
- Default to **inaction (cash / wait)** when no edge exists; default to a **clearly directional, sized, time-bound** call when edge exists. Do not produce noise calls dressed up as activity.
- Do not be reflexively conservative. The user can absorb large drawdowns; aggressive calls are welcome — but every aggressive call must be supported by data, a variant view, an explicit R:R, and a kill criterion.
- Do not mechanically recommend selling on a short-term dip — judge whether fundamentals have actually deteriorated against the kill criteria stated when the position was entered.
- Do not chase strength blindly — check valuation, growth, catalysts, and how much expectation is already in the price.
- Apply the resolved **Style-Conditioning Matrix** levers (see §15.7) to every recommendation; emit a **Style readout** block once per report (see §15.7).

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

**Empty buckets are allowed and preferred over filler.** When no edge exists today, `Must do` may render `— none today —`. Padding with low-conviction actions to fill the bucket is a hard violation of §15.1's "default to inaction" rule.

Each item that *is* in **Must do** or **May do** must carry, inline:

- **Variant tag** — one of `consensus-aligned` / `variant` (timing or magnitude differs from consensus) / `contrarian` (direction differs) / `rebalance` (rails / tax / housekeeping — no thesis). The `Contrarian appetite` lever (§15.7) gates whether `contrarian` may appear.
- **Sized %** — the recommended action's delta to current weight, expressed as percentage points of **total NAV (including cash)**. Examples: `+2.0pp of NAV`, `trim 1.5pp`, `cut to 0pp`. Never use ambiguous "trim 1.5%".
- **R:R** — per §15.4 (number, `n/a (binary outcome — see kill criteria)`, or `n/a (rebalance / tax / rail)` for housekeeping items).
- **Kill** — the price/event from §15.5 that invalidates the action (e.g. `kill: close < $X` or `kill: Q3 GM < 30%`). For `rebalance` items, write `kill: rails restored` or `kill: n/a (housekeeping)`.

If any of those four fields is missing on a non-rebalance item, the item is incomplete and must either be filled in or moved to **Need data**.

**Executable-action boundary (HARD).** Only items that change NAV or explicitly tell the user to buy / add / sell / trim / cut / hedge are "actionable" for the Variant / R:R / Kill template. `hold`, `watch`, `do not add`, `avoid chasing`, `wait for earnings`, and empty-bucket placeholders are status guidance, not executable actions. Do **not** pad these rows with fake `R:R = n/a` or invented kill fields. If the advice is "wait", write the wait trigger and keep the PM-grade template off unless a real executable order is attached.

**Structured-field rule (HARD).** The agent must not hand-write `R:R`, `pp of NAV` / `NAV百分點`, `Portfolio fit`, or PM-meta HTML inside free-form prose. Pass raw structured fields (`variant_tag`, `sized_pp_delta`, `target_pct`, `entry_price`, `target_price`, `stop_price`, `kill_trigger`, `kill_action`, `correlated_with`, `theme_overlap`, etc.) to `report_context.json`; `scripts/generate_report.py` is responsible for computing the NAV delta and formatting the canonical strings. If the renderer cannot compute a valid R:R, omit the R:R line or move the item to **Need data** — never print `R:R = n/a (inputs incomplete)` as if it were investment content.

### 15.4 Variant view & asymmetry (HARD REQUIREMENT)

Every actionable recommendation in §10.8 (high-risk / high-opportunity), §10.9 (recommended adjustments), and §10.10 (today's action list) must carry a variant view and an explicit R:R **where the framework applies** (carve-outs in §15.4.1). "Actionable" means the row changes NAV or names a buy / add / sell / trim / cut / hedge. Pure hold / watch / avoid-chasing rows with `sized_pp_delta = 0` are non-action status guidance and must not be forced into the template. Recommendations that are pure consensus must say so (`consensus-aligned`) and justify why consensus is still mispriced (timing, magnitude, second-order effect) or be downgraded.

**Required template per recommendation:**

| Field | Format | Example |
|---|---|---|
| **Consensus** | One sentence — what sell-side / market is currently pricing in. If no public consensus exists, write `unknown-consensus (no sell-side coverage / illiquid / private)` and proceed. **Never synthesise a number.** | "IBES consensus has FY26 EPS at $4.20 and views guidance as conservative." |
| **Variant** | One sentence — where you disagree. Tag as `variant` (against magnitude / timing), `contrarian` (against direction), or `consensus-aligned` (no disagreement). | "We expect FY26 EPS at $5.10 driven by data-center mix shift accelerating one quarter ahead of the Street." |
| **Anchor** | The specific datapoint, framework, or second-order effect that supports the variant. **Must cite a real, verifiable source** (10-K, 10-Q, transcript, official release, named macro series, named index). Forbidden: invented citations, "industry sources say", unattributed numbers. If no anchor is verifiable, downgrade to `consensus-aligned` and remove the variant tag. | "AWS / GCP / Azure capex run-rates (latest 10-Qs, lines [cite]) imply $X of incremental orders in next two quarters." |
| **R:R** | `Target $X (+a%) / Stop $Y (-b%) → R:R = c:1 over horizon Z` — base-case target, stop = §15.5 kill price. See R:R rules below. | "Target $260 (+30%) / Stop $185 (-7%) → R:R = 4.3:1 over 9 months." |

**R:R rules:**

- Use base case for `Target`. If providing bull/base/bear, the R:R cited is base.
- `R:R < 2:1` → at `Hype tolerance ≤ low` (§15.7) the recommendation **must be downgraded** (smaller size, conviction `low`, or moved to watchlist). At `medium` justification is allowed (very high probability, optionality, hedged structure).
- Stop must equal the §15.5 kill price exactly — no orphan stops. Exception: when the §15.5 kill action is `hedge to delta-neutral` or `hold through (binary)`, write `Stop = n/a (hedged structure — see kill action)` or `Stop = n/a (binary)`.
- Binary catalyst (FDA / earnings / vote) → write `R:R = n/a (binary outcome — see kill criteria)` and state expected payoff distribution instead.
- Rebalance / tax / rail-driven trims (no underlying thesis change) → write `R:R = n/a (rebalance)`. These items also skip the Variant view template — see §15.4.1.

**Anti-quota for contrarian calls (HARD).** The `Contrarian appetite` lever sets a *ceiling*, not a floor. **Zero contrarian calls is the correct output when consensus is right.** Manufacture-to-fill is a hard violation. Counts:

- `none` → zero contrarian calls. `consensus-aligned` and `variant` are both allowed.
- `selective` → up to 1–2 contrarian calls **only if** Anchor is independently verifiable in the cited source; produce zero if no idea clears the bar.
- `strong` → no upper limit, but every contrarian call still requires a verifiable Anchor.

#### 15.4.1 Carve-outs from the variant-view template

Some position types do not admit a variant-view + R:R framework cleanly. Apply the simplified template instead:

| Position type | Template |
|---|---|
| **Index ETF** (broad-market / multi-asset, e.g. VWRA, ACWI) | Use `consensus-aligned` by default. Replace Variant/Anchor with one line on macro view + portfolio role; R:R uses index drawdown bands instead of stops (e.g. `Target +8% / Stop -15% (1y rolling band)`) or `R:R = n/a (core allocation)`. |
| **Sector / thematic ETF** (e.g. SMH, ARKK) | Full variant template applies, but Consensus may be `unknown-consensus (no per-name sell-side aggregate)` and Anchor must reference the underlying-basket thesis. |
| **Crypto** | Variant + Anchor required (on-chain metric, supply schedule, ETF flow, regime). R:R uses regime-defined bands (e.g. `Target $X bull regime / Stop $Y range break`); `R:R = n/a (regime watch)` is allowed when no actionable level is defined. |
| **Short positions** | Full template, but Target is the downside price and Stop is upside; sizing rails apply with sign reversed; `Hype tolerance` lever applies symmetrically (no exaggerated short cases either). |
| **Rebalance / tax-lot / rail-enforcement trims** | Skip Consensus / Variant / Anchor. Tag as `rebalance`. Reason field replaces them: `reason: theme rail breach (sector cap 30% → 33%)`. R:R = `n/a (rebalance)`; kill = `n/a (housekeeping)`. |

### 15.5 Pre-mortem & kill criteria (HARD REQUIREMENT)

Every actionable recommendation must pre-commit its exit (rebalance / housekeeping items excepted — see §15.4.1). State all three of the following — short, specific, machine-readable.

| Field | Format |
|---|---|
| **Most likely failure mode** | One sentence — the highest-probability reason this trade goes wrong. |
| **Kill trigger** | A price *or* an event. Examples: `close below $185 on weekly basis`, `Q3 gross margin < 30%`, `FDA delay past 2026-09`. |
| **Kill action** | Exactly one of: `cut full position`, `cut to 50%`, `hedge to delta-neutral`, `hold through (binary)`, `convert to wait-for-trigger`. |

The kill price must equal the `Stop` used in §15.4 R:R **when the kill action is a price-based cut** (`cut full position`, `cut to 50%`, `convert to wait-for-trigger`). When the kill action is `hedge to delta-neutral` or `hold through (binary)`, the kill is structural and §15.4 R:R uses the corresponding `Stop = n/a` form documented there.

The kill action drives the §10.9 stop-loss and the §15.3 today's-action `kill:` field. The `Drawdown tolerance` lever (§15.7) influences how wide the kill price is set:

- `low` → tighter (e.g. -7% to -10% from entry, or first daily-chart structural break)
- `medium` → moderate (e.g. -12% to -18% from entry, or weekly structural break)
- `high` → wider (e.g. -20% to -30% from entry, or thesis break) — but the kill criterion must still be specific, not "we'll see"

### 15.6 Portfolio fit & sizing rails (HARD REQUIREMENT)

Every actionable recommendation in §10.9 must be checked against `SETTINGS.md` sizing rails before being printed. The required output is a one-line `Portfolio fit` annotation:

```
Portfolio fit — sized Xpp of NAV; correlated with {top-3 overlapping holdings}; theme overlap with {theme name(s)} → {pushes / does not push} {single-name | theme | high-vol bucket} cap toward warn ({current % vs warn %}); cash floor after action {Y%} vs floor {Z%}.
```

`pp of NAV` = percentage points of total net asset value including cash (the same denominator used by the §10.1 KPI strip and §9.1 weights). Never use ambiguous "% of book".

**Renderer-owned NAV math (HARD).** The `目前` / `Current` weight shown in §10.9 is computed by `scripts/generate_report.py` from `HOLDINGS.md + prices.json`, not trusted from `report_context.json`. For sizing, pass either numeric `sized_pp_delta` (signed percentage points of total NAV) or numeric `target_pct`; if `target_pct` is supplied, the renderer computes `sized_pp_delta = target_pct − actual_current_pct`. Do not hand-write NAV percentages in prose, do not use risk-asset-only denominators for `pp of NAV`, and do not mix share-count trims with NAV pp without converting through the current price and total NAV.

Rails to check (defaults; override from `SETTINGS.md` if specified):

- **Single-name weight cap** (default 10% — warn above)
- **Theme concentration cap** (default 30% — warn above)
- **High-volatility bucket cap** (default 30% — warn above)
- **Cash floor** (default 10% — warn below)
- **Single-day move alert** (default ±8%)

Rules:

- If a recommendation would push any rail above its warn threshold, the recommendation must either (a) include an explicit accompanying trim of a correlated holding (named lot per the lot-ordering rule below), or (b) be downsized so the rail is not breached, or (c) be flagged in **§10.6 High-priority alerts** with conviction reduced. Rail-breaching recommendations are an explicit §10.6 trigger (see §10.6 trigger list).
- The `Conviction sizing` lever (§15.7) sets the typical recommended `pp of NAV` band:
  - `flat` → equal-ish weights, no name above ~5pp
  - `kelly-lite` → conviction × asymmetry drives 2–8pp per name
  - `aggressive` → top-conviction asymmetric ideas may go to 8–15pp if rails permit

#### 15.6.1 Lot-trim ordering — two independent axes (acquisition date vs cost basis)

When recommending a `sell` / `trim`, the agent must pick lot ordering on **two independent axes** based on the resolved `Holding-period bias` lever. Newest ≠ highest-cost. Conflating the two is a hard error.

| Lever value | Date-axis ordering | Cost-axis ordering | Resulting default lot to cut first |
|---|---|---|---|
| `trader`   | newest acquisition first | tie-break: highest-cost first | most recently acquired lot (lock recent gains, preserve nothing for long-term tax treatment) |
| `swing`    | newest acquisition first | tie-break: highest-cost first | most recently acquired lot |
| `investor` | (date-neutral) | **highest-cost first** (§15.2 default) | highest-cost-basis lot regardless of date |
| `lifer`    | oldest acquisition last (i.e. trim newer lots first to preserve long-term holdings) | tie-break: highest-cost first | most recently acquired lot — but never the original long-term core lot |

When the lever is missing or ambiguous, fall back to §15.2 (highest-cost first, date-neutral). Always name the chosen lot by ticker + acquisition date (e.g. "trim 2025-09 KAPA lot").

#### 15.6.2 Length budget per recommendation (HARD REQUIREMENT — anti-bloat)

Inline content size, by surface:

- **§10.10 today's-action items** — single line each (variant tag + sized pp + R:R + kill, per §15.3). Hard cap: 240 characters.
- **§10.9 recommended adjustments** — `≤ 60 words per position`. Use bullet form: 1 line consensus + 1 line variant + 1 line anchor + 1 line R:R + 1 line kill + 1 line portfolio fit. Promote only the **top 5 by conviction** to the full block; remaining holdings get a one-line `hold / pass / trim Xpp / kill: $X` summary in the same section.
- **§10.9 renderer input hygiene** — `why` is plain text only. Do not include `<br>`, `<span>`, preformatted PM-meta strings, manual `R:R`, or manual NAV labels inside `why`; the renderer escapes prose and appends structured PM fields itself.
- **§10.8 high-risk / high-opportunity watchlist** — one-line per name: `{tag} {ticker}: {1-clause thesis} [variant: {tag}] [R:R {value}] [kill: {trigger}]`.
- **Style readout** — single paragraph, ≤ 90 words, ≤ 6 sentences.

Reports for books ≥ 20 positions should still fit within 6,000 words of investment-content text; if not, compress §10.9 by tightening the top-5 selection.

### 15.7 Style-conditioning matrix (HARD REQUIREMENT — single source of truth)

**This table is the single source of truth for Style-Conditioning Matrix levers.** `AGENTS.md` summarises but defers here. Any future tweak — lever name, allowed values, effect — must land in this section first.

The agent must resolve six behavioral levers from `SETTINGS.md` (free-form `Investment Style` bullets are primary; the optional `Style levers` block overrides inferred values) and apply them to every recommendation. Levers are not cosmetic — they change *what* is recommended, not just phrasing.

| Lever | Allowed values | Effect |
|---|---|---|
| **Drawdown tolerance** | low / medium / high | Width of kill prices (§15.5); willingness to scale into drawdowns. |
| **Conviction sizing** | flat / kelly-lite / aggressive | Typical recommended `pp of NAV` per name (§15.6). |
| **Holding-period bias** | trader / swing / investor / lifer | Skews horizon recommendations and §15.6.1 lot-trim ordering (two-axis: date and cost). |
| **Confirmation threshold** | low / medium / high | Whether the agent waits for trigger confirmation before recommending entry, or is permitted to front-run setups. |
| **Contrarian appetite** | none / selective / strong | Ceiling (not floor) on `contrarian` variant calls per §15.4. Manufacturing-to-fill is a hard violation. |
| **Hype tolerance** | zero / low / medium | Hard cap on optimistic language. `zero` → no superlatives, every upside number must be base/bull/bear bracketed, bull case ≤ 1.5× base unless an explicit comparable trade is cited. |

#### Inference rules

1. **Distinct bullet per lever (preferred).** If a single SETTINGS bullet plausibly drives more than one lever (e.g. "我能承受極大的短期虧損與波動" arguably touches Drawdown, Confirmation, *and* Conviction), the agent may use it for **at most one** lever; the rest must either map to a different bullet or be marked `(inferred — pin to confirm)` in the readout.
2. **No invented preferences.** If no bullet supports a lever value, fall back to the neutral default and tag `(default)`.
3. **Override > infer.** Any value pinned in the optional `Style levers` block in `SETTINGS.md` overrides inference and is tagged `(pinned)`.
4. **Neutral defaults (when both `Investment Style` and `Style levers` are missing):** `medium / flat / investor / medium / selective / low`. This is the canonical default — `AGENTS.md` and `SETTINGS.example.md` cross-reference here; do not duplicate.

#### Style readout — mandatory once per report

Render the `Style readout` block as **the first item under §10.11 Sources & data gaps**. (The renderer's masthead is a fixed template per the renderer-out-of-scope rule and cannot accept new fields without a renderer change.) The block is a single paragraph, ≤ 90 words, listing each of the six resolved lever values with the SETTINGS source it was derived from and a confidence tag (`pinned` / `bullet "<text>"` / `inferred — pin to confirm` / `default`). Example:

> **Style readout** — Drawdown tolerance: high (bullet "我能承受極大的短期虧損與波動"); Conviction sizing: kelly-lite (pinned); Holding-period bias: investor (default); Confirmation threshold: low (inferred — pin to confirm); Contrarian appetite: selective (pinned); Hype tolerance: zero (bullet "不希望聽到過度誇大的樂觀預測"). Correct in `SETTINGS.md` if any value is wrong.

If `Investment Style` is missing or empty *and* `Style levers` is omitted, fall back to neutral defaults and say so. Never invent risk preferences the user did not state.

When a recommendation would differ across plausible lever settings, **state the difference inline** so the user sees the lever's effect:

> "For a steady investor we'd hold; the user's high drawdown tolerance + kelly-lite sizing supports adding +2pp on a -10% pullback, capped at the 10% single-name rail."

#### 15.7.1 Translation contract for new field labels (HARD)

The new field labels introduced in §§15.3–15.7 — `Style readout`, `Consensus`, `Variant`, `Anchor`, `R:R`, `Kill`, `Portfolio fit`, `Sized at`, `Must do` / `May do` / `Avoid` / `Need data`, `pp of NAV` — are reference keys in this English-only spec. **At runtime they must be rendered in the SETTINGS `Language`.** Bilingual labels are forbidden per §5.1; the agent translates each label into the resolved language consistently throughout the report. Field *values* that are reference tokens (`consensus-aligned`, `variant`, `contrarian`, `rebalance`, `flat / kelly-lite / aggressive`, etc.) may stay in English as proper-noun-style codes, since they are part of the agent's vocabulary, not user-facing prose.

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

- [ ] **Prerequisite check ran before any yfinance call**: `import yfinance, requests` succeeded (or install completed and re-detection succeeded) (§8.0).
- [ ] `subagent_prerequisites` line recorded in **Sources & data gaps**: install outcome, resolved version, install command (§8.0).
- [ ] Market-native primary source ran first: **Stooq JSON** for listed securities (with Yahoo v8 chart currency verification on every hit) → `yfinance` per-ticker secondary; **`yfinance` `=X`** primary for FX; Binance / CoinGecko for crypto (§8.2).
- [ ] Pacing rules respected for every yfinance call (per-ticker only, no batch): sequential, ≥ 1.5–2.0s gap, single shared session, 10–15s timeout (§8.3).
- [ ] **Rate-limit handling: §8.3.1 tier-down rule honored** — on any 429 / `YFRateLimitError`, §8.4 auto-correction was **skipped** and the agent continued to keyed APIs → web search → no-token APIs.
- [ ] **No `agent_web_search:TODO` left dangling.** Every ticker still at `price_source = "n/a"` after the script ran has a `fallback_chain` showing real tier 3 + tier 4 attempts (or explicit `tier3:exhausted` / `tier4:exhausted` markers) (§8.1 workflow gate, §8.3.1).
- [ ] Symbol/format-style failures got up to 3 auto-corrections before fallback; rate-limit failures did **not** consume the auto-correction budget (§8.4).
- [ ] Per-asset fallback order followed (§8.5).
- [ ] Freshness gate applied; no stale value accepted before exhausting sources (§8.7).
- [ ] §8.8 fields stored per ticker; `n/a` rendered when nothing was credible (§8.7, §9.6).
- [ ] No API keys, tokens, or auth URLs leaked into HTML (§7.2, §8.6).

### A.5 Computations

- [ ] **Base-currency basis enforced.** Every aggregate cell (KPI strip, `市值`, `損益`, P&L ranking, theme/sector, weights, period-pacing aggregates, popover footer) uses the configured base-currency prefix; native trade currency (`NT$` / `¥` / `£` / `HK$`) appears **only** inside the `最新價` cell, the per-lot popover `成本` rows, the cash-line popover, and the source audit (§9.0).
- [ ] **FX rates resolved for every non-base currency in the book.** Rates came from the automatic `scripts/fetch_prices.py` FX pipeline, are stored in `prices.json["_fx"]`, and are recorded with source + `as_of` in **Sources & data gaps**, plus listed in the masthead meta row (§9.0). No manual rates came from `SETTINGS.md` or `report_context.json`.
- [ ] No silent parity assumption — the build did not treat any non-USD currency as if it were USD (§9.0).
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

- [ ] Voice is professional research-note, PM persona (§15.1).
- [ ] Recommendations include action + price band + trigger (§15.2).
- [ ] Trims name specific lot(s) by ticker + acquisition date; ordering matches the §15.6.1 two-axis table for the resolved `Holding-period bias` lever (date axis vs cost axis are *not* conflated). Default fallback is §15.2 highest-cost-first.
- [ ] Today's action list has the 4 buckets in order, translated (§15.3). **Empty `Must do` / `May do` is acceptable and preferred over filler when no edge exists** (§15.1, §15.3).
- [ ] Each Must-do / May-do item carries variant tag, sized pp of NAV, R:R, and kill (§15.3). `rebalance` items are exempt from variant/R:R/kill per §15.4.1.
- [ ] **Style readout** rendered as the first item under §10.11 Sources & data gaps (not in the masthead — masthead template is fixed). Names all six resolved levers with confidence tags `pinned` / `bullet "<text>"` / `inferred — pin to confirm` / `default` (§15.7).
- [ ] Distinct-bullet rule respected — any lever inferred from a bullet already used for another lever is tagged `(inferred — pin to confirm)` (§15.7).
- [ ] Every actionable recommendation (§10.8 / §10.9 / §10.10) carries a **Variant view** (Consensus / Variant / Anchor), is explicitly `consensus-aligned`, or uses a §15.4.1 carve-out template (Index ETF / sector ETF / crypto / short / rebalance).
- [ ] Non-action status rows (`hold`, `watch`, `do not add`, `avoid chasing`, `wait`) with `sized_pp_delta = 0` do **not** print fake R:R / kill / NAV strings; they show only the wait trigger or data need (§15.3 / §15.4).
- [ ] **No fabricated consensus numbers.** Every `Consensus` line cites a real source (IBES, Visible Alpha, named report) or uses `unknown-consensus (...)` (§15.4).
- [ ] **No fabricated anchors.** Every Anchor cites a verifiable source (10-K/Q, transcript, named index, named macro series). Recommendations without a verifiable anchor are downgraded to `consensus-aligned` (§15.4).
- [ ] Every actionable recommendation has explicit **R:R** in the §15.4 format, or `n/a (binary outcome — see kill criteria)`, or `n/a (rebalance / tax / rail)` for housekeeping items. Stop equals §15.5 kill price for price-based cuts; uses `Stop = n/a (hedged ...)` or `Stop = n/a (binary)` when kill action is non-cut (§15.4 / §15.5).
- [ ] Every actionable recommendation (rebalance items excepted) carries a **Pre-mortem & kill criteria** triplet (failure mode, kill trigger, kill action) (§15.5).
- [ ] Every actionable recommendation carries a **Portfolio fit** annotation — sized pp of NAV, correlated holdings, theme overlap, rail-check vs SETTINGS sizing rails (§15.6).
- [ ] NAV math is renderer-owned: `Current` uses actual total-NAV weight from `HOLDINGS.md + prices.json`; action size is numeric `sized_pp_delta` or `target_pct`; no free-form `NAV百分點` / `pp of NAV` strings are hand-written in prose (§15.3 / §15.6).
- [ ] No recommendation breaches a SETTINGS rail without either an accompanying named-lot trim, a downsize, or escalation to §10.6 High-priority alerts (§15.6). Rail-breach is a §10.6 trigger.
- [ ] `Contrarian appetite` lever respected as a **ceiling, not a floor**. Zero contrarian calls is acceptable and is the correct output when consensus is right. Manufacture-to-fill flagged as a violation (§15.4 / §15.7).
- [ ] `Hype tolerance` lever respected — no superlatives at `zero`; price targets are base/bull/bear bracketed; bull case ≤ 1.5× base unless a named comparable trade is cited (§15.7).
- [ ] **Length budget respected** (§15.6.2): §10.10 items ≤ 240 chars each; §10.9 top-5 full block + ≤ 60 words/position, others one-line; §10.8 watchlist one-line per name; Style readout ≤ 90 words.
- [ ] **Translation contract honored** (§15.7.1): all field labels (`Style readout`, `Consensus`, `Variant`, `Anchor`, `R:R`, `Kill`, `Portfolio fit`, `Sized at`, action-list bucket names, `pp of NAV`) rendered in the SETTINGS `Language`. Reference token values (`consensus-aligned` / `variant` / `contrarian` / `rebalance` / `flat`-`kelly-lite`-`aggressive` / etc.) may stay in English.

### A.12 Reply

- [ ] Absolute path to HTML given (§16).
- [ ] Most important alerts and data gaps listed (§16).
- [ ] **建議更新 agent spec** note included if any `yfinance` auto-correction or pacing tweak succeeded (§8.3, §8.4, §16).
- [ ] Reply written in the SETTINGS language (§16).
