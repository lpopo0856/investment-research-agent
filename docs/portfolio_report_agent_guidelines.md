# Portfolio Report Agent Guidelines

## Natural-language user interface

Natural language is the default user interface for this workflow. Commands, flags, paths, schemas, and machine-readable examples in this document are agent-internal contracts or audit evidence. In normal user replies, translate them into natural-language actions, execute eligible steps yourself, collect missing parameters conversationally, and summarize results naturally. Do not show Python/shell commands, command code blocks, canonical command names, or JSON/file-format requirements as user instructions unless the user explicitly asks for CLI/API help or execution is blocked by missing authority.

Machine entrypoint for portfolio-report generation. The spec is optimized for agent execution, not narrative readability.

## Required Bundle Read

Read this file first, then read **every** part file below in order on every portfolio-report run. The part files are normative; do not use existing generated report HTML as a shortcut or data source.

1. [00-preface-and-toc.md](./portfolio_report_agent_guidelines/00-preface-and-toc.md)
2. [01-critical-references-to-glossary.md](./portfolio_report_agent_guidelines/01-critical-references-to-glossary.md)
3. [02-inputs-to-self-containment.md](./portfolio_report_agent_guidelines/02-inputs-to-self-containment.md)
4. [03-latest-price-retrieval.md](./portfolio_report_agent_guidelines/03-latest-price-retrieval.md)
5. [04-computations-to-static-snapshot.md](./portfolio_report_agent_guidelines/04-computations-to-static-snapshot.md)
6. [05-cell-popovers.md](./portfolio_report_agent_guidelines/05-cell-popovers.md)
7. [06-visual-design.md](./portfolio_report_agent_guidelines/06-visual-design.md)
8. [07-investment-content-and-checklist.md](./portfolio_report_agent_guidelines/07-investment-content-and-checklist.md)

## Hard Run Invariants

- **Network use is section-triggered, not report-global.** Latest price / FX / history fetches are part of every normal run and may require network access. §10.5 live news, §10.6 dated-catalyst lookup, follow-up research, consensus-style decision research, and temp-researcher delegation run **only when the effective rendered sections require them** (see "Section-level pipeline routing" below). Today, that means **single-account `daily_report` only**. `portfolio_report` and all `total_account` variants **must not** run §10.5 news search, event-calendar search, `research_targets`, `research_coverage`, or temp-researcher news/events delegation.
- **When a rendered section does require live research, run unsandboxed — explicit authorization granted.** For those included research-class sections, the workflow requires live internet and the agent does not need a separate user prompt to disable the sandbox. Concrete delegation primitives the agent will use for such sections:
  - **Codex CLI `spawn_agent` / Codex subagents:** every `spawn_agent` invocation that fulfills a rendered research-class step (Phase A news, events, follow-up research) MUST pass `sandbox: "danger-full-access"` (or the project equivalent unsandboxed profile) plus a network-enabled approval policy in the call arguments. Inheriting a `read-only` / `workspace-write` default is a workflow violation.
  - **Claude Code Task tool / `subagent_type="temp-researcher"`:** the surrounding session must allow network egress; Bash calls that fetch external data must run with `dangerouslyDisableSandbox: true` when the session default would otherwise block them.
  - **Gemini CLI subagents / fresh-session delegation:** invoke with `--yolo` / `--no-sandbox` / runtime equivalent.
  - **Direct (non-delegated) work in the parent agent:** the same authorization applies only for included research-class sections.

  A run that renders `news` / `events_30d` / `research_coverage` but silently returns them empty because the network or sandbox blocked outbound calls is a workflow violation, not a clean empty-result outcome. When those sections are skipped by report policy, the correct state is **absent / not authored**, not empty researched output.
- Execute in four serial phases: **A Gather → B Think → C Review → D Render + reply**.
- Phase A gathers files, prices, metrics, and **only the live research required by rendered sections** before any judgment for those sections is drafted.
- Phase B drafts **only rendered editorial sections** (alerts / watchlists / adjustments / action items / `trading_psychology` / Strategy readout / summary as applicable) while continuously anchoring to `SETTINGS.md` `## Investment Style And Strategy`.
- Phase C switches hat to a senior PM reviewer, annotates issues for rendered strategy-dependent sections only, and sends serious defects back to the relevant earlier phase before render.
- Phase D renders one self-contained HTML file only after `scripts/validate_report_context.py --snapshot "$REPORT_RUN_DIR/report_snapshot.json" --context "$REPORT_RUN_DIR/report_context.json" --report-type <daily_report|portfolio_report>` passes for the selected mode, runs Appendix A self-checks, **deletes `$REPORT_RUN_DIR`** (`rm -rf`), and replies with the absolute HTML path plus required audit notes.
- `SETTINGS.md` and `transactions.db` (resolved from `accounts/<active>/` via `--account <name>` or the `accounts/.active` pointer; see §4) are read-only unless the user explicitly asks to edit them.

### Intermediate files and cleanup (HARD)

Aligns with `CLAUDE.md` **Temp files**: nothing ephemeral in the repo working tree.

- **Pick one directory per report run:** e.g. `export REPORT_RUN_DIR="/tmp/investments_portfolio_report_$(date +%Y%m%d_%H%M)"` (wall-clock, one stamp per run), then `mkdir -p "$REPORT_RUN_DIR"`. Use `export` so subprocess-spawned CLI steps inherit the variable when the runner wraps each command separately.
- **Write only under `$REPORT_RUN_DIR`:** `prices.json` (including merged `_history` / `_fx_history`), `report_snapshot.json`, `report_context.json`, any `fill_history_gap.py --merge-into` target, and optional `--ui-dict` JSON. **Do not** place these files at the repository root.
- **After success:** HTML lives under `reports/` only; then `rm -rf "$REPORT_RUN_DIR"`. On repeated failed renders you may keep the directory for debugging, but never leave successful-run debris in the repo root.
- **Basenames in part files:** unqualified names like `report_snapshot.json` / `prices.json` mean those files **inside** `$REPORT_RUN_DIR`, not cwd-relative to the repo.

### Report type and account scope (HARD)

Every report run must choose two orthogonal axes before Phase A gather:

- `report_type`: `daily_report` or `portfolio_report`. This is the content taxonomy.
- `account_scope`: `single_account` or `total_account` (`--all-accounts`). This is only input aggregation; **total is not a report type**. If the user does not name an account or ask for total/consolidated/all-accounts scope, resolve the active/default account and proceed as single-account scope after the report type is selected.

**Unspecified report type stop rule.** If the user asks to generate/run a report and the prompt does not clearly specify `daily_report` or `portfolio_report`, stop before Phase A. Do not run `account migrate`, fetch prices/history, read `SETTINGS.md` / `transactions.db`, create `$REPORT_RUN_DIR`, launch live research, or infer a default. Ask one concise question that briefly explains:

- `daily_report`: daily decision/editorial report with alerts, today's summary, material news, 30-day events, high risk/opportunity, recommended adjustments, today's actions, trading psychology, and the holdings Action column for single-account scope.
- `portfolio_report`: math/position review that omits immediate-attention/news/events/actions/trading-psychology sections and the holdings Action column.

Resume the pipeline only after the user selects a type. Account scope can still be inferred from wording (for example, "all accounts") or resolved from the active/default account for ordinary single-account requests; `total_account` is not a substitute for report type.

`daily_report` is the current report minus Profit Panel, Performance Attribution, Discipline Check, Holding Period and Pacing, and P&L Ranking. It still includes alerts, today's summary, material news, 30-day events, high risk/opportunity, recommended adjustments, today's actions, trading psychology, and the holdings Action column for single-account scope.

`portfolio_report` is the current report minus Immediate Attention, Today's Summary, Recent Trading Mindset, Latest Material News, 30-Day Event Calendar, High Risk/Opportunity, Recommended Adjustments, Today's Action List, and the holdings Action column. Math/position sections remain.

`total_account` overlays the existing math-only / strategy-dependent suppression. Effective rendered sections = report-type skips ∪ total-account overlay. Agents must gather/research only sections that will render; do not collect news/events/actions/trading psychology for skipped sections.

### Section-level pipeline routing (HARD)

Before gathering editorial context, compute the effective skipped renderer set with `scripts/report_mode_policy.py`. A section can trigger data collection only if its renderer is not skipped. This table is the agent-facing source of truth for what to gather, what to skip, and which context keys are legal. The `total_account` column shows only the additional account-scope overlay; final total-account rendering is still `report_type` skips ∪ this overlay.

| Renderer / UI section | Single-account `daily_report` | Single-account `portfolio_report` | `total_account` overlay (additional; still apply report-type skips) | Pipeline trigger |
|---|---:|---:|---:|---|
| `render_masthead` / report header | Render | Render | Render | Snapshot metadata + selected axes only. `next_event` may be populated only if `render_events` renders; never search events just for the masthead. |
| `render_alerts` / Immediate Attention | Render | Skip | Skip | Daily-only Phase B from snapshot risk checks + §10.5 evidence. Triggers live research only in daily single. |
| `render_today_summary` / Today's Summary | Render | Skip | Skip | Daily-only synthesis from gathered evidence. No extra search beyond daily §10.5. |
| `render_dashboard` / Portfolio dashboard | Render | Render | Render | Snapshot math only. No news/research. |
| `render_profit_panel` / Profit Panel | Skip | Render | Render | Snapshot `profit_panel` + price/history math. No news/research. |
| `render_report_accuracy` / Report accuracy | Render | Render | Skip | Snapshot/source-quality fields + data gaps. No news/research. |
| `render_performance_attribution` / Performance Attribution | Skip | Render | Skip | Snapshot `transaction_analytics.performance_attribution`. No news/research. |
| `render_trade_quality` / Trade Quality | Render | Render | Skip | Snapshot `transaction_analytics.trade_quality`. No news/research. |
| `render_discipline_check` / Discipline Check | Skip | Render | Skip | Snapshot `transaction_analytics.discipline_check`. No news/research. |
| `render_trading_psychology` / Recent Trading Mindset | Render | Skip | Skip | Daily-only agent-authored self-coaching from `snapshot.transaction_analytics` + SETTINGS strategy. No news/event search; skip entirely for portfolio/total. |
| `render_allocation_and_weight` / Allocation & weights | Render | Render | Render | Snapshot allocation math only. No news/research. |
| `render_holdings_table` / Holdings P&L and weights | Render with Action column | Render without Action column | Render without Action column | Snapshot holdings math. The Action column may use daily `holdings_actions` / `adjustments`; portfolio/total must not author action context. |
| `render_pnl_ranking` / P&L Ranking | Skip | Render | Render | Snapshot realized/unrealized ranking only. No news/research. |
| `render_holding_period` / Holding Period and Pacing | Skip | Render | Render | Snapshot holding-period / pacing math only. No news/research. |
| `render_theme_sector` / Theme & sector exposure | Render | Render | Skip | Agent-authored classification + audit. Static issuer / ETF taxonomy or factsheet lookup is allowed when needed, but this is not §10.5 decision research: no material-news search, no event search, no `research_targets`, no `research_coverage`. |
| `render_news` / Latest Material News | Render | Skip | Skip | Daily-only §10.5 temp-researcher news workflow. Forbidden for portfolio/total. |
| `render_events` / Forward 30-Day Event Calendar | Render | Skip | Skip | Daily-only §10.5 temp-researcher events workflow. Forbidden for portfolio/total. |
| `render_high_risk_opp` / High Risk and High Opportunity | Render | Skip | Skip | Daily-only Phase B from snapshot risk heat + §10.5 decision evidence. Forbidden for portfolio/total. |
| `render_adjustments` / Recommended Adjustments | Render | Skip | Skip | Daily-only recommendations with PM fields. Requires §10.5 evidence when action depends on external developments. Forbidden for portfolio/total. |
| `render_actions` / Today's Action List | Render | Skip | Skip | Daily-only action buckets from §10.5 + strategy. Forbidden for portfolio/total. |
| `render_sources` / Sources & data gaps | Render | Render | Skip | Price/FX/data gaps, Strategy readout, reviewer summary. Include `research_coverage` / searched-ticker counts only if §10.5 rendered. Portfolio reports must omit research coverage rather than backfilling it. |

**Research trigger rule.** Run §10.5 news/events, `research_targets`, `research_coverage`, and temp-researcher delegation if and only if at least one effective rendered section is in this set: `render_news`, `render_events`, `render_high_risk_opp`, `render_adjustments`, `render_actions`, `render_alerts`, `render_today_summary`. Under the current policy this is **single-account `daily_report` only**. `portfolio_report` must not trigger news search or research.

**Context authoring by mode.**

- Single-account `daily_report`: author rendered editorial keys only: `alerts`, `today_summary`, `news`, `events`, `research_coverage`, `high_opps`, `adjustments`, `actions`, `trading_psychology`, `theme_sector_html`, `theme_sector_audit`, `strategy_readout`, `data_gaps`, `reviewer_pass`, and optional `holdings_actions`.
- Single-account `portfolio_report`: author math-adjacent / non-daily context only: `theme_sector_html`, `theme_sector_audit`, `strategy_readout`, `data_gaps`, `reviewer_pass`. Do **not** author `news`, `events`, `research_coverage`, `research_targets`, `high_opps`, `adjustments`, `actions`, `trading_psychology`, or holdings action text.
- `total_account` with either report type: context may be empty or contain only renderer-safe metadata. Do not read per-account strategies, do not author strategy-dependent editorial sections, and do not run news/events/recommendation research.

**Account readiness gate.** Single-account reports require usable settings
before Phase A; missing, empty, or template-only strategy is a setup blocker,
not a neutral-fallback case. Total/all-account reports are strategy-free but
still ledger/account-bound: stop if any real included account lacks usable
settings unless using an explicit demo/bootstrap path, and use runtime language
and base-currency prompts instead of per-account strategy.

**History fetch note.** `fetch_history.py` remains in the canonical pipeline because current snapshots compute profit panel / transaction analytics in one pass. It is math/history support, not §10.5 research, and it never authorizes news or event search for `portfolio_report`.

### Pipeline order (HARD)

The renderer (`scripts/generate_report.py`) is a **pure projection** of an
upstream snapshot — it does no aggregation, no FX conversion, no pacing /
heat scoring / special checks, and does not auto-run analytics. Every numeric
or structural field is materialized once, in this order:

1. `python scripts/fetch_prices.py --account default --output "$REPORT_RUN_DIR/prices.json"` — populates
   per-ticker latest-price metadata + `prices.json["_fx"]` (§8 + §9.0).
2. `python scripts/fetch_history.py --account default --merge-into "$REPORT_RUN_DIR/prices.json"` — adds
   `_history` + `_fx_history` for the profit-panel boundary lookups (§10.1.5).
3. `python scripts/transactions.py snapshot --account default --prices "$REPORT_RUN_DIR/prices.json"
   --output "$REPORT_RUN_DIR/report_snapshot.json"` — runs the canonical math
   (`portfolio_snapshot.compute_snapshot`): aggregates, totals, FX-converted
   market value / P&L, book pacing, risk-heat scoring, §11 special checks,
   profit panel, realized + unrealized, transaction analytics. The snapshot
   is the single source of truth for every numeric field downstream. The
   snapshot also bakes in the resolved locale and prints a `NEXT STEP
   REQUIRED` block on stderr if that locale has no built-in UI dictionary.
3.5. **UI dictionary translation (only when `SETTINGS.md` `Language:`
   resolves to a locale outside `en` / `zh-Hant` / `zh-Hans`)** — the agent
   reads `scripts/i18n/report_ui.en.json`, translates every value into the
   target language preserving keys and `{format}` placeholders, writes the
   result to `$REPORT_RUN_DIR/report_ui.<locale>.json`, and passes it to
   `generate_report.py` via `--ui-dict $REPORT_RUN_DIR/report_ui.<locale>.json`.
   Skipping this step makes `generate_report.py` exit with code **8** —
   there is no English-chrome fallback for non-English settings. See §5.1.1
   in `02-inputs-to-self-containment.md` for the full contract.
4. Agent authors `"$REPORT_RUN_DIR/report_context.json"` with editorial-only content **only for sections included by the effective report policy** (for example, single-account daily gathers news/actions/psychology; single-account portfolio skips them). The agent **must not** re-derive any numeric field that the snapshot already exposes. The context must be linted with:

   ```bash
   python scripts/validate_report_context.py \
       --snapshot "$REPORT_RUN_DIR/report_snapshot.json" \
       --context "$REPORT_RUN_DIR/report_context.json" \
       --report-type daily_report
   ```

   Replace `daily_report` with `portfolio_report` as selected. For total scope, use `--all-accounts` / `--account-scope total_account`; total scope intentionally skips strategy-dependent editorial validation.
5. `python scripts/generate_report.py --account default --report-type daily_report --snapshot "$REPORT_RUN_DIR/report_snapshot.json"
   --context "$REPORT_RUN_DIR/report_context.json"` — projects the
   snapshot + context onto the §10 HTML. (Omitting `--account` resolves the active account
   from `accounts/.active`; pass `--account <name>` to target a specific account.)

The renderer's legacy `--prices --db` path remains for backwards compatibility
but emits a deprecation warning; new agent runs must use `--snapshot`.

### Total / All-Accounts scope (§N)

**Trigger phrases.** "Total report", "all-accounts report", "portfolio across
all my accounts", "consolidated report". The agent must still choose `--report-type daily_report` or `--report-type portfolio_report`; "total" only means account scope.

**What it does.** Unions every real account under `accounts/<name>/` (filtered by `NAME_REGEX`; underscore-prefixed sinks like `_total` are skipped) and then applies the selected report type plus the total-account math-only overlay. Editorial/strategy-dependent sections are excluded by construction.

**Runtime prompts (agent → user).**
1. Language — default `en`; restricted to `en` / `zh-Hant` / `zh-Hans`. ja /
   vi / ko require a translated `--ui-dict` JSON (deferred D8).
2. Base currency — default `USD`. Overrides any per-account SETTINGS.
3. Strategy is **not** prompted — strategy lives in per-account SETTINGS and
   is intentionally excluded from the total report (D3).

**Pipeline (literal four-command sequence).**

```bash
RUN="$(date +%Y%m%d_%H%M)"
RUN_DIR="/tmp/investments_portfolio_report_${RUN}"
mkdir -p "$RUN_DIR"

python scripts/fetch_prices.py --all-accounts \
    --output "$RUN_DIR/prices.json" [--skip-yfinance]

python scripts/fetch_history.py --all-accounts \
    --merge-into "$RUN_DIR/prices.json" \
    [--cache market_data_cache.db]

python scripts/transactions.py snapshot --all-accounts --base-currency USD \
    --prices "$RUN_DIR/prices.json" \
    --output "$RUN_DIR/report_snapshot.json" \
    --today $(date +%Y-%m-%d)

python scripts/generate_report.py --snapshot "$RUN_DIR/report_snapshot.json" \
    --report-type daily_report \
    --all-accounts --language en
# Output defaults to accounts/_total/reports/<YYYY-MM-DD_HHMM>_total_account_daily_report.html
```

After success, `rm -rf "$RUN_DIR"`.

**Output path.** When `--output` is omitted, the renderer writes to
`accounts/_total/reports/<YYYY-MM-DD_HHMM>_total_account_<report_type>.html`. The
`accounts/_total/` directory holds **only** reports — there is no SETTINGS.md
or transactions.db; `account list` does not show it.

**Mutually exclusive with `--account NAME`.** Passing both on any of the
four pipeline scripts (`fetch_prices.py`, `fetch_history.py`,
`transactions.py snapshot`, `generate_report.py`) emits an argparse error
and exits non-zero. `generate_report.py` also rejects omitted `--report-type` on render paths.

**Exit codes.** `2` = mutex / invalid combo (e.g., `--all-accounts --db`).
`4` = no real accounts under `accounts/`. `7` is **not** raised in total
mode (the `validate_report_context` gate is bypassed; editorial fields are
intentionally absent). `8` cannot be raised because the language is
constrained to built-in locales by argparse.

**Single-account equivalence (AC#8).** When only one real account exists,
`--all-accounts` produces a snapshot byte-equivalent to `--account <that
one>` (modulo `generated_at`). This is a structural invariant — both paths
share `_compute_snapshot_core` in `scripts/portfolio_snapshot.py`.

Smoke test: `tests/smoke_total_account.sh` exercises every assertion above
on a synthetic 3-account fixture under `/tmp/`.

### Demo ledger for report generation

To exercise the **same pipeline** without reading or writing the user’s active-account
`transactions.db`, use **`demo/`**: seed `demo/transactions_history.json` →
`demo/transactions.db` via `python demo/bootstrap_demo_ledger.py --apply`.
There is no demo report pipeline script and no committed demo editorial JSON; context is authored per run under `$REPORT_RUN_DIR` like production and only for sections rendered by the selected report type / account scope.
The demo ledger is an **alternate `--db` path** plus **alternate history cache**:
run the normal portfolio-report workflow, pass **`--db demo/transactions.db`**
to `fetch_prices.py`, `fetch_history.py`, and `transactions.py snapshot`, and
pass **`--cache demo/market_data_cache.db`** to **`fetch_history.py` and
`fill_history_gap.py`** so demo fetches do not read or write the root
`market_data_cache.db`. (Do not use `--account` for demo runs; the explicit `--db`/`--settings` path is the intentional escape hatch.) Then author the context from the snapshot, latest
public data, `SETTINGS.md`, and these guidelines exactly as for a production
report. Prefer writing deliverable demo HTML under **`demo/reports/`** (same
filename pattern) instead of `reports/` so user production reports stay
separated. Only the transaction ledger is synthetic; price retrieval, FX,
history, snapshot math, analytics, section-gated editorial context, reviewer pass,
and HTML rendering must all be real run outputs. For demo `portfolio_report`
runs, the same portfolio rule applies: no news, catalysts, `trading_psychology`,
consensus, recommendations, actions, or §10.5 temp-researcher workflow.

## Section Links

0. [Critical references — read first](./portfolio_report_agent_guidelines/01-critical-references-to-glossary.md#0-critical-references--read-first)
1. [Trigger phrases & scope](./portfolio_report_agent_guidelines/01-critical-references-to-glossary.md#1-trigger-phrases--scope)
2. [Execution procedure (canonical order)](./portfolio_report_agent_guidelines/01-critical-references-to-glossary.md#2-execution-procedure-canonical-order)
3. [Glossary](./portfolio_report_agent_guidelines/01-critical-references-to-glossary.md#3-glossary)
4. [Inputs](./portfolio_report_agent_guidelines/02-inputs-to-self-containment.md#4-inputs) (includes §4.4 demo ledger)
5. [Output language (HARD)](./portfolio_report_agent_guidelines/02-inputs-to-self-containment.md#5-output-language-hard)
6. [File output](./portfolio_report_agent_guidelines/02-inputs-to-self-containment.md#6-file-output)
7. [Self-containment rules](./portfolio_report_agent_guidelines/02-inputs-to-self-containment.md#7-self-containment-rules)
8. [Latest-price retrieval pipeline](./portfolio_report_agent_guidelines/03-latest-price-retrieval.md#8-latest-price-retrieval-pipeline)
9. [Computations & missing-value glyphs](./portfolio_report_agent_guidelines/04-computations-to-static-snapshot.md#9-computations--missing-value-glyphs)
10. [Required report sections](./portfolio_report_agent_guidelines/04-computations-to-static-snapshot.md#10-required-report-sections)
11. [Per-run special checks](./portfolio_report_agent_guidelines/04-computations-to-static-snapshot.md#11-per-run-special-checks)
12. [Static latest-price snapshot rules](./portfolio_report_agent_guidelines/04-computations-to-static-snapshot.md#12-static-latest-price-snapshot-rules)
13. [Cell popovers (Symbol & Price)](./portfolio_report_agent_guidelines/05-cell-popovers.md#13-cell-popovers-symbol--price)
14. [Visual design standard](./portfolio_report_agent_guidelines/06-visual-design.md#14-visual-design-standard)
15. [Investment content standard](./portfolio_report_agent_guidelines/07-investment-content-and-checklist.md#15-investment-content-standard)
16. [Reply format to user](./portfolio_report_agent_guidelines/07-investment-content-and-checklist.md#16-reply-format-to-user)
17. [Appendix A — Pre-delivery self-check](./portfolio_report_agent_guidelines/07-investment-content-and-checklist.md#appendix-a--pre-delivery-self-check)

## Section Map

- `00-preface-and-toc.md`: title, preface, README language links, table of contents
- `01-critical-references-to-glossary.md`: §§0-3
- `02-inputs-to-self-containment.md`: §§4-7
- `03-latest-price-retrieval.md`: §8
- `04-computations-to-static-snapshot.md`: §§9-12
- `05-cell-popovers.md`: §13
- `06-visual-design.md`: §14
- `07-investment-content-and-checklist.md`: §§15-16 and Appendix A

## Usage Rule

When a workflow or another doc says to read `/docs/portfolio_report_agent_guidelines.md`, read this entrypoint and then the complete required bundle above. Partial reading is allowed only as a paging method; the effective read set is the full bundle.
