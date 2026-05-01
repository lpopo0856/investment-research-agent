# Demo ledger only

This directory exists only to provide a synthetic transaction ledger for generating a real portfolio report without touching the production `transactions.db`.

The demo does **not** provide a report pipeline script, report context template, fake news, fake catalysts, fake consensus, fake recommendations, or prefilled theme/sector output. An agent generating a demo report must run the normal portfolio-report workflow end to end and use `demo/transactions.db` only as the transaction database.

## Files

| File | Role |
|------|------|
| `transactions_history.json` | Canonical synthetic transaction seed. Safe to commit. |
| `bootstrap_demo_ledger.py` | Regenerates the JSON and materializes `demo/transactions.db`. |
| `transactions.db` | Gitignored SQLite ledger built from the JSON. |

## Refresh The Demo DB

```bash
python3 demo/bootstrap_demo_ledger.py --write-json
python3 demo/bootstrap_demo_ledger.py --apply
```

## Generate A Demo Report

Follow the normal portfolio-report workflow exactly as if generating a real report. The only difference is transaction source selection: anywhere the workflow reads the transaction database, use `demo/transactions.db` instead of the root `transactions.db`.

Only the transaction ledger is fake. Everything else is generated or researched during the normal report run, including the mandatory `trading_psychology` block.
