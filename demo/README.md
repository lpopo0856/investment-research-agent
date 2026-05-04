# Demo ledger only

This directory exists only to provide a synthetic transaction ledger for generating a real portfolio report without touching the production `transactions.db`.

## Account-model isolation note

`demo/` lives as a sibling at the **repo root** — it is **NOT** under `accounts/` and is never account-scoped. The `--account` flag does not resolve `demo/`. Demo invocations must always use explicit flags: `--db demo/transactions.db --settings demo/SETTINGS.md --cache demo/market_data_cache.db`. The multi-account migration that moves root `SETTINGS.md` / `transactions.db` into `accounts/default/` does **not** touch `demo/`.

The demo does **not** provide a report pipeline script, report context template, fake news, fake catalysts, fake consensus, fake recommendations, or prefilled theme/sector output. An agent generating a demo report must run the normal report workflow end to end, choose an explicit `--report-type <daily_report|portfolio_report>`, and use `demo/transactions.db` only as the transaction database.

## Report type vs account scope

Demo runs use the same two-axis taxonomy as production:

- `report_type`: `daily_report` or `portfolio_report`.
- `account_scope`: always the demo explicit DB path. `demo/` is not an account under `accounts/`, so do **not** use `--account demo` or `--all-accounts`.

`daily_report` is the decision-heavy daily flow. It includes daily sections such as Immediate Attention, Today's Summary, Latest Material News, Forward 30-Day Event Calendar, High Risk / High Opportunity, Recommended Adjustments, Today's Action List, Recent Trading Mindset, and the holdings Action column. It skips the slower math sections that moved out of daily: Profit Panel, Performance Attribution, Discipline Check, Holding Period and Pacing, and P&L Ranking.

`portfolio_report` is the math/position review. It keeps dashboard, Profit Panel, Report Accuracy, Performance Attribution, Trade Quality, Discipline Check, Allocation & Weights, Holdings P&L and Weights **without** Action column, P&L Ranking, Holding Period and Pacing, Theme / Sector, and Sources & Data Gaps. It **must not** trigger §10.5 news search, event-calendar search, `research_targets`, `research_coverage`, temp-researcher news/events delegation, high-risk/opportunity, recommended adjustments, today's action list, Recent Trading Mindset / `trading_psychology`, or holdings action authoring.

## Isolation from the repo root (HARD)

Running the pipeline from the repository root **without** extra flags still defaults `scripts/fetch_history.py` and `scripts/fill_history_gap.py` to **`./market_data_cache.db`** — the same SQLite cache as production. That **does** touch root-level gitignored state and mixes demo fetches with your real ledger’s cache.

For demo work, keep **all durable demo-side artifacts under `demo/`**:

| Concern | What to pass |
|--------|----------------|
| Transaction store | `--db demo/transactions.db` on `fetch_prices.py`, `fetch_history.py`, `transactions.py snapshot` (already required). |
| Strategy / language / base currency | **`--settings demo/SETTINGS.md`** on `fetch_prices.py`, `fetch_history.py`, **`transactions.py snapshot`**, and `generate_report.py` so demo runs do **not** read the user's real strategy or base currency from the root `SETTINGS.md`. The snapshot bakes `locale` / `base_currency` into `report_snapshot.json`; the renderer reads those from the snapshot (its own `--settings` flag is ignored for locale once `--snapshot` is used), so omitting this flag on the snapshot step silently renders the report in the root profile's language. |
| History / gap-fill cache | **`--cache demo/market_data_cache.db`** on `fetch_history.py` and on **`fill_history_gap.py`** whenever you inject rows for that demo run. |
| Pipeline JSON | Still only under `/tmp/$REPORT_RUN_DIR` per `docs/portfolio_report_agent_guidelines.md` — never `prices.json` at repo root. |
| Delivered HTML (optional) | Write `generate_report.py --output demo/reports/<locale>_<report_type>.html` when refreshing the root `index.html` preview (for example `zh-Hant_daily_report.html` / `zh-Hant_portfolio_report.html`). For ad hoc archives, a dated `YYYY-MM-DD_HHMM_demo_<report_type>.html` name is also fine. Create `demo/reports/` if missing. |

Do **not** write `prices_history.json` or a merge-target `prices.json` in the repo root for demo; use `$REPORT_RUN_DIR` only.

## Files

| File | Role |
|------|------|
| `transactions_history.json` | Canonical synthetic transaction seed. Safe to commit. |
| `bootstrap_demo_ledger.py` | Regenerates the JSON and materializes `demo/transactions.db`. |
| `transactions.db` | Gitignored SQLite ledger built from the JSON. |
| `SETTINGS.md` | Synthetic strategy / language / base-currency profile for the demo. Pass via `--settings demo/SETTINGS.md`. Safe to commit. |
| `market_data_cache.db` | Optional gitignored cache created when you pass `--cache demo/market_data_cache.db` during demo history runs. |
| `reports/` | Optional output directory for demo-only HTML (gitignored); create as needed. |

## Refresh The Demo DB

```bash
python3 demo/bootstrap_demo_ledger.py --write-json
python3 demo/bootstrap_demo_ledger.py --apply
```

## Generate A Demo Report

**MUST FOLLOW THE Portfolio reports SECTION OF AGENTS.MD**

Follow the normal report workflow exactly as if generating a real report, with **four** differences from a default root run:

1. **Transaction DB:** anywhere the workflow reads the transaction database, use `demo/transactions.db` instead of the root `transactions.db`.
2. **Settings profile:** pass **`--settings demo/SETTINGS.md`** to `fetch_prices.py`, `fetch_history.py`, **`transactions.py snapshot`**, and `generate_report.py` so demo runs do not read the user's real strategy / language / base currency. (The snapshot step is the one that bakes locale + base currency into `report_snapshot.json`; the renderer reads them from the snapshot, not from its own `--settings` flag.)
3. **Market-data cache:** pass **`--cache demo/market_data_cache.db`** to `fetch_history.py` and to `fill_history_gap.py` so the root `market_data_cache.db` is not used.
4. **Report type:** pass `--report-type daily_report` or `--report-type portfolio_report` to `validate_report_context.py` and `generate_report.py`, and author only the context keys that render for that type.

### Example: daily report

This type can run the full daily editorial/research workflow. Author `report_context.json` with daily sections (`news`, `events`, `research_coverage`, `alerts`, `high_opps`, `adjustments`, `actions`, `trading_psychology`, theme/sector audit, Strategy readout, reviewer pass, etc.) exactly as required by the main spec.

After `export REPORT_RUN_DIR=...` under `/tmp`:

```bash
python3 scripts/fetch_prices.py --db demo/transactions.db --settings demo/SETTINGS.md \
  --output "$REPORT_RUN_DIR/prices.json"
python3 scripts/fetch_history.py --db demo/transactions.db --settings demo/SETTINGS.md \
  --cache demo/market_data_cache.db --merge-into "$REPORT_RUN_DIR/prices.json"
python3 scripts/transactions.py snapshot --db demo/transactions.db --settings demo/SETTINGS.md \
  --prices "$REPORT_RUN_DIR/prices.json" --output "$REPORT_RUN_DIR/report_snapshot.json"
# … author daily report_context.json, then:
python3 scripts/validate_report_context.py \
  --snapshot "$REPORT_RUN_DIR/report_snapshot.json" \
  --context "$REPORT_RUN_DIR/report_context.json" \
  --report-type daily_report
python3 scripts/generate_report.py --settings demo/SETTINGS.md \
  --report-type daily_report \
  --snapshot "$REPORT_RUN_DIR/report_snapshot.json" \
  --context "$REPORT_RUN_DIR/report_context.json" \
  --output demo/reports/zh-Hant_daily_report.html
```

### Example: portfolio report

This type is intentionally cost-reduced and math/position focused. It uses the same price/history/snapshot steps, but the context step must skip daily research/editorial keys.

For `portfolio_report`, author only the rendered non-daily context, normally:

- `theme_sector_html`
- `theme_sector_audit`
- `strategy_readout`
- `data_gaps`
- `reviewer_pass`

Do **not** author `news`, `events`, `research_targets`, `research_coverage`, `high_opps`, `adjustments`, `actions`, `holdings_actions`, or `trading_psychology`; do **not** launch a temp-researcher for news/events.

```bash
python3 scripts/fetch_prices.py --db demo/transactions.db --settings demo/SETTINGS.md \
  --output "$REPORT_RUN_DIR/prices.json"
python3 scripts/fetch_history.py --db demo/transactions.db --settings demo/SETTINGS.md \
  --cache demo/market_data_cache.db --merge-into "$REPORT_RUN_DIR/prices.json"
python3 scripts/transactions.py snapshot --db demo/transactions.db --settings demo/SETTINGS.md \
  --prices "$REPORT_RUN_DIR/prices.json" --output "$REPORT_RUN_DIR/report_snapshot.json"
# … author portfolio report_context.json with only rendered portfolio keys, then:
python3 scripts/validate_report_context.py \
  --snapshot "$REPORT_RUN_DIR/report_snapshot.json" \
  --context "$REPORT_RUN_DIR/report_context.json" \
  --report-type portfolio_report
python3 scripts/generate_report.py --settings demo/SETTINGS.md \
  --report-type portfolio_report \
  --snapshot "$REPORT_RUN_DIR/report_snapshot.json" \
  --context "$REPORT_RUN_DIR/report_context.json" \
  --output demo/reports/zh-Hant_portfolio_report.html
```

Only the transaction ledger is synthetic. Everything else is generated during the normal selected report run. Daily reports may research live news/events and author `trading_psychology`; portfolio reports must skip those daily-only flows. Intermediate pipeline files (`prices.json`, snapshot, context, etc.) belong under `/tmp` in `$REPORT_RUN_DIR` and are removed after the HTML is written and checks pass — same as production (`/docs/portfolio_report_agent_guidelines.md`). Prefer **`demo/reports/`** for the final HTML so user-facing `reports/` stays for production runs. The root `index.html` expects stable preview filenames in the shape `demo/reports/<locale>_<report_type>.html` (`en_daily_report.html`, `en_portfolio_report.html`, `zh-Hant_daily_report.html`, `zh-Hant_portfolio_report.html`).
