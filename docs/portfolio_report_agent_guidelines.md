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
- Phase B drafts all alerts, watchlists, adjustments, action items, scoring, Strategy readout, and summary while continuously anchoring to `SETTINGS.md` `## Investment Style And Strategy`.
- Phase C switches hat to a senior PM reviewer, annotates issues, and sends serious defects back to the relevant earlier phase before render.
- Phase D renders one self-contained HTML file, runs Appendix A self-checks, removes temp files, and replies with the absolute path plus required audit notes.
- `SETTINGS.md` and `HOLDINGS.md` are read-only unless the user explicitly asks to edit them.

## Section Links

0. [Critical references — read first](./portfolio_report_agent_guidelines/01-critical-references-to-glossary.md#0-critical-references--read-first)
1. [Trigger phrases & scope](./portfolio_report_agent_guidelines/01-critical-references-to-glossary.md#1-trigger-phrases--scope)
2. [Execution procedure (canonical order)](./portfolio_report_agent_guidelines/01-critical-references-to-glossary.md#2-execution-procedure-canonical-order)
3. [Glossary](./portfolio_report_agent_guidelines/01-critical-references-to-glossary.md#3-glossary)
4. [Inputs](./portfolio_report_agent_guidelines/02-inputs-to-self-containment.md#4-inputs)
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
