---
name: investment-analysis
description: Produce ad hoc stock, ETF, crypto, market, sector, or portfolio investment analysis without generating an HTML report. Use when the user asks what to buy/sell/hold, asks for a ticker or market view, compares investment ideas, or wants portfolio-level judgment; enforce SETTINGS strategy binding, latest public data, consensus/variant/anchor discipline, R:R, kill criteria, portfolio fit, and reviewer pass.
---

# Investment Analysis

## Core Rule

This skill covers investment research and recommendations that do not produce an HTML report. For HTML deliverables, route to `skills/report-management/SKILL.md`. For ledger, account, or settings changes, route to the matching management skill; this skill must not edit `SETTINGS.md`, `transactions.db`, reports, or account state; do not edit `SETTINGS.md` or `transactions.db` from this skill.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.

## Trigger Boundary

Use this skill for:

- single-name stock / ETF / crypto / market / sector analysis;
- “should I buy/sell/hold/add/trim?” questions;
- comparison of investment ideas;
- portfolio-level judgment without report generation;
- watchlist, thesis, catalyst, valuation, or risk/reward questions.

If the user asks for a generated report, stop this skill and use `skills/report-management/SKILL.md`.

## Strategy And Account Context

Ad hoc investment analysis is account-bound by default. Before making any personalized judgment, recommendation, sizing, portfolio-fit statement, risk call, buy/sell/hold answer, or thesis action, resolve the target account through the multi-account preflight. If the user did not name an account, use the current active account; if no active pointer exists but `default` is safely available, use `default`. Stop on `partial` or unresolved account state.

Internal preflight contract:

```bash
python scripts/transactions.py account detect
```

Then read the resolved account `SETTINGS.md`, especially the full `## Investment Style And Strategy`, and load enough current portfolio/ledger context to judge fit: holdings, cash/rails where available, concentration, correlated themes, and existing exposure to the idea. Internalize temperament, drawdown tolerance, sizing approach, holding-period bias, entry discipline, contrarian appetite, hype tolerance, off-limits zones, and language/tone.

If no account is safely resolvable, or the target account is missing usable
settings, stop before personalized analysis and guide the user to
onboarding/settings completion first. Usable settings means the settings
workflow has collected or confirmed the required cold-start fields, not merely
that `SETTINGS.example.md` was copied into place. You may still provide
generic/non-personalized research, clearly labeled as generic market
education/news, but do not answer account-bound buy/sell/hold, sizing,
portfolio-fit, or risk questions until onboarding/settings are complete.

Only skip account context when the user explicitly asks for generic market education/news or non-personalized background. If a generic answer turns into “should I buy/sell/hold/add/trim?” or “fit for me?”, resolve the account before answering.

Write in first person as the user making their own capital-allocation decision, not as a sell-side narrator.

## Research Standard

Use latest public information when any fact may have changed. Browse for current prices, filings, earnings/guidance, consensus estimates, industry/policy/catalysts, valuation, technicals, flows, and material news. Prefer primary/official sources for hard facts and named consensus providers or cited public consensus where available.

If the question is tactical, classify the state as `act_now`, `wait`, `exit`, or `need_data`. For mid/long-term questions, state thesis status and strategic fit. Mark source gaps explicitly.

## Output Contract

Use the user's language when known. Keep the note concise but decision-grade:

1. **Bottom line first** — direction, conviction, horizon, recommended size in pp of NAV, cheap/fair/rich, and the one-sentence judgment.
2. **Consensus / Variant / Anchor** — state public consensus; state our view as `variant`, `contrarian`, or `consensus-aligned`; cite the verifiable anchor. If public consensus is unavailable, write `unknown-consensus`; if the anchor is weak or unverifiable, downgrade to `consensus-aligned`.
3. **Market state and fundamentals** — latest price/action, material news, revenue/margins/EPS/FCF, balance sheet, guidance, moat, and earnings quality as applicable.
4. **Valuation and trend** — relevant multiples vs history/peers, base/bull/bear bands when giving targets, industry/secular trend, and technical/momentum read.
5. **Catalyst path** — dated 3/6/12-month catalysts where available; mark what confirms or invalidates the thesis.
6. **R:R and Kill** — format reward-to-risk from the base target and kill price/event; pre-commit kill trigger and kill action. No orphan stops.
7. **Portfolio fit** — size as pp of NAV, correlation/theme overlap, concentration/rails pressure, and whether a trim is needed to fund the idea.
8. **Operating playbook** — buy zone, scale-in/add conditions, take-profit conditions, and stop/kill that matches the kill criteria.
9. **Reviewer pass** — before finalizing, switch to senior-PM reviewer and annotate sizing, anchor, kill, concentration, data-gap, or persona-drift issues. Empty review is acceptable.
10. **Final verdict** — buy now / wait / hold / add / sell, sized at the same pp of NAV, and top variables to track.

## Decision Discipline

Bias to action only when asymmetry exists; otherwise recommend wait/cash. Empty action lists are preferred over filler. Never fabricate consensus numbers, citations, anchors, prices, holdings, or rails. If data is insufficient, say what would sharpen the call.

For detailed report-specific rendering, Strategy readout placement, canonical R:R strings, reviewer-note shape, and Appendix checks, see `docs/portfolio_report_agent_guidelines/07-investment-content-and-checklist.md`; do not generate report JSON or HTML from this skill.
