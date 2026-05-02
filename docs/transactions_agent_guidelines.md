# Transactions Ledger — Agent Guidelines

`transactions.db` is the **only** record of the portfolio. It is a local
SQLite database stored at the repo root and gitignored. It captures both:

1. The **append-only event log** of every flow (BUY / SELL / DEPOSIT /
   WITHDRAW / DIVIDEND / FEE / FX_CONVERT / ADJUST / REVERSAL), including
   the *operation mindset* (`rationale`, `tags`, `lot consumption`).
2. The **derived projected state** in two materialized tables (`open_lots`
   and `cash_balances`) that get rebuilt from a fresh log replay after
   every write. This is what the report renderer, price fetcher, and
   profit panel read from.

`HOLDINGS.md` has been **retired** as a live source. The previous markdown
transaction ledger (`TRANSACTIONS.md`) was retired one iteration earlier. The
DB is the single source of truth; consumers either read the balance tables directly via
`scripts/transactions.py load_holdings_lots(db_path)` or query SQL.

> **Iteration 3 (2026-04-30 late-night)** — `HOLDINGS.md` removed from
> runtime inputs; balance tables added; `holdings_update_agent_guidelines.md` folded into this
> document.

---

## 0. Token discipline (HARD)

Per `docs/context_drop_protocol.md`. The DB grows over time; what was 5
rows during onboarding becomes 500+ after a year of recording. Reading
the whole ledger into agent context every turn is unnecessary and
expensive.

- **`db dump` is for backup, not for context.** Never paste `db dump` output
  into the conversation to "see what's there." Use `db stats` for shape
  (counts by type, date range), `transactions.py snapshot` /
  `transactions.py analytics` / `transactions.py pnl` for the canonical
  compact analytical views, or narrow SQL (`sqlite3 transactions.db
  "SELECT … LIMIT 50"`) for targeted lookups.
- **Bulk-import preview is path + sample, not full row list.** For batches
  > 20 rows, show counts, the `/tmp/...json` path, and `jq '.[0:5]' <path>`
  — same rule as `docs/onboarding_agent_guidelines.md` §6.3.
- **Schema-validate canonical JSON in an isolated context for large imports.**
  A brokerage CSV with 200+ rows is research-class — delegate parsing /
  mapping / validation to a temp-researcher per
  `docs/temp_researcher_contract.md` (using whatever isolation primitive
  the runtime provides). The parent reads only the summary + the
  `/tmp/...json` path before §3.7 confirmation.

These rules do not weaken any §1 safety rule below — backup, plan,
confirm, verify still apply unchanged.

## 1. Hard safety rules

1. **Never** UPDATE or DELETE rows in `transactions` or `sell_lot_consumption`
   to "fix" a prior entry. Mistakes are corrected by appending a `REVERSAL`
   row whose `target_id` references the bad row's `id`, then appending the
   corrected entry.
2. **Never** edit the derived tables (`open_lots`, `cash_balances`) directly.
   They are auto-rebuilt on every successful import. Run
   `python scripts/transactions.py db rebuild` if you suspect drift.
3. **Always** back up to `transactions.db.bak` before any agent-driven write
   (`db add`, `db import-csv`, `db import-json`, `db import-md`, `migrate`).
4. **Never** show a write without first showing a parsed plan + the JSON
   blob(s) that will be inserted + getting explicit `yes` from the user in
   the same conversation turn.
5. **Always** run `python scripts/transactions.py verify` after every write
   and report the result. Verify reconciles the log replay against the
   balance tables — drift means something wrote the balance tables outside
   the rebuild path. On mismatch, restore `transactions.db.bak` and tell
   the user.
6. **Never** invent missing fields. Every defaulted field is tagged
   `(assumed)` in the plan. `rationale` and `tags` are optional — leave them
   `NULL` when the user did not volunteer them; never interrogate the user
   just to fill them in.

## 2. Schema

`transactions.db` has four tables:

```sql
-- Append-only event log.
transactions(
  id, date, type, ticker, qty, price, gross, fees, net, amount,
  currency, cash_account, bucket, market, rationale, tags,
  from_amount, from_currency, from_cash_account,
  to_amount, to_currency, to_cash_account, rate,
  source, source_ref, created_at, target_id
)

-- Lot consumption detail for SELL events.
sell_lot_consumption(
  id, transaction_id, acq_date, cost, qty
)

-- Derived: current open lots. Rebuilt from a fresh replay after every import.
open_lots(
  id, ticker, qty, cost, acq_date, bucket, market, currency, is_share, updated_at
)

-- Derived: current cash by currency. Rebuilt the same way.
cash_balances(
  currency, amount, updated_at
)
```

Schema version is tracked in `schema_meta`. `db init` is idempotent and
upgrades older DBs to the current schema by adding the derived tables and
running a rebuild.

Transaction types (`type` column):

| Type         | Direction       | Cash impact                          | Position impact      | P&L impact |
|--------------|-----------------|--------------------------------------|----------------------|------------|
| `BUY`        | external → lot  | `−(qty × price + fees)`              | append lot           | none       |
| `SELL`       | lot → external  | `+(qty × price − fees)`              | reduce/remove lots   | realized = (price − cost) × qty per lot |
| `DEPOSIT`    | external → cash | `+amount`                            | none                 | none (external flow) |
| `WITHDRAW`   | cash → external | `−amount`                            | none                 | none (external flow) |
| `DIVIDEND`   | external → cash | `+amount`                            | none                 | realized = `+amount` |
| `FEE`        | cash → external | `−amount`                            | none                 | realized = `−amount` |
| `FX_CONVERT` | cash → cash     | net 0 across two cash lines          | none                 | none       |
| `ADJUST`     | varies          | varies                               | varies               | manual review |
| `REVERSAL`   | varies          | inverse of `target_id` row           | inverse              | inverse    |

Required fields per type are enforced by `_validate_canonical_dict()` in
`scripts/transactions.py`. CSV / JSON / message imports go through that
validator before any row is INSERTed.

## 3. Natural-language workflow (the common case)

When the user describes a trade, correction, or cash adjustment in plain
English ("bought 30 NVDA at $185 yesterday", "sold 10 TSLA at $400",
"deposited $5,000"), follow this contract end-to-end. **Hard rule**: never
INSERT into the DB without showing a parsed plan, the canonical JSON blob,
and getting an explicit `yes` from the user in the same turn.

### 3.1 When this section applies

Any user message that describes a position or cash change. Typical
phrasings:

- "I bought 30 NVDA at $185 yesterday"
- "Sold 10 TSLA at $400 today"
- "Log trade: 5 BTC at 78,500 on 2026-04-25, long-term"
- "Trim 50% of my INTC short-term lots at $82"
- "Add 100 shares of GAMA at $660 to mid term"
- "Fix the GOOG lot from 2025-09: actually 70 shares not 75"
- "I deposited $5,000"
- "Q1 dividend on GOOG, $80"

If the message is ambiguous (e.g. just "buy NVDA"), ask one specific
question for the missing field — do not guess.

### 3.2 Parse: required fields per trade

For each trade in the user's message, extract:

| Field     | Notes |
|-----------|-------|
| Direction | `BUY` or `SELL` (or `DEPOSIT` / `WITHDRAW` / `DIVIDEND` / `FEE`) |
| Ticker    | Case-normalized; preserve exchange suffix (`2330.TW`) and crypto symbols. Required for `BUY` / `SELL` / `DIVIDEND`; omitted for cash-only events. |
| Quantity  | Decimal allowed (crypto / fractional shares) |
| Price     | Per unit; preserve the original currency prefix (`$`, `NT$`, `€`, …) |
| Date      | `YYYY-MM-DD`. If the user did not say, default to today's local date and **state the assumption** |
| Bucket    | `Long Term`, `Mid Term`, `Short Term`. Required for a `BUY` of a ticker not yet in `open_lots`; for an existing ticker, default to that ticker's current bucket and confirm; for a `SELL`, derive from the existing lots being consumed |
| Currency  | Settlement currency. Derive from the price prefix and the ticker's market. If multiple cash lines could match, ask |
| Market    | Market-type tag — `US`, `TW`, `TWO`, `JP`, `HK`, `LSE`, `crypto`, `FX`, `cash`. For an existing ticker, default to that ticker's prior tag and confirm. For a new ticker, derive from the venue / suffix / asset class; if ambiguous (e.g. dual-listed), ask |
| Rationale | **Optional**. Capture verbatim only when the user volunteered a reason. Never invent or interrogate. |
| Tags      | **Optional**. Suggest 1–3 short tags only if natural; otherwise leave blank |

If any required field is missing or ambiguous, stop and ask one specific
question — do not guess.

### 3.3 BUY procedure

- Build a canonical JSON object with `type=BUY`, `ticker`, `qty`, `price`,
  `bucket`, `market`, `currency`, `cash_account` (defaults to `currency`).
- Cash impact: `qty × price + fees` is debited from `cash_account`. The
  rebuild step recomputes the new `cash_balances` row automatically.
- The market tag is the single source of truth for `scripts/fetch_prices.py`.
  The script formats `2330.TW`, `BTC-USD`, `7203.T`, `VWRA.L`, etc. based on
  this tag — do not duplicate the suffix into the ticker itself unless the
  user wrote it that way.

### 3.4 SELL procedure

- List candidate open lots for the ticker, sorted by **highest cost basis
  first** (default tax-efficient ordering for gains). The user may override
  with phrases like "FIFO", "oldest first", or "specific lot 2025-09".
- Decrement quantities across one or more lots until the sell quantity is
  satisfied. The replay engine drains lots in declaration order; the
  matching `sell_lot_consumption` rows are inserted alongside the SELL.
- Cash impact: `+ qty × price − fees`.
- Compute realized P&L per affected lot (`(sell_price − cost) × qty_taken`)
  and show it in the confirmation step.
- If the requested sell quantity exceeds the total open quantity, refuse
  with each lot's max sellable amount. The replay logs the issue rather
  than silently proceeding.

### 3.5 EDIT procedure (corrections to a prior transaction)

When the user is fixing a typo / wrong price / wrong date / wrong quantity
in a transaction that is already in the DB:

1. Find the bad row's `id` (`db dump | jq` or `db stats` plus a quick
   inspection works).
2. Append a `REVERSAL` row whose `target_id` is the bad row's `id`. This
   inverts the cash and position impact.
3. Append the corrected `BUY` / `SELL` / `DEPOSIT` / etc. row.
4. The rebuild step yields the corrected balance tables.

Never UPDATE or DELETE the bad row. The append-only invariant is what gives
the agent a credible audit trail.

### 3.6 Confirmation transcript (required before INSERT)

Before any INSERT, reply with exactly these blocks:

1. **Parsed trades** — a small table or bullet list with every field per
   trade. Mark every defaulted / inferred field as `(assumed)`. Include
   `rationale` and `tags` only when the user volunteered them.
2. **Plan** — bullet list, e.g.:
   - `INSERT into transactions: {"date":"2026-04-27","type":"BUY","ticker":"NVDA","qty":30,"price":185.00,"bucket":"Mid Term","market":"US","currency":"USD","cash_account":"USD"}`
   - `→ open_lots gains 1 row (NVDA 30 @ 185.00); cash_balances USD 50000 → 44450 after auto-rebuild`
3. **JSON blob(s)** — the exact JSON that will be passed to
   `transactions.py db add` (or `import-csv` / `import-json` for batches),
   in a fenced ```json block.
4. **Resulting state** — short summary: open_lots row count delta,
   cash_balances per-currency before/after, transaction count inserted.
5. **Realized P&L** (only for `SELL`) — per-lot realized P&L and the
   `lots: [{acq_date, cost, qty}, …]` array that will land in
   `sell_lot_consumption`. (IRR is intentionally not computed; see
   `docs/portfolio_report_agent_guidelines.md` §9.4.)
6. **Question** — literal prompt: `Confirm and write? (yes / no / edit)`.

Write only on `yes` / `confirm` / `go` / equivalent. On `edit`, re-prompt
for what to change. On `no`, drop the plan and reply with a one-liner
acknowledgement.

### 3.7 Write procedure

1. `cp transactions.db transactions.db.bak`.
2. INSERT each transaction via `python scripts/transactions.py db add --json '<canonical-json>'`
   in the order the user listed them (or `db import-csv` / `db import-json`
   for a batch file). Each call auto-rebuilds the balance tables.
3. Run `python scripts/transactions.py verify`. Must exit 0:
   `OK: replay matches open_lots + cash_balances.`
4. Reply with the inserted transaction `id`s and a one-line summary, e.g.
   `Inserted txn id=87 (NVDA BUY 30 @ $185.00); open_lots +1, USD cash 50000 → 44450.`
5. If verification fails, restore `transactions.db.bak` and report the
   failure without retrying silently.

### 3.8 Edge cases

- **Sell more than held** → refuse, list each lot's max sellable quantity.
- **BUY for unknown ticker without a bucket** → ask the user to pick `Long
  Term` / `Mid Term` / `Short Term`.
- **Multiple cash accounts in the same currency** → ask which one to debit
  / credit.
- **Date in the future** → refuse. The DB is the executed-transaction log;
  planned or limit orders are out of scope.
- **Ambiguous price prefix** (e.g. bare `185` with no `$`) → ask for the
  currency.
- **Multi-trade batch** ("bought 10 NVDA at 200 and sold 5 TSLA at 400
  yesterday") → parse each trade separately and present them as a single
  confirmation block. Insert atomically (one validation pass; all-or-nothing
  per `db_import_records`).
- **Cash-only adjustments** ("I deposited $5,000") → use `DEPOSIT`; no
  ticker, no qty, no price.

## 4. Bulk ingestion paths

For broker statements or transaction history files, the agent has three
direct importers plus a one-shot markdown migration.

### 4.1 CSV file

```
python scripts/transactions.py db import-csv \
    --input statements/2026-04-schwab.csv [--mapping mapping.json]
```

Canonical columns:

```
date, type, ticker, qty, price, gross, fees, net, amount,
currency, cash_account, bucket, market, rationale, tags,
from_amount, from_currency, from_cash_account,
to_amount, to_currency, to_cash_account, rate,
lots_json
```

`lots_json` is a JSON-encoded list of `{acq_date, cost, qty}` for SELL
events. For broker-specific CSVs that use different column names, pass a
`--mapping` JSON file:

```json
{
  "Symbol": "ticker",
  "Action": "type",
  "Quantity": "qty",
  "Price (USD)": "price",
  "Trade Date": "date"
}
```

The import is **atomic** — if any row fails validation, no rows are
written. Errors are reported with line numbers.

### 4.2 JSON file

```
python scripts/transactions.py db import-json --input transactions.json
```

A JSON array (or single object) where every element matches the canonical
schema. SELL records may include a `lots` array directly (no
JSON-in-JSON `lots_json` encoding needed).

### 4.3 Single-message add

```
python scripts/transactions.py db add --json '<canonical-json>'
```

Used by the natural-language workflow once the agent has parsed the
message. Same validation pipeline as `import-json`.

### 4.4 Markdown migration (one-shot)

```
python scripts/transactions.py db import-md \
    --input TRANSACTIONS.md --delete-after
```

Used **once** when carrying over data from iteration 1's `TRANSACTIONS.md`.
After a successful import, the markdown file is deleted (`--delete-after`).
Subsequent flows go through 3 / 4.1 / 4.2 / 4.3.

### 4.5 Other formats (PDF / HTML / XLSX broker statements)

Out of scope for direct script support. The agent preprocesses such files
into canonical CSV or JSON, then uses 4.1 / 4.2.

## 5. Bootstrapping from a pre-existing HOLDINGS.md

If you are upgrading from iteration 2 (where `HOLDINGS.md` was the
projected ledger) and need to seed the DB:

```sh
python scripts/transactions.py db init        # create transactions.db schema
python scripts/transactions.py migrate \
    --holdings HOLDINGS.md                    # synthesize BUY/DEPOSIT records
python scripts/transactions.py verify         # confirm replay matches balance tables
rm HOLDINGS.md HOLDINGS.md.bak HOLDINGS.example.md   # the file is no longer needed
```

`migrate` produces one synthetic `BUY` per existing lot and a single
`DEPOSIT` per cash currency, sized so replay round-trips the seeded
balances. The synthetic entries carry `tags=migrated,bootstrap` and
`source=migrate`. `migrate` refuses to run when the DB already contains
rows, so it is safe against double-bootstrapping.

## 6. Profit-panel computation

The periodic profit panel is computed from the DB. In the automated portfolio
report pipeline this is produced by `python scripts/transactions.py snapshot`
and embedded in `report_snapshot.json["profit_panel"]`; do not manually merge a
separate `profit_panel.json` into `report_context.json`. For that pipeline,
`--prices` points at `$REPORT_RUN_DIR/prices.json` under `/tmp` (see
`/docs/portfolio_report_agent_guidelines.md` — Intermediate files), not the
repo root. The standalone command below is for inspection/debugging; write
`--output` under `/tmp` unless the user explicitly wants a file in the repo:

```
python scripts/transactions.py profit-panel \
    --db transactions.db --prices /tmp/investments_debug_prices.json \
    --settings SETTINGS.md --output /tmp/investments_debug_profit_panel.json
```

Periods covered: `1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME`.

For each period:

```
period_pnl   = ending_value − starting_value − net_external_flows
return_pct   = period_pnl / max(starting_value + 0.5 × net_external_flows, ε)
realized     = Σ realized events (SELL_LOT, DIVIDEND, FEE) whose date falls in (boundary, today]
unrealized_Δ = ending open-lot unrealized P&L − boundary open-lot unrealized P&L
               where each side is mark price − lot cost, converted to base
net_flows    = Σ DEPOSIT − Σ WITHDRAW       # flows external to the portfolio
```

`starting_value` requires daily closing prices and FX as of the boundary
date. Run `scripts/fetch_history.py` once per report run to populate the
run’s prices file (typically `$REPORT_RUN_DIR/prices.json` under `/tmp`; or
`prices_history.json` only if you deliberately use that path) with `_history` and `_fx_history`.
The script uses `market_data_cache.db` by default: it reads cached daily
closes / FX first, fetches missing or stale ranges from free APIs, and upserts
successful rows back into the cache. Use `--no-cache` only for debugging a
network-only run. The cache is derived market data; it is not canonical user
transaction data.
Missing history degrades to a fallback (current price) with an explicit
audit note rendered under Sources & data gaps, not inside the profit panel.

For ALLTIME, `starting_value = 0`, `starting_unrealized = 0`, and
`net_flows` includes every DEPOSIT − WITHDRAW from the beginning of the DB.

### 6.1 Transaction analytics for report sections

Use the transaction history to build the report's three behavioral sections. In
the automated report pipeline this is also produced by `transactions.py
snapshot` and embedded in `report_snapshot.json["transaction_analytics"]`; the
standalone command is for inspection/debugging or intentional override review:

```
python scripts/transactions.py analytics \
    --db transactions.db --prices /tmp/investments_debug_prices.json \
    --settings SETTINGS.md --output /tmp/investments_debug_transaction_analytics.json
```

The output is a JSON object with three top-level groups (`performance_attribution`,
`trade_quality`, `discipline_check`) plus `base_currency` and `as_of`. Each
group's emitted keys (canonical — consume by name, do not paraphrase):

- `performance_attribution`: `ending_nav`, `money_weighted_return_annualized`,
  `periods`, `top_contributors`, `top_detractors`, `asset_class_contribution`.
- `trade_quality`: `closed_lot_count`, `win_rate_pct`, `gross_profit`,
  `gross_loss`, `profit_factor`, `avg_realized`, `avg_win`, `avg_loss`,
  `avg_hold_days`, `sell_followups`, `buy_followups`, `recent_activity`.
- `discipline_check`: `avg_days_deposit_to_buy` (cash deploy speed from
  DEPOSIT → next BUY), `avg_days_sell_to_buy` (redeploy speed from SELL →
  next BUY), `top_position_weights`, `recent_buy_counts_30d` (buy churn,
  filtered to ≥ 3), `short_bucket_over_1y` (stale short-term lots),
  `latest_lot_cost_flags` (high-cost-vs-prior adds), `largest_unrealized_losses`,
  `largest_unrealized_gains`, `data_gaps`.

The shape and key names are authoritative in `scripts/transactions.py`
(`compute_transaction_analytics`); update this list when keys are added,
removed, or renamed.

## 7. Realized + unrealized snapshot

Lifetime realized P&L (closed sells, dividends, fees) and current
unrealized P&L (open lots vs latest price) are produced by:

```
python scripts/transactions.py pnl \
    --db transactions.db --prices /tmp/investments_debug_prices.json --settings SETTINGS.md
```

In the automated report pipeline this output is embedded by
`transactions.py snapshot` under `report_snapshot.json["realized_unrealized"]`
and then surfaced as a KPI strip above the profit panel. The standalone command
is for inspection/debugging; do not treat it as an extra report step.

## 8. Verify, rebuild, dump, stats, self-check

- `python scripts/transactions.py verify` — replay the log, compare to
  the materialized `open_lots` + `cash_balances`. Drift means something
  wrote the balance tables outside the rebuild path.
- `python scripts/transactions.py db rebuild` — force-rebuild balance
  tables from a fresh log replay (the import path runs this automatically;
  this is the manual escape hatch).
- `python scripts/transactions.py db dump` — emit every row as JSON
  (suitable for ad-hoc analysis or backup).
- `python scripts/transactions.py db stats` — count by type, distinct
  tickers, date range, schema version.
- `python scripts/transactions.py self-check` — unit tests for parser,
  replay, P&L math, period boundaries, and the DB import paths
  (md / csv / json / db_add / load_holdings_lots round-trip). Treat
  failures as a regression gate.

## 9. What does **not** belong in transactions.db

- Watchlist or thesis updates that do not move money.
- Speculative limit orders that have not filled.
- Strategy text or research — those live in `SETTINGS.md` and report
  context, not the event log.
- Backfilled fictional history. Only record events that actually happened.

## 10. Documented input shapes

The `parse_holdings()` reader (used only by the one-shot `migrate`) accepts
the iteration-2 `HOLDINGS.md` lot format:

```
<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]
<SYMBOL> <quantity> @ <cost> on <YYYY-MM-DD> [crypto|FX]
<CURRENCY>: <amount> [cash]
```

This shape is preserved purely for migration purposes. New ingestion
should always use CSV / JSON / message paths described in §4.
