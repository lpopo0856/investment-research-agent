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

- [ ] **Prerequisite check ran before any yfinance call**: `import yfinance, requests` succeeded (or install completed and re-detection succeeded) (§8.0).
- [ ] `subagent_prerequisites` line recorded in **Sources & data gaps**: install outcome, resolved version, install command (§8.0).
- [ ] Market-native primary source ran first: `yfinance` for listed securities / FX (batched where possible), Binance / CoinGecko for crypto (§8.2).
- [ ] Pacing rules respected: `threads=False`, ≥ 1.5–2.0s gap, ≤ 25/batch, single session, 10–15s timeout (§8.3).
- [ ] **Rate-limit handling: §8.3.1 tier-down rule honored** — on any 429 / `YFRateLimitError`, §8.4 auto-correction was **skipped** and the agent continued to keyed APIs → web search → no-token APIs.
- [ ] **No `agent_web_search:TODO` left dangling.** Every ticker still at `price_source = "n/a"` after the script ran has a `fallback_chain` showing real tier 3 + tier 4 attempts (or explicit `tier3:exhausted` / `tier4:exhausted` markers) (§8.1 workflow gate, §8.3.1).
- [ ] Symbol/format-style failures got up to 3 auto-corrections before fallback; rate-limit failures did **not** consume the auto-correction budget (§8.4).
- [ ] Per-asset fallback order followed (§8.5).
- [ ] Freshness gate applied; no stale value accepted before exhausting sources (§8.7).
- [ ] §8.8 fields stored per ticker; `n/a` rendered when nothing was credible (§8.7, §9.6).
- [ ] No API keys, tokens, or auth URLs leaked into HTML (§7.2, §8.6).

### A.5 Computations

- [ ] **USD basis enforced.** Every aggregate cell (KPI strip, `市值`, `損益`, P&L ranking, theme/sector, weights, period-pacing aggregates, popover footer) starts with `$`; native trade currency (`NT$` / `¥` / `£` / `HK$`) appears **only** inside the `最新價` cell, the per-lot popover `成本` rows, the cash-line popover, and the source audit (§9.0).
- [ ] **FX rates resolved for every non-USD currency in the book.** Rates either came from `SETTINGS.md` or the editorial context JSON; or were fetched at generation time and recorded with their source + `as_of` in **Sources & data gaps**, plus listed in the masthead meta row (§9.0).
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

- [ ] Voice is professional research-note (§15.1).
- [ ] Recommendations include action + price band + trigger (§15.2).
- [ ] Trims name specific lot(s) by acquisition date, default highest-cost-first (§15.2).
- [ ] Today's action list has the 4 buckets in order, translated (§15.3).

### A.12 Reply

- [ ] Absolute path to HTML given (§16).
- [ ] Most important alerts and data gaps listed (§16).
- [ ] **建議更新 agent spec** note included if any `yfinance` auto-correction or pacing tweak succeeded (§8.3, §8.4, §16).
- [ ] Reply written in the SETTINGS language (§16).
