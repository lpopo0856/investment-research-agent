# Migration Flow Agent Guidelines

This document is the source of truth for the legacy-to-Markdown migration-flow
skill. It preserves the repo's natural-language safety contract while moving
transaction history from legacy SQLite evidence into canonical Markdown ledger
events and generated file caches.

## Scope

Use this workflow for:

- migrating a legacy SQLite evidence file into `accounts/<name>/ledger/events/`;
- proving Markdown ledger/cache parity;
- moving legacy SQLite evidence into `ledger/archive/legacy-sqlite/<migration-id>/`
  after a separate confirmation gate;
- rolling back recorded migration state without re-enabling legacy-store normal
  runtime;
- running the static no-SQLite quarantine validator.

Do not use this workflow to change investment strategy/settings, redesign
reports, redesign broker import semantics, manually edit generated caches, or
delete archived legacy SQLite evidence.

## State machine

1. `detect` — read-only. Classifies account layout, legacy SQLite evidence presence,
   existing Markdown events, generated cache status, migration bundles, and
   archived legacy SQLite evidence.
2. `prepare` — read-only by default. Reads legacy SQLite through the
   quarantine adapter path and builds a proposal: row counts, planned event
   paths, checksums, archive target, rollback plan, and blockers. Optional
   `--write-proposal` writes proposal evidence under `ledger/migrations/`.
3. `apply` — gated. Writes Markdown event files, generated caches, and
   `LEDGER_STATE.json`. It must not move, delete, or overwrite
   legacy SQLite evidence file.
4. `verify` — read-only. Proves Markdown events, generated caches, legacy SQLite evidence
   checksum/parity when the source evidence is still present, and archive state after source-evidence archival.
5. `archive-db` — separately gated protected-file move. Moves
   legacy SQLite evidence file and SQLite journal files into
   `ledger/archive/legacy-sqlite/<migration-id>/`, writes manifest and restore
   instructions, and leaves normal runtime Markdown-backed.
6. `rollback` — gated. Restores prior Markdown/file state or copies archived SQLite evidence
   evidence back only as recovery/legacy import input. It must not silently
   restore legacy-store normal runtime.

## Safety gates

Before any script reads account ledger/settings files, run account detection and
obey its exact result:

- `partial`: stop and explain reconciliation is required.
- `migrate`: route through account-management legacy-layout migration first.
- `clean`: do not run account-layout migration; continue with legacy-to-Markdown
  migration only if requested.
- `demo_only_at_root`: do not migrate account layout.

### Apply gate

Before `migration apply`, present:

1. target account and ledger path;
2. source legacy evidence path and checksum;
3. number of legacy `transactions` rows and planned Markdown events;
4. generated cache/write plan;
5. rollback/audit bundle plan;
6. explicit statement that `apply` will not move/delete legacy SQLite evidence file;
7. prompt: `Confirm migration apply? (yes / no / edit)`.

Only an explicit same-turn `yes` authorizes apply.

### Archive gate

Before `migration archive-db`, verify that apply succeeded and present:

1. source legacy evidence path and checksum;
2. archive path under `ledger/archive/legacy-sqlite/<migration-id>/`;
3. statement that this is a protected-file move, not deletion;
4. statement that archived evidence deletion is out of scope;
5. prompt: `Archive the legacy SQLite evidence now? (yes / no)`.

Only an explicit same-turn `yes` authorizes archive-db.

## Mapping invariant

Every legacy `transactions` row maps to exactly one canonical Markdown event.
Auxiliary legacy rows such as lot-consumption rows, report archive rows,
metadata/version rows, and derived projection rows map to event metadata, lot
links, durable archive records, migration manifests, or generated caches rather
than standalone canonical events.

Verification must prove that economic history is preserved: quantities, cash,
SELL lot consumption, reversal targets, realized P&L, generated caches, and
source checksum evidence.

## Static no-SQLite validator

`python scripts/transactions.py migration verify-no-sqlite` is the normal
entry point. It delegates to `scripts/validate_no_sqlite.py`.

- `--mode transition` allows the migration/import/archive quarantine surfaces
  plus the final legacy importer allowlist, and is used while compatibility
  shims are still being audited.
- `--mode final` allows only the exact legacy importer/docs/test allowlist and
  must pass before declaring SQLite removed from normal runtime.

The final allowlist is machine-readable in `scripts/validate_no_sqlite.py`.
If a new SQLite reference appears outside the allowlist, treat it as a
regression until it is removed or explicitly classified as legacy-import-only.

## User-facing style

Do not ask the user to run commands, choose flags, assemble JSON, or understand
internal file formats. The agent runs safe commands internally, reports concise
evidence in natural language, and asks only for the required `yes / no / edit`
decisions at apply/archive/rollback gates.

## Stop conditions

- account detector returns `partial`;
- prepare/apply parity has blockers;
- generated cache verification fails;
- source legacy evidence checksum differs unexpectedly;
- archive is requested before apply+verify pass;
- a step would delete live or archived legacy SQLite evidence;
- a step would change `SETTINGS.md` strategy semantics, report UI, broker
  import semantics, or add heavy dependencies.
