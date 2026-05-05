---
name: onboarding
description: Route new-user setup, legacy-layout migration, statement extraction, and first ledger import through the repo's canonical onboarding contracts. Use when SETTINGS.md or transactions.db/account files are missing, the user asks to get started/onboard/import a statement, or an agent needs the safe setup path without absorbing the full onboarding, settings, or transaction docs.
---

# Onboarding

## Core Rule

Onboarding is a router, not an absorber. Follow `docs/onboarding_agent_guidelines.md` end to end, and route specialist work to `docs/settings_agent_guidelines.md` for settings/strategy and `docs/transactions_agent_guidelines.md` for ledger imports. Do not duplicate or improvise those workflows inside this skill.

Onboarding is mandatory before account-sensitive work when no account is safely
resolvable or the target account lacks usable settings. Account creation may
scaffold `SETTINGS.md` from `SETTINGS.example.md`, but that scaffold is not
completed user settings until the settings workflow has collected or confirmed
Account description, Language, Investment Style And Strategy, and Base
currency. Other account-sensitive skills must route here/settings first in that
state.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.

## Environment Preflight

For new-user onboarding, the agent owns the technical setup check. Do not send the user to README for Python or package installation steps.

Run a lightweight environment check before account/layout work:

```bash
python3 --version
python3 - <<'PY'
import importlib.util
missing = [m for m in ("requests", "yfinance") if importlib.util.find_spec(m) is None]
print(",".join(missing) if missing else "ok")
PY
```

If Python is missing or older than 3.11, stop before account work and ask in natural language whether the user wants you to try installing or updating Python 3.11+ for them. Because this is a system-level change, require an explicit same-turn `yes` before attempting it. If confirmed, use the safest available local installer/package manager for the platform; if no safe installer is available or installation fails, report the blocker and explain that Python 3.11+ is needed before onboarding can continue. Do not invent credentials or bypass OS prompts.

If Python is usable and only dependencies are missing, install the small runtime dependency set yourself:

```bash
python3 -m pip install yfinance requests
```

If dependency installation fails, report the blocker and continue only with workflow parts that do not require the missing dependency. Do not ask the user to run pip commands unless execution is blocked by local permissions or they explicitly ask for manual CLI instructions.

## Layout Preflight Gate

Before any script reads `SETTINGS.md` or `transactions.db`, run the C-8 layout preflight:

```bash
python scripts/transactions.py account detect
```

Act only on the detector state:

- `migrate`: run migration through the canonical command, then continue only after it succeeds:

```bash
python scripts/transactions.py account migrate --yes
```

- `clean`: do not migrate; continue with the active/default account workflow when one exists, or scaffold the requested first account through the gated account/onboarding path.
- `demo_only_at_root`: do not migrate; treat demo assets as isolated demo inputs.
- `partial`: hard stop; follow the reconciliation path in `docs/onboarding_agent_guidelines.md` before doing anything else.

Never run `python scripts/transactions.py account migrate --yes` unless `account detect` printed exactly `migrate` in the same workflow.

## Routing Workflow

0. Run the environment preflight above.
1. Detect account state with `python scripts/transactions.py account detect`.
2. If an account must be created, accept the user's framing for the name — accounts are separate ledgers and can be split by person (self / spouse / a kid's college fund), goal (retirement / house / emergency), strategy (core / satellite / speculative), tax bucket (taxable / tax-advantaged), or stock market (Taiwan / US / Japan). The canonical framing lives in `skills/account-management/SKILL.md` under "Account Concept". Do not rewrite a person/goal/strategy name into a market label. Then use the canonical scaffold command:

```bash
python scripts/transactions.py account create <name>
```

3. For account description, language, base currency, time zone, or strategy text, switch to `docs/settings_agent_guidelines.md`. Bootstrap from `SETTINGS.example.md` only as a local scaffold/default source under that settings workflow, not as completed account settings, and keep its diff-confirm gate.
4. For trades, cash, broker CSV/JSON, or converted statement imports, switch to `docs/transactions_agent_guidelines.md`. Keep the transaction confirmation, backup, and verify gates.
5. After onboarding verification, stop at the user's completed setup state. Do not immediately offer report generation; wait for a separate report request.

## Statement Extraction Discipline

Keep all extraction intermediates under `/tmp`, never in the repo tree. For large statements, screenshots, PDFs, or broker files whose extraction would create large tool output, delegate extraction to a temp-researcher per `docs/context_drop_protocol.md` / `docs/temp_researcher_contract.md`; the temp-researcher returns only a result file path, short summary, and audit.

Write normalized import JSON to `/tmp/onboarding_<broker>_<timestamp>.json` and show a sample plus resulting state preview before any insert/import.

## Batch Import Confirmation Gate

Before any onboarding import writes to the ledger, show:

1. Parsed trades / cash flows.
2. Write plan and target account.
3. Exact canonical JSON blob for small batches, or `/tmp` JSON path plus sample for large batches.
4. Resulting state preview.
5. SELL realized P&L when relevant.
6. Literal prompt: `Confirm and write? (yes / no / edit)`.

Only after explicit same-turn `yes`, use the canonical transaction import path from `docs/transactions_agent_guidelines.md`, back up first when required, then verify with:

```bash
python scripts/transactions.py verify --account <name>
```

On verify failure, roll back from backup and report the mismatch.
