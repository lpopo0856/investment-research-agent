---
name: transaction-management
description: Safely record, import, correct, and verify investment ledger transactions through the canonical transaction guidelines. Use when the user describes trades, deposits, withdrawals, dividends, fees, broker imports, SELL lot consumption, or ledger corrections; preserve the exact pre-write confirmation, backup, and verify contract.
---

# Transaction Management

## Core Rule

`transactions.db` is the canonical ledger. Follow `docs/transactions_agent_guidelines.md` end to end, keep all live writes confirmation-gated, and never edit projected tables directly.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.


## Target Account Resolution

Before parsing a write plan, previewing resulting state, importing broker data, recording cash flows, inspecting ledger state, or correcting transactions, resolve the target account. Use the user-named account when provided; otherwise use the current active account, falling back to `default` only when safely resolvable. Stop on `partial` or unresolved account state. Include the resolved account name in every natural-language write plan and confirmation gate.

If no account is safely resolvable, or the target account is missing usable
`SETTINGS.md`, route to onboarding/settings completion before ledger
inspection, write previews, imports, or corrections. Do not treat a
template-copied settings file as completed account settings until the settings
workflow has collected or confirmed the required cold-start fields. Safe
account detection/listing and onboarding/settings interview are the only
account-related bootstrap exceptions.

## Canonical Commands

Single canonical JSON insert:

```bash
python scripts/transactions.py db add --json '<canonical-json>' --account <name>
```

CSV import:

```bash
python scripts/transactions.py db import-csv --input <path> --account <name>
```

JSON import:

```bash
python scripts/transactions.py db import-json --input <path> --account <name>
```

Post-write verification and inspection:

```bash
python scripts/transactions.py verify --account <name>
python scripts/transactions.py db stats --account <name>
python scripts/transactions.py self-check
```

## Exact Pre-Write Gate

Before any `db add`, `db import-csv`, or `db import-json`, show the user all six blocks below and get an explicit same-turn `yes`:

1. Parsed trades / cash flows.
2. Write plan.
3. Exact canonical JSON blob or `/tmp` JSON path.
4. Resulting state preview.
5. SELL realized P&L when relevant.
6. Literal prompt: `Confirm and write? (yes / no / edit)`.

If the answer is `edit`, revise the plan and repeat the full gate. If the answer is `no`, do not write.

## Write Safety

Before a confirmed write, create the required backup of the target account database, normally `accounts/<name>/transactions.db.bak` unless the source guideline specifies a stronger timestamped backup. After the write, run:

```bash
python scripts/transactions.py verify --account <name>
```

If verification fails, roll back from the backup, rerun verify, and report the mismatch plus restored state. Then inspect with:

```bash
python scripts/transactions.py db stats --account <name>
```

## Forbidden Paths

Do not use SQL `UPDATE` or SQL `DELETE` on ledger tables during normal transaction management. Do not directly edit `open_lots` or `cash_balances`; they are derived state rebuilt by the canonical replay/import path. Do not patch `transactions.db` manually, bypass the confirmation gate, or skip backup/verify to save time.

## Context Discipline

For broker files or large batches, write normalized JSON under `/tmp` and show counts plus a small sample instead of pasting a huge payload. Delegate large extraction/mapping work to a temp-researcher when it would exceed the context-drop threshold; the returned `/tmp` JSON path is what crosses back into the transaction gate.
