## 4. Inputs

### 4.1 `transactions.db` — positions and cash

**Path resolution:** `transactions.db` lives under the active account directory (`accounts/<active>/transactions.db`). Pass `--account <name>` to target a specific account; omitting it resolves in order: `accounts/.active` pointer → `accounts/default/` → hard error. Explicit `--db <path>` overrides `--account` for that flag (escape hatch; used by demo runs).

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

### 4.2 `SETTINGS.md`

**Path resolution:** `SETTINGS.md` lives under the active account directory (`accounts/<active>/SETTINGS.md`), resolved by the same `--account` / `accounts/.active` / `default` chain as §4.1. Explicit `--settings <path>` overrides `--account` for that flag.

Read every run for account description, language, tone, `## Investment Style And Strategy`, optional sizing rails, optional API keys (§8.6). Settings rails override spec defaults. The account description is a short purpose label from `## Account description (optional)` / `- Description: ...`; it is metadata for identifying account intent, not a strategy substitute and not a place for secrets.

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

**Safety:** `scripts/transactions.py` resolves the active account via `--account` / `accounts/.active` / `accounts/default/` when `--db` is omitted. For demo work, always pass **`--db demo/transactions.db`** (or an absolute path to that file) to every pipeline step that reads transactions — this is the intentional explicit-path escape hatch; do **not** use `--account` for demo runs. `scripts/account.py` `check_pairing()` validates that `--db` and `--settings` point to the same account directory when both are supplied; mismatched explicit paths produce a pairing error. **`fetch_history.py` and `fill_history_gap.py` default to `market_data_cache.db` in the current working directory** when `--cache` is omitted — for demo work, always pass **`--cache demo/market_data_cache.db`** on those two scripts so the repository root cache is not mixed with the synthetic ledger. Do not run demo bootstrap commands against production paths.
Full runbook: [`demo/README.md`](../../demo/README.md).

There is no demo-specific report pipeline, no committed demo
`report_context.json`, and no auto-fill script for editorial content. Only the
transaction ledger is synthetic. Everything else must be generated exactly as
in a real report for the selected `report_type` + `account_scope`: latest-price
retrieval, history retrieval, snapshot math, profit panel, transaction analytics,
section-gated editorial context, Strategy readout / reviewer pass when rendered,
and HTML rendering. A demo `portfolio_report` follows the same portfolio policy:
no `trading_psychology`, news, catalysts, consensus, recommendations, actions,
or §10.5 temp-researcher workflow. Parser-test/offline flags
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
- **Any other language is honored.** `SETTINGS.md` `Language:` accepts (a) curated natural-language names and endonyms — `français`, `Deutsch`, `Português`, `Brazilian Portuguese`, `Español`, `Italiano`, `Nederlands`, `Русский`, `العربية`, `日本語`, `한국어`, `ไทย`, `Türkçe`, `Polski`, `Bahasa Indonesia`, `हिन्दी`, etc. — and (b) any well-formed BCP-47 code (`fr`, `de-CH`, `pt-BR`, `es-419`, `zh-Hant-TW`, `en-IN`). The renderer normalizes casing (`fr-fr` → `fr-FR`, `zh-hant` → `zh-Hant`) so `<html lang>` is always valid. Unrecognized input falls back to `en` rather than emitting an invalid tag.

#### 5.1.1 Phase 0 — UI dictionary translation (HARD GATE)

When `transactions.py snapshot` finishes, it inspects the resolved locale.
If the locale is **not** in the built-in set (`en`, `zh-Hant`, `zh-Hans`),
it prints a `NEXT STEP REQUIRED` block to stderr naming the source file,
target file, and the `--ui-dict` flag the renderer needs. The executing
agent **must** complete this before rendering.

**Translator identity (HARD):** the executing agent translates the
dictionary **itself**, in-context, with the same model running the rest
of the pipeline. Do **not** call Google Translate, DeepL, Bing
Translator, Papago, Yandex, or any other external translation service /
HTTP API / CLI wrapper. The dictionary is small (~245 keys, ~5 KB) and
domain-specific (`R:R`, `MWR annualized`, `Profit Factor`, `Kill
action`, `Portfolio fit`, `pp of NAV`, `Variant`, `Anchor`, action
buckets `Must` / `May` / `Avoid` / `Fix Data`); a generic translator
mangles these terms, drops `{format}` placeholders, escapes special
chars (`<`, `>`, `&`, `Δ`), and ignores the §5.1 token-codes
allow-list. The agent already authors news, alerts, and
`trading_psychology` in the target language — the chrome dictionary is
the same kind of work and belongs in the same hand.

**The procedure:**

1. Read `scripts/i18n/report_ui.en.json` (≈245 keys, single self-contained
   JSON object).
2. Translate **every value** into the target language inside the agent's
   own context — no external HTTP / SDK / shell call to a translation
   service. Keep every key unchanged. Preserve every `{format}`
   placeholder (`{base}`, `{pct:.1f}`, `{count}`, `{value:,.0f}` …)
   byte-for-byte. Preserve `<`, `>`, `&`, `Δ`, `·`, `—`, `+`, `−`
   exactly as they appear in the source.
3. Token values stay English as codes (per §5.1 allow-list and §15
   PM-meta): `consensus-aligned`, `variant`, `contrarian`, `rebalance`,
   `cut`, `add`, `trim`, `hold`, `exit`, `watch`. Action labels like
   `Must` / `May` / `Avoid` / `Fix Data` (`actions.must_do`, etc.) are
   chrome **and must be translated**.
4. Write the translated JSON to
   `$REPORT_RUN_DIR/report_ui.<locale>.json` (basename inside the run
   directory, not at the repo root).
5. Pass `--ui-dict $REPORT_RUN_DIR/report_ui.<locale>.json` to
   `generate_report.py`. Equivalently, merge it into
   `report_context.json` as `context["ui_dictionary"]`.

`generate_report.py` exits with code **8** if it loads a snapshot whose
locale has no built-in dictionary and no `--ui-dict` /
`context["ui_dictionary"]` override is supplied. There is no English
fallback for non-English `SETTINGS.md` `Language:` — chrome and content
must agree. The renderer never calls a translation service either; the
agent owns the translation step the same way it owns news, alerts, and
psychology authoring.

### 5.2 Allow-list

May remain as-is: tickers, currency codes, unit symbols, ISO dates, URL hostnames in citations, inherently English source names (`Reuters`, `StockAnalysis`).

### 5.3 Delivery check

Search rendered HTML for stray non-SETTINGS-language text; every non-allow-listed hit must be translated/removed.

---

## 6. File output

Write exactly one HTML file whose filename encodes both axes: `accounts/<active>/reports/YYYY-MM-DD_HHMM_single_account_<daily_report|portfolio_report>.html` for single-account runs, or `accounts/_total/reports/YYYY-MM-DD_HHMM_total_account_<daily_report|portfolio_report>.html` for total-account scope. The active account is resolved via `--account <name>` or `accounts/.active`; omitting `--account` defaults to `accounts/default/`. For **demo-ledger-only** runs (`--db demo/transactions.db`), write the same type/scope filename pattern under **`demo/reports/`** instead so the artifact stays under `demo/` and does not sit beside user reports. No Markdown summary or companion files in the repo.

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
