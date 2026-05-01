# Portfolio Report Agent Guidelines — Preface

**README languages** · [English](../../README.md) · [繁體中文](../l10n/README.zh-Hant.md) · [简体中文](../l10n/README.zh-Hans.md) · [日本語](../l10n/README.ja.md) · [Tiếng Việt](../l10n/README.vi.md) · [한국어](../l10n/README.ko.md) (canonical overview: English; this spec is English-only.)

## Execution Contract

- The portfolio report HTML under `reports/` is the final deliverable; pipeline JSON stays under `/tmp` in `$REPORT_RUN_DIR` and is deleted after success (main guidelines — Intermediate files). This is not a frontend project.
- Do not split the user-facing report into executable scripts, external CSS, external JS, external chart libraries, or runtime data fetches.
- This spec is the single source of truth for any "portfolio health check" / "portfolio report" run.
- Follow the required bundle from [`../portfolio_report_agent_guidelines.md`](../portfolio_report_agent_guidelines.md) end-to-end, in order.

## Table Of Contents

0. [Critical references — read first](01-critical-references-to-glossary.md#0-critical-references--read-first)
1. [Trigger phrases & scope](01-critical-references-to-glossary.md#1-trigger-phrases--scope)
2. [Execution procedure (canonical order)](01-critical-references-to-glossary.md#2-execution-procedure-canonical-order)
3. [Glossary](01-critical-references-to-glossary.md#3-glossary)
4. [Inputs](02-inputs-to-self-containment.md#4-inputs)
5. [Output language (HARD)](02-inputs-to-self-containment.md#5-output-language-hard)
6. [File output](02-inputs-to-self-containment.md#6-file-output)
7. [Self-containment rules](02-inputs-to-self-containment.md#7-self-containment-rules)
8. [Latest-price retrieval pipeline](03-latest-price-retrieval.md#8-latest-price-retrieval-pipeline)
9. [Computations & missing-value glyphs](04-computations-to-static-snapshot.md#9-computations--missing-value-glyphs)
10. [Required report sections](04-computations-to-static-snapshot.md#10-required-report-sections)
11. [Per-run special checks](04-computations-to-static-snapshot.md#11-per-run-special-checks)
12. [Static latest-price snapshot rules](04-computations-to-static-snapshot.md#12-static-latest-price-snapshot-rules)
13. [Cell popovers (Symbol & Price)](05-cell-popovers.md#13-cell-popovers-symbol--price)
14. [Visual design standard](06-visual-design.md#14-visual-design-standard)
15. [Investment content standard](07-investment-content-and-checklist.md#15-investment-content-standard)
16. [Reply format to user](07-investment-content-and-checklist.md#16-reply-format-to-user)
17. [Appendix A — Pre-delivery self-check](07-investment-content-and-checklist.md#appendix-a--pre-delivery-self-check)
