## 0. Critical references — read first

Before running the report, read these files. They are normative; this guidelines doc references them.

**MAKE SURE YOU READ FULL CONTENT OF THIS FILE BY PARTIAL READING**
**DO NOT USE ANY EXISTING REPORT HTML AS FAST REFERENCE OR DATA SOURCE**
**DO NOT EDIT/DELETE SETTINGS.md, HOLDINGS.md UNLESS USER SPECIFICALLY ASK TO**
**DO NOT EDIT FILES WHILE GENERATING REPORT, YOU SHOULD ONLY ADD THE REPORT AND TEMP FILES**
**ALL THE TEMP FILES CREATED DURING THE PROCESS SHOULD BE REMOVED AFTER REPORT GENERATED**

- `AGENTS.md` — repo-wide agent guidance.
- `README.md` — project overview.
- `/docs/*` — all docs in this directory.
- `HOLDINGS.md` — current positions (auto-read every run).
- `SETTINGS.md` — output language, tone, optional API keys, optional position-sizing rails.
- `reports/_sample_redesign.html` — **canonical visual reference**. New reports must align color, typography, layout, and component styling with this file. If missing, rebuild from the tokens in §14.
- `scripts/fetch_prices.py` — **canonical price-retrieval template** implementing §8 (market-aware primary-source routing: **Stooq JSON primary for listed securities, `yfinance` per-ticker secondary**; **`yfinance` primary for FX**; Binance / CoinGecko first for crypto; Yahoo v8 chart used for ticker-currency verification after every Stooq hit; yfinance pacing for the secondary/FX branches; auto-correction; fallback chain) and §9.0 auto-FX conversion-rate retrieval into `prices.json["_fx"]`. Run this rather than re-implementing the pipeline ad-hoc each report. Output: `prices.json`. **Before invoking it, the latest-price subagent must complete §8.0 (install `yfinance` and `requests`) — `requests` powers the Stooq / Yahoo-chart / keyed-API branches; `yfinance` powers the secondary listed-equity fallback and the FX primary branch.**
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

The procedure is structured as **four serial phases**: **(A) Gather** all data — prices, metrics, news, forward events — then **(B) Think** — form alerts, variant views, recommendations, action list, scoring — then **(C) Review** — switch persona from "I am the user" to "I am a senior PM reviewing the user's analysis" and walk every alert / watchlist entry / recommendation / action / Strategy readout, attaching review notes where the reviewer flags something important or has a suggestion (no replacement of the user's content) — then **(D) Render** + reply. **Each phase only begins after the prior phase is complete.** Forming judgments while data is still being gathered produces stale opinions; rendering before review locks in unchallenged blind spots — the user-as-author voice is too close to the analysis to catch its own gaps, which is precisely why the reviewer pass switches hats before render.

| # | Phase | Step | See |
|---|---|---|---|
| 1 | A · Gather | Read `HOLDINGS.md`, `SETTINGS.md`, and `/docs/*`. Resolve output language and any position-sizing rails | §4, §5 |
| 2 | A · Gather | Auto-classify each holding by asset class, sector, and theme based on current data | §4.3 |
| 3 | A · Gather | Delegate latest-price retrieval to the latest-price subagent: **Stooq JSON primary** for listed securities (with Yahoo v8 chart currency verification), **`yfinance` per-ticker secondary**; **`yfinance` primary** for FX; Binance / CoinGecko first for crypto. Apply pacing rules to every yfinance call | §8.2, §8.3 |
| 4 | A · Gather | If `yfinance` fails for a ticker (secondary listed-equity or FX primary branch), run up to **3 auto-correction attempts** before further fallback | §8.4 |
| 5 | A · Gather | For tickers still unresolved, walk the source hierarchy: keyed APIs → web search / public quote pages → no-token APIs | §8.1, §8.5, §8.6 |
| 6 | A · Gather | Apply the **Freshness gate** to every candidate price; reject stale values until all sources are exhausted | §8.7 |
| 7 | A · Gather | Compute all required metrics (totals, weights, P&L, hold period, book-wide pacing, etc.) | §9 |
| 8 | A · Gather | **Live web research — agent owns this.** Cover universe = **every position in `HOLDINGS.md`** (cash excluded), de-duplicated, plus any extra ticker that surfaces in §10.6 alerts or §10.9 adjustments. Pull (a) 14-day material news per ticker, (b) 30-day dated catalysts per ticker, (c) macro events from official central-bank / BLS / BEA calendars. **Top-N-by-weight is not a substitute for full coverage** — small positions can carry the most consequential news (regulator action, going-concern, debt covenant, large-customer loss). Empty news / events for any cover-universe ticker without an audit row is a workflow violation. **Once findings are on the page, prioritisation into §10.6 / §10.8 / §10.9 / §10.10 is by materiality, not by weight** — a 1.5%-weight name with a regulator action belongs ahead of a 12%-weight mega-cap with a routine analyst nudge | §10.5 |
| 9 | A · Gather | **Follow-up research while gathering.** When step 8 surfaces an interesting datapoint that materially changes the picture for any position (guidance change, regulator action, large customer event, peer datapoint, suspicious price move with no public news, anomalous lot/concentration revealed by step 7's metrics), open a follow-up search **inside Phase A** before moving to Phase B. Do not defer interesting threads to "next run" or to the final reply. The user benefits from the agent connecting dots that the headline list missed | §10.5 |
| 10 | **B · Think** | **All judgment is formed here, with the full data + research set in hand.** Run **per-run special checks** (§11), assemble **High-priority alerts** (§10.6), build the §10.8 high-risk / high-opportunity watchlist, draft §10.9 recommended adjustments (with §15.4 variant view, §15.5 kill criteria, §15.6 portfolio-fit / sizing rails), and write the §10.10 today's action list. **No alert, recommendation, or action item may be drafted before its underlying news / event evidence has been gathered in Phase A.** **Continuous strategy-anchor check (HARD):** the full `## Investment Style And Strategy` content must remain your active touchstone for every judgment in this phase — re-read the relevant strategy bullets before each call (sizing → conviction bullets, kill width → drawdown bullets, lot-trim → holding-period bullets, contrarian variant → contrarian-appetite bullets, hype cap → hype-tolerance bullets, position-type allowance → off-limits bullets) and verify the call respects them. Drift from the strategy under the pull of a compelling standalone analysis is a defect | §10.6, §10.8, §10.9, §10.10, §11, §15, §15.7 |
| 11 | **B · Think** | Compose the **Strategy readout** (§15.7) and **today's summary** (§10.1 #1) — both are interpretive and must reflect the gathered evidence, not pre-written boilerplate. The summary should explicitly call out anything Phase A surfaced that contradicts the prior narrative | §10.1, §15.7 |
| 12 | **C · Review** | **Switch persona** from "I am the user" to a senior PM reviewing the user's analysis. **Re-read the full `## Investment Style And Strategy`** as the touchstone for the review — every alert / watchlist entry / recommendation / action / Strategy readout is checked against it. Attach **review notes** where the reviewer flags something important or has a suggestion (e.g. drift from the user's strategy, sizing inconsistencies, weak anchors, kill criteria that won't survive normal volatility, contradictions between the readout and the action list). **Do not replace the user's content** — review notes annotate, they do not overwrite. Empty notes are acceptable when nothing notable surfaces; padding to look thorough is a hard violation | §15.7, §15.8 |
| 13 | D · Render | Render the HTML (11 sections in order) with inline charts, popovers, RWA, and visual standard, slotting in the Phase C review notes alongside the user's content | §10.1, §10.2, §10.3, §10.4, §13, §14, §15.8 |
| 14 | D · Render | Run the **Pre-delivery self-check** (Appendix A) | Appendix A |
| 15 | D · Render | Reply to the user with the absolute HTML path plus key alerts, data gaps, and any cross-cutting reviewer concerns. Per §10.5.1, name which tickers were searched and how many material items each surfaced. If `yfinance` auto-correction succeeded, include a **建議更新 agent spec** note | §16 |

**Anti-pattern (HARD) — Phase A skipped.** Drafting the alert block, action list, or recommended adjustments from holdings + prices alone — and only then "decorating" them with whatever news happens to come up — produces opinions that look authoritative but are not actually informed by the latest evidence. If you find yourself writing a recommendation before you have read this run's news for that ticker, **stop and go back to Phase A**. The cost of restarting Phase B is a few minutes; the cost of telling the user to act on a stale read is real money.

**Anti-pattern (HARD) — Phase C skipped.** Going straight from user-voice analysis to render — without the senior-PM reviewer pass — produces reports that lock in unchallenged blind spots. The user-as-author voice is too close to its own analysis to catch sizing inconsistencies, weak anchors, kill criteria that won't survive normal volatility, or contradictions between the Strategy readout and the action list. The reviewer hat is what surfaces those. Even a "no notes — content is sound" output from Phase C is required; silently skipping the pass is a violation.

**Anti-pattern (HARD) — strategy-anchor drift.** Reading `## Investment Style And Strategy` once at session start and then drafting Phase B / Phase C content from a fading memory of "what the user roughly wanted" produces calls that quietly diverge from the user's stated stance — typically by adopting PM defaults under the pull of a compelling standalone analysis. The full strategy text must remain your active touchstone for every actionable judgment; re-read the relevant bullets before each call. A judgment that cannot be traced to a strategy bullet is operating from PM defaults, not from the user, and must be flagged accordingly per §15.7's continuous-reference rule.

---

## 3. Glossary

| Term | Meaning |
|---|---|
| **Lot** | A single line in `HOLDINGS.md` representing one acquisition: ticker, quantity, cost basis, acquisition date |
| **Bucket** | One of `Long Term`, `Mid Term`, `Short Term`, `Cash Holdings` — the four risk-horizon groups in `HOLDINGS.md` |
| **Hold period** | Duration since the *oldest* lot's acquisition date (per ticker) |
| **Freshness gate** | The rule set that rejects stale prices based on current market state; see §8.7 |
| **Source hierarchy** | The fallback order for latest prices. **Listed securities:** Stooq JSON → `yfinance` per-ticker → keyed APIs → web search / quote pages → other no-token APIs. **FX:** `yfinance` `=X` → keyed APIs → Frankfurter / Open ER / official central-bank reference. **Crypto:** Binance / CoinGecko → keyed APIs → web pages → other no-token APIs. After every Stooq hit, the ticker quote currency is verified via Yahoo's v8 chart endpoint |
| **— (em-dash)** | Glyph for "Not applicable" (the metric never makes sense for this row) |
| **n/a** | Glyph for "Missing" (the metric should exist but the input is `?` or could not be sourced) |
| **price_source / price_as_of / price_freshness / market_state_basis** | Mandatory per-ticker provenance fields stored at generation time |
| **Strategy readout** | First-person paragraph the agent writes in the user's voice, restating the working strategy internalised from `## Investment Style And Strategy` (§15.7) |
| **Strategy-anchor check** | The continuous-reference discipline: the full `## Investment Style And Strategy` content must remain the active touchstone for every Phase B / Phase C judgment, with each call traced back to specific strategy bullets (sizing → conviction; kill width → drawdown; lot-trim → holding-period; contrarian variant → contrarian appetite; upside cap → hype tolerance; allowed asset / structure → off-limits zones). Internalisation is not a one-time read (§15.7) |
| **Reviewer pass** | Phase C — the agent switches hat from "I am the user" to a senior PM reviewing the user's analysis, then walks every alert / watchlist / recommendation / action item and attaches review notes where it has something to flag or suggest. Does not replace the user's content (§15.8) |
| **Reviewer note** | A short annotation produced during the Reviewer pass and rendered alongside (not in place of) the user's content. Each note flags a concern (sizing inconsistency, weak anchor, kill not surviving normal volatility, contradiction between Strategy readout and action list, missed correlation) or offers a constructive suggestion |
| **建議更新 agent spec** | Final-reply note proposing spec wording when a `yfinance` auto-correction or pacing tweak succeeded |

---
