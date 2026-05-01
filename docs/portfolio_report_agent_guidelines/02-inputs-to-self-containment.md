## 4. Inputs

### 4.1 `transactions.db` — positions and cash

Positions are loaded via `transactions.load_holdings_lots(db_path)` which
returns the materialized `open_lots` + `cash_balances` tables as a
`List[Lot]` compatible with the report renderer's lot shape. Each row carries:

| Column     | Meaning |
|------------|---------|
| `ticker`   | Canonical ticker (uppercase; preserves dotted suffix like `2330.TW`) |
| `qty`      | Open quantity (floats; crypto allows fractional) |
| `cost`     | Per-unit cost basis in trade currency |
| `acq_date` | ISO YYYY-MM-DD; the lot's BUY date |
| `bucket`   | `Long Term` / `Mid Term` / `Short Term` |
| `market`   | One of `US` / `TW` / `TWO` / `JP` / `HK` / `LSE` / `crypto` / `FX` |
| `currency` | Trade currency (USD / TWD / JPY / …) |

Routing per market tag:

| Tag | Meaning | Routing |
|---|---|---|
| `US`     | NYSE/NASDAQ/AMEX equity/ETF | bare ticker; dotted class Yahoo dash (`BRK.B` → `BRK-B`) |
| `TW`     | TWSE | `<code>.TW` |
| `TWO`    | TPEx | `<code>.TWO` |
| `JP`     | Tokyo | `<code>.T` |
| `HK`     | Hong Kong | `<code>.HK` |
| `LSE`    | London / UCITS | `<code>.L` |
| `crypto` | Crypto | Binance `<SYM>USDT`; CoinGecko id |
| `FX`     | Currency pair | `<PAIR>=X` |
| `cash`   | Cash/equivalent | no price fetch (one row per currency in `cash_balances`) |

Drift between the materialized tables and a fresh log replay is caught by
`transactions.py verify`; on mismatch run `db rebuild`. The renderer must
not invent or hard-code holdings — always read fresh from the DB.

For historical migrations only, `transactions.py migrate --holdings HOLDINGS.md`
can bootstrap a DB from the pre-existing markdown lot file. Report generation
never reads `HOLDINGS.md`.

### 4.2 `SETTINGS.md`

Read every run for language, tone, `## Investment Style And Strategy`, optional sizing rails, optional API keys (§8.6). Settings rails override spec defaults.

### 4.3 Auto-classify

Auto-read all positions every run; never hard-code holdings or assume tickers. Re-classify by asset class/sector/theme from current data. Buckets flexible: ETF, single stock, crypto, cash, semiconductor, AI, energy, aerospace, financials, healthcare, consumer, industrial, optical/data center, defense, other.

### 4.4 Demo ledger (isolated `transactions.db` + cache)

The repo ships a **non-production** transaction ledger under `demo/` for
generating demo HTML reports without touching the root `transactions.db`:

| Artifact | Role |
|----------|------|
| `demo/transactions_history.json` | Canonical JSON seed (multi-year synthetic flow); safe to commit. |
| `demo/bootstrap_demo_ledger.py` | Regenerates the JSON from code (replay-validated) and **`--apply`** rebuilds `demo/transactions.db`. |
| `demo/transactions.db` | Gitignored SQLite store — **not** the user’s root `transactions.db`. |
| `demo/market_data_cache.db` | Optional gitignored cache — use with **`--cache demo/market_data_cache.db`** on `fetch_history.py` / `fill_history_gap.py` so demo runs do **not** use the root `market_data_cache.db`. |
| `demo/reports/` | Optional directory for demo-only HTML output (gitignored); keeps deliverables out of user `reports/`. |

**Safety:** `scripts/transactions.py` defaults to `./transactions.db` when
`--db` is omitted. For demo work, always pass **`--db demo/transactions.db`**
(or an absolute path to that file) to every pipeline step that reads
transactions. **`fetch_history.py` and `fill_history_gap.py` default to
`market_data_cache.db` in the current working directory** when `--cache` is omitted — for demo work, always
pass **`--cache demo/market_data_cache.db`** on those two scripts so the
repository root cache is not mixed with the synthetic ledger. Do not run demo
bootstrap commands against production paths.
Full runbook: [`demo/README.md`](../../demo/README.md).

There is no demo-specific report pipeline, no committed demo
`report_context.json`, and no auto-fill script for editorial content. Only the
transaction ledger is synthetic. Everything else must be generated exactly as
in a real report: latest-price retrieval, history retrieval, snapshot math,
profit panel, transaction analytics, mandatory `trading_psychology`,
theme/sector classification, news, catalysts, consensus, recommendations,
Strategy readout, reviewer pass, and HTML rendering. Parser-test/offline flags
that produce `n/a` quotes are not valid for user-facing demo reports.

---

## 5. Output language (HARD)

Every user-facing HTML string uses SETTINGS language; no bilingual labels or English fallback unless allowed.

### 5.1 Rules

- `<html lang>` and `<title>` match language; filename remains ASCII.
- Translate section titles, headers, KPI labels, badges, tag text, callouts, action labels, tooltips/popovers, prose, natural-language source/freshness labels. Provider names may stay English (`Twelve Data`, `Finnhub`, `CoinGecko`, `TWSE`). No session-state badges.
- Translate visible tag chips (`High vol`, `Long`, `Mid`, `Rich val`); CSS class hooks stay English.
- Missing/unparseable `SETTINGS.md` → English default and masthead meta `n/a`.
- Renderer loads stable dictionaries for English / Traditional Chinese / Simplified Chinese from `scripts/i18n/`.
- Other single language → executing agent translates `scripts/i18n/report_ui.en.json` to a JSON file under `$REPORT_RUN_DIR` and passes `--ui-dict` (or `context["ui_dictionary"]`); renderer does not call translation services.

### 5.2 Allow-list

May remain as-is: tickers, currency codes, unit symbols, ISO dates, URL hostnames in citations, inherently English source names (`Reuters`, `StockAnalysis`).

### 5.3 Delivery check

Search rendered HTML for stray non-SETTINGS-language text; every non-allow-listed hit must be translated/removed.

---

## 6. File output

Write exactly one HTML file to `reports/YYYY-MM-DD_HHMM_portfolio_report.html` using local clock (production / user runs). For **demo-ledger-only** runs (`--db demo/transactions.db`), write the same filename pattern under **`demo/reports/`** instead so the artifact stays under `demo/` and does not sit beside user reports. No Markdown summary or companion files in the repo.

**Pipeline intermediates (HARD):** `fetch_prices` / `fetch_history` / `fill_history_gap` / `transactions.py snapshot` / `report_context.json` / optional `--ui-dict` JSON for the report run **must** use paths under `$REPORT_RUN_DIR` in `/tmp` only (see main `portfolio_report_agent_guidelines.md` — Intermediate files and cleanup). After successful render + Appendix A, delete the whole directory.

---

## 7. Self-containment rules

### 7.1 Hard rules

Single directly-openable HTML: inline CSS, SVG/CSS charts, static data, optional popover-only inline JS. No external generator scripts, CSS, CDN, build artifacts, frontend structure, relative/local image paths, external fonts/chart libs, login/payment services, runtime market-data fetch. External URLs only data-source citations. Market data is generation-time static. Missing sourced value → `n/a` + Sources/data-gaps audit; own derivations OK; guesses forbidden.

Temp wrangling scripts and one-off scrapers go under `/tmp` and are removed with the run. Portfolio pipeline JSON is never “repo-local temp”; it lives under `$REPORT_RUN_DIR` and is removed after success. Final delivery = requested HTML under `reports/` (or **`demo/reports/`** for demo-ledger runs) and any explicitly requested spec-doc updates only.

### 7.2 Inline JavaScript

Allowed only for optional Symbol/Price popover ergonomics if CSS descendant pattern (§13.3) cannot cover target browser behavior. Constraints: inline `<script>` only; no `<script src>`; no third-party libs/bundlers/transpiled output; hand-written ES2020; page remains valid/complete with JS disabled/offline; no API keys/tokens/user-identifying headers/market endpoints/`fetch`/XHR/polling/runtime quote refresh. Agent may call APIs only during generation using optional `SETTINGS.md` keys.

### 7.3 Self-containment grep

Run:

```sh
rg -n "<script\\s+src=|<link[^>]+stylesheet|href=.*\\.css" reports/*.html
```

For each hit, verify citation-only; otherwise inline. If any `<script>` exists, verify no `fetch`, `XMLHttpRequest`, API keys, market endpoints.
