# Portfolio Report Agent Guidelines

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

- Execute in four serial phases: **A Gather → B Think → C Review → D Render + reply**.
- Phase A gathers files, prices, metrics, full-universe news, dated catalysts, and follow-up research before any judgment is drafted.
- Phase B drafts all alerts, watchlists, adjustments, action items, scoring, mandatory `trading_psychology`, Strategy readout, and summary while continuously anchoring to `SETTINGS.md` `## Investment Style And Strategy`.
- Phase C switches hat to a senior PM reviewer, annotates issues, reviews `trading_psychology`, and sends serious defects back to the relevant earlier phase before render.
- Phase D renders one self-contained HTML file only after `scripts/validate_report_context.py --snapshot report_snapshot.json --context report_context.json` passes, runs Appendix A self-checks, removes temp files, and replies with the absolute path plus required audit notes.
- `SETTINGS.md` and `transactions.db` are read-only unless the user explicitly asks to edit them.

### Pipeline order (HARD)

The renderer (`scripts/generate_report.py`) is a **pure projection** of an
upstream snapshot — it does no aggregation, no FX conversion, no pacing /
heat scoring / special checks, and does not auto-run analytics. Every numeric
or structural field is materialized once, in this order:

1. `python scripts/fetch_prices.py --output prices.json` — populates
   per-ticker latest-price metadata + `prices.json["_fx"]` (§8 + §9.0).
2. `python scripts/fetch_history.py --merge-into prices.json` — adds
   `_history` + `_fx_history` for the profit-panel boundary lookups (§10.1.5).
3. `python scripts/transactions.py snapshot --prices prices.json
   --output report_snapshot.json` — runs the canonical math
   (`portfolio_snapshot.compute_snapshot`): aggregates, totals, FX-converted
   market value / P&L, book pacing, risk-heat scoring, §11 special checks,
   profit panel, realized + unrealized, transaction analytics. The snapshot
   is the single source of truth for every numeric field downstream.
4. Agent authors `report_context.json` with editorial-only content (news,
   events, alerts, adjustments, action list, theme/sector HTML,
   `trading_psychology`, Strategy readout, reviewer notes). The agent **must
   not** re-derive any numeric field that the snapshot already exposes. The
   entire context must be linted with `python scripts/validate_report_context.py
   --snapshot report_snapshot.json --context report_context.json` before render.
5. `python scripts/generate_report.py --snapshot report_snapshot.json
   --context report_context.json --settings SETTINGS.md` — projects the
   snapshot + context onto the §10 HTML.

The renderer's legacy `--prices --db` path remains for backwards compatibility
but emits a deprecation warning; new agent runs must use `--snapshot`.

### Demo ledger for report generation

To exercise the **same pipeline** without reading or writing the user’s root
`transactions.db`, use **`demo/`**: seed `demo/transactions_history.json` →
`demo/transactions.db` via `python demo/bootstrap_demo_ledger.py --apply`.
There is no demo report pipeline script and no demo `report_context.json`.
The demo ledger is an **alternate `--db` path** only: run the normal
portfolio-report workflow, pass **`--db demo/transactions.db`** to
`fetch_prices.py`, `fetch_history.py`, and `transactions.py snapshot`, then
author the context from the snapshot, latest public data, `SETTINGS.md`, and
these guidelines exactly as for a production report. Only the transaction
ledger is synthetic; price retrieval, FX, history, snapshot math, analytics,
mandatory `trading_psychology`, theme/sector classification, news, catalysts,
consensus, recommendations, reviewer pass, and HTML rendering must all be real
run outputs.

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
