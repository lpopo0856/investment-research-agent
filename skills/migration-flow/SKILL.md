---
name: migration-flow
description: Safely migrate legacy SQLite investment ledgers to canonical Markdown event ledgers, verify Markdown-only runtime readiness, archive legacy SQLite evidence file after a separate confirmation gate, and coordinate rollback without re-enabling legacy-store normal runtime.
---

# Migration Flow

## Core Rule

Use this skill when the user asks to remove legacy SQLite usage, migrate legacy SQLite evidence file
to Markdown, verify no-SQLite readiness, archive legacy SQLite evidence, or roll
back a legacy-to-Markdown migration. Follow `docs/migration_flow_agent_guidelines.md`,
`docs/transactions_agent_guidelines.md`, and the protected-file floors in
`AGENTS.md`.

`archive-db` is the only migration command that may move a live
legacy SQLite evidence file, and it requires its own same-turn confirmation after
`prepare`, `apply`, and `verify` pass. `apply` writes Markdown ledger files and
generated caches but must not move, delete, or overwrite the source legacy evidence.
In short: apply must not move the source legacy evidence.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets,
flags, paths, and machine formats below are internal agent contracts or audit
evidence, not user instructions. Execute eligible steps yourself via tools,
summarize results naturally, and collect missing parameters conversationally.
Do not ask the user to run commands, choose flags, know canonical command
names, assemble files, or write JSON unless they explicitly request CLI/API
instructions or execution is blocked by missing authority. Confirmation gates
ask for the required decision in natural language and must not delegate command
execution or machine formatting to the user.

## Side-Effect Taxonomy

### Read-only / safe

- Detect layout/account migration state.
- Build a prepare proposal without writing it.
- Verify Markdown ledger/cache/parity state.
- Run static no-SQLite validation.

Internal command contracts:

```bash
python scripts/transactions.py account detect
python scripts/transactions.py migration detect --account <name>
python scripts/transactions.py migration prepare --account <name>
python scripts/transactions.py migration verify --account <name>
python scripts/transactions.py migration verify-no-sqlite
```

### Write-capable / gated

- Write a proposal bundle under `ledger/migrations/`.
- Apply Markdown events/caches from legacy SQLite input.
- Rebuild generated caches.
- Write `LEDGER_STATE.json`.
- Roll back recorded migration state.

Internal command contracts:

```bash
python scripts/transactions.py migration prepare --account <name> --write-proposal
python scripts/transactions.py migration apply --account <name> --yes
python scripts/transactions.py migration rollback --account <name> --migration-id <id> --yes
```

### Protected-file move / separately gated

The archive step moves the protected legacy SQLite evidence into the ledger archive. It is
not part of `apply` and must be confirmed separately after successful verify:

```bash
python scripts/transactions.py migration archive-db --account <name> --yes
```

### Forbidden without a future explicit workflow

- Deleting live or archived legacy SQLite evidence.
- Changing `SETTINGS.md` strategy, language, or base-currency semantics.
- Weakening transaction write gates.
- Manual edits of `ledger/generated/*` or other generated caches.
- legacy-store normal-runtime rollback or silent legacy-store fallback.
- Report UI redesign or broker import semantic redesign.

## Required Workflow

1. Run `python scripts/transactions.py account detect`.
   - `partial`: hard stop and explain reconciliation is required.
   - `migrate`: route to account-management legacy-layout migration first; do
     not run legacy-to-Markdown migration until account layout is clean.
   - `clean` or `demo_only_at_root`: continue only with safe detection/proposal.
2. Resolve the target account. If the user did not name one, use active account
   or safely resolvable `default`.
3. Run migration detect and prepare. Summarize account, source legacy evidence checksum,
   event count, blockers, archive target, and rollback plan.
4. Before `apply`, show a migration write gate in natural language:
   - source legacy evidence and checksum;
   - target ledger path;
   - event count and generated cache plan;
   - resulting state preview;
   - rollback/audit bundle location;
   - statement that `apply` will not move or delete legacy SQLite evidence file;
   - prompt: `Confirm migration apply? (yes / no / edit)`.
5. Only after explicit same-turn `yes`, run the apply command and then verify.
6. After verify passes, ask a separate archive gate:
   - state that this moves the protected legacy SQLite evidence file into
     `ledger/archive/legacy-sqlite/<migration-id>/`;
   - state that it does not delete archived evidence;
   - prompt: `Archive the legacy SQLite evidence now? (yes / no)`.
7. Only after explicit same-turn `yes`, run `archive-db` and verify again.

## Verification

After any write-capable step, run the smallest proof that covers the claim:

```bash
python scripts/transactions.py migration verify --account <name>
python scripts/transactions.py ledger verify-cache --account <name>
python scripts/transactions.py migration verify-no-sqlite --mode transition
python scripts/validate_project_skills.py
```

Use `--mode final` for the static no-SQLite validator when the normal runtime
is intended to be Markdown-only. During compatibility cleanup it must still
report any new SQLite surfaces outside the quarantine allowlist.

## Rollback

Rollback restores Markdown/file-backed migration state and audit notes. If an
archived SQLite evidence must be copied back, it is recovery evidence or a legacy import
input only; rollback must not make legacy-store runtime normal again. Report
exactly what was restored and verify Markdown runtime after rollback.
