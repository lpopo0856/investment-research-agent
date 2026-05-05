---
name: split-asset-account
description: Safely split an asset class, market, strategy sleeve, or ticker set out of one investment ledger into a separate account while preserving combined balances. Use when a user asks to isolate crypto, options, private assets, broker sleeves, strategy buckets, or any subset of holdings/transactions into another account; when ledger surgery must be auditable, dry-run first, backed up, and verified; or when an agent needs a brand-agnostic account-split workflow rather than broker-specific import logic.
---

# Split Asset Account

## Core Rule

Treat account splitting as ledger migration, not table editing. Follow `docs/transactions_agent_guidelines.md` for ledger write safety: preserve the combined economic state of source plus target, keep the original source DB backed up, and verify both reconstructed ledgers before writing live files.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.

Use the reusable helper when this repo's account-aware SQLite ledger is available:

```bash
python scripts/split_asset_account.py \
  --source-account default \
  --target-account crypto \
  --market crypto
```

Default mode is dry-run only. Add `--apply` only after reviewing the JSON summary and confirming the dry-run has no `verify_issues`.

## Workflow

1. Resolve the source account before touching account files. Use the user-named source when provided; otherwise use the current active account, falling back to `default` only when safely resolvable. Detect layout before touching account files:

```bash
python scripts/transactions.py account detect
python scripts/transactions.py account list
```

`partial` is a hard stop; run project onboarding/migration guidance before
continuing. Continue on `clean` only when the source account has usable
settings, because split decisions depend on source-account intent and ledger
context. If the source account is unresolved or its settings are
missing/template-only/incomplete, route to onboarding/settings completion before
dry-run or ledger inspection.

Do not require target account settings before `--apply` when the canonical
split script will create or replace the target account. By default, apply copies
source `SETTINGS.md` into the target as a starting scaffold; guide the user
through target settings completion after a successful split. If the target
account already has user-confirmed settings that must be preserved, run apply
with `--no-copy-settings` and call out that any target `SETTINGS.md` overwrite
is a settings write requiring the settings-management diff-confirm gate. Safe
account detection/listing and onboarding/settings interview are the bootstrap
exceptions.

2. Define the split selector.

Prefer exact selectors that are stable in the ledger: `--market crypto`, `--ticker BTC,ETH`, or repeated `--ticker`. Do not infer a broad selector from a report label if the transaction rows use different canonical fields.

3. Dry-run the split.

```bash
python scripts/split_asset_account.py \
  --source-account <source> \
  --target-account <target> \
  --market <market-or-asset-class> \
  --run-dir /tmp/asset_account_split_<date>
```

Review:
- `source_rebuilt.json`: source account after selected rows are removed and BUY funding transfers are inserted.
- `target_import.json`: target account funding deposits plus selected transactions.
- `summary.json`: selected count, tickers, bridge count, and verification issues.

Proceed only when `verify_issues.source`, `verify_issues.target`, and `verify_issues.combined` are all empty.

4. Explain the write plan before applying.

Show the user the selector, selected tickers/assets, target account name, backup path, and the dry-run verification result. If the project has a confirm-before-write rule for transaction DBs, get explicit same-turn confirmation before `--apply`.

5. Apply.

Before applying, check whether the target already has a user-confirmed
`SETTINGS.md`. If it does, either use `--no-copy-settings` or complete the
settings-management diff-confirm gate for any overwrite before running the
default apply. Without `--no-copy-settings`, the split script copies source
settings into the target as a scaffold and target settings completion happens
after a successful split.

```bash
python scripts/split_asset_account.py \
  --source-account <source> \
  --target-account <target> \
  --market <market-or-asset-class> \
  --run-dir /tmp/asset_account_split_<date> \
  --apply
```

Use `--replace-target` only after verifying the target account is intentionally disposable or already represents the same split.

6. Verify live state.

```bash
python scripts/transactions.py verify --account <source>
python scripts/transactions.py verify --account <target>
python scripts/transactions.py db stats --account <source>
python scripts/transactions.py db stats --account <target>
```

Check that the source no longer has the selected open lots, the target has them, and the active account pointer is unchanged unless the user asked to switch accounts.

## Accounting Pattern

For selected `BUY` rows, insert a source `WITHDRAW` and target `DEPOSIT` for `qty * price + fees` on the same date, then keep the original `BUY` in the target account. This makes the target account self-funding and prevents combined NAV from double-counting.

For selected non-BUY rows such as `SELL`, `DIVIDEND`, or `FEE`, keep the selected transaction in the target account and do not mirror the cash effect in the source. The target should own later proceeds and costs from the migrated asset history.

Never edit derived balance tables directly. Rebuild them through the canonical import/replay path.

## Failure Handling

If any dry-run verification fails, do not apply. Inspect `summary.json`, narrow the selector, or handle unsupported transaction shapes manually.

If live verification fails after apply, restore the source DB from `transactions.db.bak` or the timestamped backup written by the script, then report the mismatch.

If the target account already contains transactions, refuse to overwrite unless the user explicitly intends to replace it.
