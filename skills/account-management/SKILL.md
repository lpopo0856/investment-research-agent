---
name: account-management
description: Manage the repo's multi-account layout safely by classifying account commands as read-only, write-capable/gated, or forbidden. Use when detecting layout state, listing accounts, switching active account, creating an account, or migrating a legacy root layout; enforce detector-state gates from onboarding and transaction docs.
---

# Account Management

## Account Concept

Accounts are separate ledgers — a bookkeeping container, not a market label. Users split them however suits their record-keeping: by person (self, spouse, a kid's college fund), by goal (retirement, house, emergency cash), by strategy (core, satellite, speculative), by tax bucket (taxable, tax-advantaged), or by stock market (Taiwan, US, Japan). Treat all of these as equally valid framings — do not assume a market-based split. When the user names a new account ("open an account for my spouse", "add a college fund ledger", "create a satellite strategy account"), accept their framing and create the account under that label; do not rewrite a person- or goal- or strategy-based name into a market label, and do not require the user to justify their split.

## Core Rule

Account management changes repository layout and active-account resolution.
Follow `docs/onboarding_agent_guidelines.md` and
`docs/transactions_agent_guidelines.md`; classify side effects before every
command. Creating an account is a bootstrap step only: any `SETTINGS.md`
created from `SETTINGS.example.md` is a scaffold/draft until the settings
workflow collects or confirms the required account settings.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.


## Side-Effect Taxonomy

### Read-only / safe

These commands inspect state and are safe to run as preflight evidence:

```bash
python scripts/transactions.py account detect
python scripts/transactions.py account list
python scripts/transactions.py account --help
```

`account list` may display each account's optional `SETTINGS.md` account
description as a short purpose label. Treat that as read-only metadata for
orientation; changing it is a settings-management edit and requires that
workflow's diff-confirm gate.

### Write-capable / gated

These commands write files and require the relevant workflow gate:

```bash
python scripts/transactions.py account use <name>
python scripts/transactions.py account create <name>
python scripts/transactions.py account migrate --yes
```

- `python scripts/transactions.py account use <name>` writes `accounts/.active`; run it only when switching active account is the user's requested outcome.
- `python scripts/transactions.py account create <name>` scaffolds account
  files and initializes that account's DB; use it only after confirming the
  desired account name and creation intent. The copied settings file is not
  usable account settings until `skills/settings-management/SKILL.md` has
  collected or confirmed Account description, Language, Investment Style And
  Strategy, and Base currency.
- `python scripts/transactions.py account migrate --yes` migrates a legacy root layout; run it only when `python scripts/transactions.py account detect` printed exactly `migrate` in the same workflow.

### Forbidden without explicit user-approved workflow

- Destructive file surgery outside canonical scripts.
- Any migration on `clean`, `demo_only_at_root`, or `partial` detector states.
- Manual moves/deletes of `SETTINGS.md`, `transactions.db`, account directories, or `accounts/.active` when a canonical command exists.

## Detector-State Rules

Run first:

```bash
python scripts/transactions.py account detect
```

Then apply the exact state gate:

- `clean`: do not migrate.
- `demo_only_at_root`: do not migrate.
- `partial`: hard stop; follow onboarding reconciliation before any write-capable command.
- `migrate`: migration is allowed through only this command:

```bash
python scripts/transactions.py account migrate --yes
```

Run migration only when detect prints exactly migrate. Never infer migration from file names or stale notes; the same-run detector output controls the decision.

## Verification After Writes

After `account create`, inspect account state with:

```bash
python scripts/transactions.py account list
python scripts/transactions.py verify --account <name>
```

After `account use`, confirm the active account through `python scripts/transactions.py account list` and report that `accounts/.active` changed by request. After migration, follow `docs/onboarding_agent_guidelines.md` verification and stop immediately on any mismatch.

After account creation, guide the user to settings completion before any account-sensitive workflow treats the new account as ready. Safe account detection/listing remains allowed as bootstrap evidence.
