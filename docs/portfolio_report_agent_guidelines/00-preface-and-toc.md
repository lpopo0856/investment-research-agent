# Portfolio Report Agent Guidelines

> The portfolio report in this repo is the **final deliverable**, not a frontend project.
> Do not break the user-facing report into multiple executable scripts or external resources.
> This spec is the single source of truth for any "portfolio health check" / "portfolio report" run.
> When invoked, follow it end-to-end, top-to-bottom.

**README languages** · [English](../README.md) · [繁體中文](l10n/README.zh-Hant.md) · [简体中文](l10n/README.zh-Hans.md) · [日本語](l10n/README.ja.md) · [Tiếng Việt](l10n/README.vi.md) · [한국어](l10n/README.ko.md) (canonical overview: English; this spec is English-only.)

---

## Table of contents

0. [Critical references — read first](#0-critical-references--read-first)
1. [Trigger phrases & scope](#1-trigger-phrases--scope)
2. [Execution procedure (canonical order)](#2-execution-procedure-canonical-order)
3. [Glossary](#3-glossary)
4. [Inputs](#4-inputs)
5. [Output language (HARD)](#5-output-language-hard)
6. [File output](#6-file-output)
7. [Self-containment rules](#7-self-containment-rules)
8. [Latest-price retrieval pipeline](#8-latest-price-retrieval-pipeline)
9. [Computations & missing-value glyphs](#9-computations--missing-value-glyphs)
10. [Required report sections](#10-required-report-sections)
11. [Per-run special checks](#11-per-run-special-checks)
12. [Static latest-price snapshot rules](#12-static-latest-price-snapshot-rules)
13. [Cell popovers (Symbol & Price)](#13-cell-popovers-symbol--price)
14. [Visual design standard](#14-visual-design-standard)
15. [Investment content standard](#15-investment-content-standard)
16. [Reply format to user](#16-reply-format-to-user)
17. [Appendix A — Pre-delivery self-check](#appendix-a--pre-delivery-self-check)

---

