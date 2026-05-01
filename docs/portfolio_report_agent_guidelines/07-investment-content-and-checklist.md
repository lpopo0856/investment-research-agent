## 15. Investment content standard

Renderer-owned PM math. Agent passes raw fields through `report_context.json["adjustments"][i]` / related context; `scripts/generate_report.py` computes canonical strings. Run `python scripts/generate_report.py --self-check`.

Helpers from `scripts.generate_report`: `compute_rr_ratio`, `format_rr_string`, `check_rails(...) → RailReport`, `format_portfolio_fit_line`, `length_budget_status`, `validate_recommendation_block`.

Strategy policy: no lever block / keyword inference. Read whole `SETTINGS.md` `## Investment Style And Strategy`; act as the user. Stop width, sizing band, lot ordering, contrarian latitude, tone, no-go zones flow from that prose. `context["strategy_readout"]` (legacy `style_readout`) is first-person SETTINGS-language prose, rendered verbatim as the first labeled prose block under §10.11 — above the source-audit table and the data-gaps list, never as an item inside the gaps `<ul>`.

### 15.1 Voice, stance, phase order

- SETTINGS language; professional research-note voice; PM not sell-side; direct, data-driven.
- No-edge default = cash/wait; edge default = directional, sized, time-bound, kill-bearing call.
- Aggressive calls allowed only with data, variant view, R:R, kill. Do not reflexively sell dips; distinguish fundamentals/news deterioration from price noise. Do not chase without valuation/growth/catalyst/expectation check.
- Apply full strategy section continuously. Before each alert/watchlist/variant/kill/size/lot-trim/action, check governing bullets: sizing→conviction; kill width→drawdown; lot trim→holding period; contrarian→contrarian appetite; upside language→hype tolerance; allowed structure→off-limits. Untraceable calls = PM default; flag in readout, downsize/soften, reviewer-note.
- Phase order hard gate: no summary/alert/watchlist/recommendation/action before Phase A prices + metrics + §10.5 news/events + follow-up research are complete. Interesting Phase A datapoints get follow-up search before Phase B.

### 15.2 Position handling

Dynamic `transactions.db.open_lots`; never hard-code. Judge long-term core, mid-term growth, short-term positions separately; same ticker in different buckets may get different actions. High-growth/high-vol names require bull/base/bear. Every recommendation needs action + price band + trigger. Trims name ticker + acquisition date; default highest-cost-first unless §15.6.1 strategy posture says otherwise. Use hold period and per-lot P&L context. Flag data gaps, estimates, source conflicts.

### 15.3 Today's action list

Buckets, in order, translated: `Must do`, `May do`, `Avoid`, `Need data`. Empty buckets allowed/preferred over filler (`— none today —`).

`actions` shape is always an object with four list buckets: `must_do`, `may_do`, `avoid`, `need_data`. Executable `Must do` / `May do` items must be structured objects, not prose strings, and must carry:

- `variant_tag ∈ {consensus-aligned, variant, contrarian, rebalance}`; contrarian is ceiling not quota.
- `sized_pp_delta` or renderer-computed `target_pct`, expressed as percentage points of total NAV including cash (`+2.0pp`, `trim 1.5pp`, `cut to 0pp`; never ambiguous %).
- R:R per §15.4 or allowed `n/a (binary outcome — see kill criteria)` / `n/a (rebalance / tax / rail)`.
- Kill per §15.5; rebalance kill = `rails restored` or `n/a (housekeeping)`.

Incomplete executable item → fill or move to `Need data`. Non-executable statuses (`hold`, `watch`, `do not add`, `avoid chasing`, `wait`, placeholders) do **not** get fake R:R/kill/NAV strings; show wait trigger or data need only. Agent must not hand-write `R:R`, `pp of NAV`, `Portfolio fit`, or PM-meta HTML in prose; pass structured fields (`text`, `ticker`, `action`, `variant_tag`, `sized_pp_delta`, `target_pct`, `entry_price`, `target_price`, `stop_price`, `kill_trigger`, `kill_action`, `correlated_with`, `theme_overlap`, etc.) and let renderer format. Invalid R:R inputs → omit/move to Need data; never print `R:R=n/a (inputs incomplete)`. `scripts/validate_report_context.py` fails executable string items in `must_do` / `may_do`.

### 15.3.1 Recommended adjustments (`adjustments`) (HARD)

`context["adjustments"]` must be a **non-empty** array. Every report includes at least one §10.9 table row authored by the agent, each with non-empty `ticker`, `action`, `action_label`, `why`, and `trigger` (columns rendered by `scripts/generate_report.py`). There is no “skip the table” option: if no NAV-changing trade is warranted, emit explicit `hold` / `watch` / `wait` rows with triggers tied to evidence (earnings dates, thesis checkpoints, rails). An empty `[]` fails `scripts/validate_report_context.py`. Actionable rows still require the PM-grade field bundle per §15.4–15.6.

### 15.4 Variant view & asymmetry (HARD)

Applies to actionable §10.8/§10.9/§10.10 rows: NAV-changing or buy/add/sell/trim/cut/hedge. Non-action `sized_pp_delta=0` rows skip template.

For §10.8 `high_opps`, each row must explicitly set `"actionable": true|false`. Actionable opportunity rows carry the same PM fields as §10.9; non-action watchlist rows must include `ticker`, `why`, and `trigger` or `watch`.

| Field | Required format |
|---|---|
| Consensus | What sell-side/market prices. Cite real source (IBES, Visible Alpha, named report) or `unknown-consensus (reason)`. Never synthesize. |
| Variant | Where user disagrees; tag `variant` (timing/magnitude), `contrarian` (direction), or `consensus-aligned`. Pure consensus must explain why still mispriced or downgrade. |
| Anchor | Verifiable datapoint/framework/second-order effect from real source (10-K/Q, transcript, official release, named macro series/index). No invented/unattributed anchors; if unverifiable, downgrade to `consensus-aligned`. |
| R:R | `Target $X (+a%) / Stop $Y (-b%) → R:R = c:1 over horizon Z`; target = base case; stop = §15.5 kill price unless structural/binary exception. |

R:R rules: base case used even with bull/base/bear; R:R <2:1 downgrades unless strategy explicitly accepts low-R:R and hype tolerance permits; price stop must equal kill price; `hedge to delta-neutral` / `hold through (binary)` uses `Stop=n/a`; binary catalyst uses `R:R=n/a (binary outcome — see kill criteria)` + payoff distribution; rebalance/tax/rail trims use `R:R=n/a (rebalance)` and skip Consensus/Variant/Anchor.

Contrarian anti-quota: strategy rejecting/omitting contrarianism → zero contrarian calls; selective contrarian strategy → 0-2 only with verifiable anchor; strong contrarian strategy → no cap but every call still anchored. Manufacture-to-fill = violation.

#### 15.4.1 Carve-outs

| Type | Template |
|---|---|
| Broad index ETF (VWRA/ACWI/etc.) | `consensus-aligned`; replace Variant/Anchor with macro view + portfolio role; R:R index drawdown bands (`Target +8% / Stop -15% 1y rolling`) or `n/a (core allocation)`. |
| Sector/thematic ETF | Full template; Consensus may be `unknown-consensus`; Anchor references underlying basket. |
| Crypto | Variant+Anchor required (on-chain, supply, ETF flow, regime); R:R regime bands or `n/a (regime watch)`. |
| Short | Full template; target downside, stop upside; sizing sign reversed; hype tolerance symmetric. |
| Rebalance/tax-lot/rail trim | Tag `rebalance`; `reason: theme rail breach (sector cap 30% → 33%)`; R:R `n/a (rebalance)`; kill `n/a (housekeeping)`. |

### 15.5 Pre-mortem & kill criteria

Every actionable recommendation except rebalance/housekeeping carries:

| Field | Constraint |
|---|---|
| Failure mode | Highest-probability reason trade goes wrong. |
| Kill trigger | Price or event: `weekly close below $185`, `Q3 GM <30%`, `FDA delay past 2026-09`. |
| Kill action | Exactly one: `cut full position`, `cut to 50%`, `hedge to delta-neutral`, `hold through (binary)`, `convert to wait-for-trigger`. |

Price kill used for cut/convert actions equals §15.4 stop. Structural/binary kill uses corresponding `Stop=n/a`. Kill action drives §10.9 stop-loss and §15.3 `kill:`. Width follows strategy drawdown tolerance: tight -7% to -10% / daily break; moderate -12% to -18% / weekly break; high -20% to -30% or thesis break, still specific.

### 15.6 Portfolio fit & sizing rails

Every actionable §10.9 row requires renderer-formatted Portfolio fit:

`Portfolio fit — sized Xpp of NAV; correlated with {top-3 overlaps}; theme overlap with {themes} → {pushes/does not push} {single-name|theme|high-vol bucket} cap toward warn ({current% vs warn%}); cash floor after action {Y%} vs floor {Z%}.`

NAV basis = total NAV including cash. Renderer computes `Current` from `transactions.db.open_lots + cash_balances + prices.json`; pass numeric `sized_pp_delta` or `target_pct` (renderer derives delta). No prose NAV math, risk-asset denominator, or share-count trim without converting through current price/total NAV.

Default rails, overridden by SETTINGS: single-name cap 10%, theme cap 30%, high-vol bucket cap 30%, cash floor 10%, single-day move alert ±8%. Rail breach requires one of: accompanying correlated trim with named lot, downsize, or §10.6 alert + reduced conviction.

Sizing calibration from strategy: flat posture ~equal/no name >~5pp; kelly-lite 2-8pp by conviction×asymmetry; aggressive/concentrated 8-15pp if rails permit.

#### 15.6.1 Lot-trim ordering

Two axes are independent: acquisition date vs cost basis. Newest ≠ highest-cost.

| Strategy posture | Date-axis | Cost-axis | Default cut first |
|---|---|---|---|
| Trader / short-term | newest first | tie-break highest-cost | most recent lot |
| Swing trade | newest first | tie-break highest-cost | most recent lot |
| Multi-year investor default | date-neutral | highest-cost first | highest-cost lot |
| Generational/lifer | oldest last | tie-break highest-cost | newer lot; never original core lot |

If strategy silent: highest-cost-first, date-neutral. Always name ticker + acquisition date and state posture used.

#### 15.6.2 Length budget

§10.10 action item ≤240 chars; §10.9 ≤60 words per top-5 conviction position using 1 line each consensus/variant/anchor/R:R/kill/portfolio fit; remaining holdings one-line `hold/pass/trim Xpp/kill`; `why` plain text only, no `<br>`, `<span>`, manual PM strings; §10.8 one-line per name; Strategy readout ≤90 words/≤6 sentences; books ≥20 positions should keep investment content ≤6,000 words by compressing §10.9.

### 15.7 Strategy binding — act as user (HARD)

Single source of truth for user identity. Whole `## Investment Style And Strategy` in `SETTINGS.md` must be read, including late off-limits and tone bullets. No invented preferences; silent dimensions use neutral PM fallback and are tagged. Neutral fallback when missing/empty: medium drawdown, flat sizing, multi-year horizon, medium confirmation, selective contrarian, low hype. User strategy overrides defaults; note overrides in readout.

| Decision | Check strategy bullets |
|---|---|
| Size / `pp of NAV` | conviction & sizing |
| Kill width | drawdown tolerance |
| Front-run vs wait | entry discipline / confirmation |
| Sell-lot order | holding-period bias |
| Contrarian tag | contrarian appetite (ceiling) |
| Upside language / target multiplier | hype tolerance; strict default = base/bull/bear bracketed, bull ≤1.5× base unless named comparable |
| Allowed theme/structure | off-limits zones |
| Tone/density/explicit risk | decision-style bullets |

Untraceable judgment → mark readout `inferred — pin to confirm`, downsize/soften, reviewer-note. Strategy drift is a defect.

**Strategy readout:** rendered as the first labeled prose block under §10.11 Sources & data gaps (above the source-audit table and the data-gaps list, not as an item inside the gaps `<ul>`); one paragraph ≤90 words; first person as user; SETTINGS language; covers relevant temperament/drawdown, conviction/sizing, holding period, entry discipline, contrarian appetite, hype tolerance, off-limits; cites SETTINGS bullets. Missing strategy → explicitly say neutral fallback. If recommendation differs under another strategy, state consequence inline. Reviewer notes for `strategy_readout` attach to this block, not to the gaps list.

#### 15.7.1 Translation contract

Translate field labels in SETTINGS language: `Strategy readout`, `Reviewer note`, `Reviewer summary`, `Consensus`, `Variant`, `Anchor`, `R:R`, `Kill`, `Portfolio fit`, `Sized at`, action buckets, `pp of NAV`. Bilingual labels forbidden. Token values (`consensus-aligned`, `variant`, `contrarian`, `rebalance`) may stay English as codes.

### 15.8 Reviewer pass — senior PM review (HARD)

Phase C after Phase B and before render. Persona switches from user-author to senior PM reviewer. Reviewer annotates, never rewrites; user-authored readout/alerts/watchlist/recommendations/actions remain. Empty notes acceptable; filler forbidden.

Review targets: sizing vs strategy; anchor quality; kill realism/action consistency; strategy/action contradictions; missed correlation/concentration; rail-breach handling; missing data dependencies; phase-ordering hygiene; tone/persona drift; cleaner expression (different lot, hedge, smaller tranche, limit band).

#### 15.8.1 `reviewer_pass` shape

```jsonc
{
  "reviewer_pass": {
    "completed": true,
    "reviewed_sections": [
      "alerts", "watchlist", "adjustments", "actions", "strategy_readout",
      "trading_psychology", "theme_sector", "news_events"
    ],
    "summary": ["cross-cutting concern; final reviewer-summary block under §10.11; Strategy readout remains first"],
    "by_section": {
      "alerts": ["..."],
      "watchlist": ["..."],
      "adjustments": ["..."],
      "actions": ["..."],
      "strategy_readout": ["..."],
      "trading_psychology": ["..."],
      "theme_sector": ["..."],
      "news_events": ["..."]
    }
  }
}
```

Inline per-row preferred: add `"reviewer_notes":["..."]` to `adjustments[i]`, `watchlist[i]`, or `actions[bucket][i]`. Renderer displays notes alongside content with translated `Reviewer note`; summary with translated `Reviewer summary` as final reviewer-summary block under §10.11. Empty notes are expressed as `summary: []` and `by_section: {}`, but `completed: true` and full `reviewed_sections` remain required so the reviewer pass cannot be silently skipped.

#### 15.8.2 Discipline

Notes ≤240 chars / 2 sentences; summary ≤120 words. Reviewer prose in SETTINGS language, third-person about user, not first-person. Serious defects (unsourced action dependency, unrealistic kill, rail breach without trim/downsize/escalation) must return to earlier phase and be fixed, not shipped as note.

---

## 16. Reply format to user

Reply in SETTINGS language with absolute HTML path, most important alerts, data gaps, §10.5.1 searched-ticker counts, and `建議更新 agent spec` note if yfinance correction/pacing tweak succeeded. Do not ask user to assemble/install/run anything.

---

## Appendix A — Pre-delivery self-check

### A.1 Inputs/language

- [ ] Fresh read: `transactions.db` (positions via `load_holdings_lots`), `SETTINGS.md`, `/docs/*`; output language + `<html lang>` match; no bilingual labels; stray-language grep clean except §5.2 allow-list.

### A.2 File output

- [ ] HTML only at `reports/YYYY-MM-DD_HHMM_portfolio_report.html`; local-clock timestamp; no companion Markdown/files.

### A.3 Self-containment

- [ ] No `<script src>`, stylesheet link, CDN chart lib, runtime `fetch`/XHR/API key/market endpoint; valid with JS disabled; self-containment grep clean; single `<style>` ordered tokens→base→layout→components.

### A.4 Latest-price retrieval

- [ ] §8.0 import/install probe + `subagent_prerequisites`; market-native primary order honored (Stooq+Yahoo currency verify → yfinance listed secondary; yfinance FX; Binance/CoinGecko crypto); yfinance pacing respected; 429 tier-down skipped §8.4; no dangling `agent_web_search:TODO`; symbol failures got ≤3 auto-fixes; per-asset fallback order + Freshness gate + §8.8 fields; no leaked keys/auth URLs.

### A.5 Computations

- [ ] Base-currency aggregates everywhere required; native currency only allowed surfaces; FX rates auto in `prices.json["_fx"]` with source/as_of/masthead/audit; no parity assumption; totals/weights/P&L/per-lot/avg cost; hold period formats; move % subline rule; no IRR; pacing aggregates; `—` vs `n/a` cell-level glyphs.

### A.6 Required sections

- [ ] 11 sections in order; 7 holdings columns and no `Held`/`Move`; §10.3 KPI+strip+bucket-notes; 8 inline charts no external lib; §10.5 news and events searched for every cover ticker with item or audit; materiality-not-weight ordering; no silent small-position omission; events cover earnings/calls/ex-div/launches/regulators/M&A/raises/debt/lockup/macro; final reply names searched tickers + item counts; high-priority alerts rendered when triggered.

### A.7 Special checks

- [ ] All 10 §11 checks explicitly answered, including clean passes.

### A.8 Static price snapshot

- [ ] §12.1 retrieval order; price cell + popover display; source audit includes provider/degraded/EOD/`n/a` reasons and yfinance failure/correction trail.

### A.9 Popovers

- [ ] Symbol/Price triggers are `<div tabindex="0" role="button">`; descendant `:hover`/`:focus-within`; Symbol and Price content complete including `<tfoot class="summary">`; tablet/phone bottom sheet verified ≤880/≤600; reduced motion; no §13.8 anti-patterns.

### A.10 Visual

- [ ] `:root` tokens; system fonts only; typography settings; §14.4 floors; component/layout rules; price-cell CSS; responsive breakpoints incl 360px phone; no §14.8 anti-patterns; checked against `_sample_redesign.html`.

### A.11 Investment content

- [ ] Phase ordering + Phase A follow-up research; PM voice; recommendations action+band+trigger; trims name lots and respect §15.6.1; translated 4 action buckets and empty buckets allowed; executable Must/May fields variant tag + sized pp + R:R + kill; mandatory `trading_psychology` authored from `snapshot.transaction_analytics`; `theme_sector_audit` and `research_coverage` complete; `scripts/validate_report_context.py` passes; Strategy readout first under §10.11, first-person, ≤90 words, whole SETTINGS strategy reflected or fallback flagged; continuous strategy-anchor trace for every actionable judgment; actionable rows carry Variant/Consensus/Anchor or carve-out; non-action rows avoid fake PM strings; no fabricated consensus/anchors; R:R/kill/Portfolio fit complete; NAV math renderer-owned; rail breaches handled; contrarian appetite ceiling; hype tolerance base/bull/bear and bull ≤1.5× base unless comparable; length budgets; translation contract.

### A.12 Reply

- [ ] Absolute HTML path, key alerts, data gaps, yfinance spec-update note if relevant, SETTINGS language.

### A.13 Reviewer pass

- [ ] Phase C executed before render; `reviewer_pass.completed=true` and required `reviewed_sections` present; reviewer annotations do not replace content; empty notes allowed/filler rejected; third-person reviewer voice; note/summary length budgets; translated labels/prose; serious defects sent back to earlier phase; reviewer summary rendered as final reviewer-summary block under §10.11 when present.
