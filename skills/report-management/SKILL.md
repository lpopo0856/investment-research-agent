---
name: report-management
description: Generate daily_report or portfolio_report HTML through the canonical portfolio-report pipeline. Use when the user asks to generate/run a daily report, portfolio report, all-accounts/consolidated/total report, or demo report; enforce report-type selection, /tmp intermediates, snapshot-first pipeline, context validation, and section routing.
---

# Report Management

## Core Rule

This skill is the report-generation gate. It does not replace the report spec: before any report run, read `docs/portfolio_report_agent_guidelines.md` and every numbered file under `docs/portfolio_report_agent_guidelines/` in order, including `docs/portfolio_report_agent_guidelines/07-investment-content-and-checklist.md`. Existing generated HTML is never a shortcut or data source.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.

## Trigger Boundary

Use this skill when the user asks for a generated report, for example:

- daily report / today's report / decision report
- portfolio report / position review / math report
- all-accounts, consolidated, total report
- demo report

If the user asks only what is possible, route to `skills/investment-help/SKILL.md`. If the user asks for ad hoc ticker or market research without an HTML deliverable, use `skills/investment-analysis/SKILL.md` instead.

## Required Type And Scope Gate

Choose both axes before Phase A:

1. `report_type`: exactly `daily_report` or `portfolio_report`.
2. account scope: a named account, the resolved active/default account for ordinary single-account requests, or all accounts only when the user explicitly asks for total/consolidated/all-accounts scope.

If the user asks to generate a report but does not clearly specify `daily_report` or `portfolio_report`, stop before Phase A. Do not create `REPORT_RUN_DIR`, fetch prices, read account data, run account migration, or start live research. Ask one concise question explaining:

- `daily_report`: daily decision/editorial report with alerts, news/events, risks/opportunities, recommended adjustments, today's actions, trading psychology, and holdings Action text when single-account.
- `portfolio_report`: math/position review that omits immediate-attention, news/events, actions, trading psychology, recommendations, and holdings Action text.

`total`, `all-accounts`, and `consolidated` are scope words, not a third report type. If the report type is clear and scope is not, resolve the active/default account and proceed as single-account scope; do not ask the user to choose a flag.

## Layout And File-Safety Gate

Before any account-reading report script, run:

```bash
python scripts/transactions.py account detect
```

If it prints `partial`, hard stop and route to onboarding/account reconciliation. If it prints `migrate`, do not repair layout inside the report lane; route to onboarding/account-management before report generation. Do not edit protected account files or ledgers during report generation.

All intermediates must live under one fresh `/tmp` directory:

```bash
export REPORT_RUN_DIR="/tmp/investments_portfolio_report_$(date +%Y%m%d_%H%M)"
mkdir -p "$REPORT_RUN_DIR"
```

Write `prices.json`, merged history, `report_snapshot.json`, `report_context.json`, optional UI dictionaries, and gap-fill merge targets only under `$REPORT_RUN_DIR`. After successful render and checks, delete it:

```bash
rm -rf "$REPORT_RUN_DIR"
```

## Canonical Single-Account Pipeline

Replace `<name>` and `<daily_report|portfolio_report>` with the selected axes:

```bash
python scripts/fetch_prices.py --account <name> --output "$REPORT_RUN_DIR/prices.json"
python scripts/fetch_history.py --account <name> --merge-into "$REPORT_RUN_DIR/prices.json"
python scripts/transactions.py snapshot --account <name> --prices "$REPORT_RUN_DIR/prices.json" --output "$REPORT_RUN_DIR/report_snapshot.json"
python scripts/validate_report_context.py --snapshot "$REPORT_RUN_DIR/report_snapshot.json" --context "$REPORT_RUN_DIR/report_context.json" --report-type <daily_report|portfolio_report>
python scripts/generate_report.py --report-type <daily_report|portfolio_report> --account <name> --snapshot "$REPORT_RUN_DIR/report_snapshot.json" --context "$REPORT_RUN_DIR/report_context.json"
```

For total scope, use the same pipeline with `--all-accounts` instead of `--account <name>` on compatible commands, and pass total-scope options exactly as required by the report spec. Do not combine `--all-accounts` with `--account <name>`.

## History Gap Loop

`fetch_history.py` is math/history support, not news research. If it exits with structured gap code 5, fill only market-history gaps with the canonical helper, merge into the same prices file, then re-run history fetch:

```bash
python scripts/fill_history_gap.py
```

Include the gap-specific arguments from the structured gap list and `--merge-into "$REPORT_RUN_DIR/prices.json"`. Do not use `--allow-incomplete` for a deliverable report.

## Context Authoring By Report Type

Run `scripts/report_mode_policy.py` or the report spec's section table before authoring context. Author only keys for sections that render.

- Single-account `daily_report`: may author daily/editorial keys (`alerts`, `today_summary`, `news`, `events`, `research_coverage`, `high_opps`, `adjustments`, `actions`, `trading_psychology`, theme/sector audit, strategy readout, data gaps, reviewer notes, and optional holdings actions). Use temp-researcher/context-drop rules for research-heavy §10.5 work.
- Single-account `portfolio_report`: math/position only. `portfolio_report` must not author or trigger `news`, `events`, `research_coverage`, `research_targets`, `high_opps`, `adjustments`, `actions`, `trading_psychology`, or holdings Action text.
- Total scope: keep context empty or renderer-safe only; do not read per-account strategies, do not run news/events/recommendation research, and do not author strategy-dependent editorial sections.

Always validate context before rendering with `validate_report_context.py`; never re-derive numeric fields already present in the snapshot.

## Demo Reports

For demo reports, use only the isolated demo ledger:

```bash
python demo/bootstrap_demo_ledger.py --apply
```

Then run the normal report pipeline using `--db demo/transactions.db` for ledger-reading steps and `--cache demo/market_data_cache.db` for `fetch_history.py` and `fill_history_gap.py`. Prefer final HTML under `demo/reports/`. Never point demo bootstrap at production data. Demo `portfolio_report` follows the same no news / no actions / no trading psychology rule.

## Stop Conditions

Stop and report the blocker when:

- report type is unspecified;
- account detect returns `partial` or layout needs migration before report work;
- history gaps cannot be filled without `--allow-incomplete`;
- context validation fails;
- a step would write intermediates outside `/tmp` or edit protected account files;
- a `portfolio_report` path starts to gather news, events, recommendations, actions, or trading psychology.
