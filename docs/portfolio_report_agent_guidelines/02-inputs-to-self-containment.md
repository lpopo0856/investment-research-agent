## 4. Inputs

### 4.1 HOLDINGS.md — lot format

Every lot follows:

```
<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]
```

- `on YYYY-MM-DD` is the **acquisition date** for that lot. It powers per-lot tooltips and hold-period analytics.
- `[<MARKET>]` is the **market-type tag** — required for new lots. It tells the price agent which `yfinance` symbol convention to use and which fallback hierarchy applies. The tag is the *single source of truth* for routing; do **not** rely on the bare-ticker shape to guess the market.
- Crypto / FX use `<SYMBOL> <quantity> @ <cost> on <YYYY-MM-DD> [<MARKET>]` (no "shares").
- Cash uses `<CURRENCY>: <amount> [cash]` (no "shares", no `@ cost`, no date).
- `?` is allowed in place of cost or date when truly unknown — render the affected metric as `n/a` in the report (see §9.6). **Never invent a value.**
- A ticker may have multiple lots across the four buckets (`Long Term`, `Mid Term`, `Short Term`, `Cash Holdings`). Aggregate per ticker for the holdings table; keep the lot-level array embedded in the page so the per-lot popover can render without a re-fetch.

#### Market-type tag values

| Tag | Meaning | Primary quote routing |
|---|---|---|
| `[US]` | NYSE / NASDAQ / AMEX listed equity or ETF | bare ticker (`NVDA`); dotted classes use Yahoo dash form (`BRK.B` → `BRK-B`) |
| `[TW]` | Taiwan listed equity (TWSE) | `<code>.TW` (`2330.TW`) |
| `[TWO]` | Taiwan OTC equity (TPEx) | `<code>.TWO` |
| `[JP]` | Tokyo Stock Exchange | `<code>.T` |
| `[HK]` | Hong Kong Stock Exchange | `<code>.HK` |
| `[LSE]` | London Stock Exchange (UCITS ETFs etc.) | `<code>.L` |
| `[crypto]` | Crypto asset | Binance public spot `<SYM>USDT`; CoinGecko by coin id |
| `[FX]` | Currency pair held as position | `<PAIR>=X` (`USDJPY=X`) |
| `[cash]` | Cash / cash-equivalent (no price fetch) | — |

If a legacy lot has no `[<MARKET>]` tag, the price agent falls back to a heuristic (suffix → market, known crypto / fiat lists). The heuristic is best-effort; always migrate the line to a tagged form when you next touch it. The holdings-update agent (§ `docs/holdings_update_agent_guidelines.md`) requires the tag for all new lots.

### 4.2 SETTINGS.md

- Read for output language, tone, and (if present) position-sizing rails. Settings rails override defaults in this spec when in conflict.
- Language enforcement is in §5.
- Optional API keys are listed in §8.6.

### 4.3 Auto-classify on every run

- Auto-read all positions from `HOLDINGS.md` at run time. Do not hard-code holdings, do not assume any specific ticker is present, and re-classify on every run.
- Auto-classify each holding by asset class, sector, and theme based on current data. Buckets are not fixed — examples include `ETF`, single stock, crypto, cash, semiconductor, AI, energy, aerospace, financials, healthcare, consumer, industrial, optical / data center, defense, other. Use whatever fits the actual book.

---

## 5. Output language (HARD)

`SETTINGS.md` declares the output language. **Every** user-facing string in the HTML must be in that language — no bilingual mixing, no untranslated headers, no English fallbacks because "the term has no good translation".

### 5.1 Rules

- The `<html lang="…">` attribute must match (`zh-TW`, `en`, `ja`, etc.).
- Every section title, table header, KPI label, badge, tag, callout text, action label, tooltip / popover content, and prose paragraph must be in the SETTINGS language.
- Bilingual headers like `代號 Symbol` or `損益 P&L` are **not** acceptable. Pick one — the SETTINGS language.
- Latest-price source / freshness labels must be translated when they are natural-language labels. Provider names such as `Twelve Data`, `Finnhub`, `CoinGecko`, and `TWSE` may remain in English because they are source names. **Do not show session-state badges in any language.**
- Tag chips (`High vol`, `Long`, `Mid`, `Rich val`): translate every visible label. Default English class names stay (the CSS hooks); the visible text is translated.
- The HTML `<title>` must also be in the SETTINGS language (the filename itself stays ASCII per §6).
- If `SETTINGS.md` is missing or unparseable, default to **English** and surface the missing setting as a `n/a` in the masthead meta row.
- `scripts/generate_report.py` must load **stable built-in dictionaries** for `english`, `traditional chinese`, and `simplified chinese` from JSON files under `scripts/i18n/`.
- If `SETTINGS.md` requests another single language, the **executing agent** should translate `scripts/i18n/report_ui.en.json` into a temporary JSON overlay and pass it into the renderer via `--ui-dict` or `context["ui_dictionary"]`. The renderer itself should not call external translation services.

### 5.2 Allowed non-language tokens (allow-list)

These tokens may remain as-is regardless of SETTINGS language:

- Ticker symbols (`NVDA`, `2330.TW`, `BTC`)
- Currency codes (`USD`, `TWD`)
- Unit symbols (`%`, `$`, `NT$`)
- ISO dates (`2026-04-27`)
- URL hostnames in citations
- Bracketed source names that are inherently English (`Reuters`, `StockAnalysis`)

### 5.3 Self-check before delivery

Search the rendered HTML for stray English (or non-SETTINGS-language) words. Every hit that is not in the §5.2 allow-list must be translated or removed.

---

## 6. File output

- The HTML must be written to `reports/`.
- HTML filename: `YYYY-MM-DD_HHMM_portfolio_report.html`
- Use the **local clock at execution time** for the timestamp prefix.
- **Only** the HTML is produced. No Markdown summary, no companion files. The HTML is the single deliverable.

---

## 7. Self-containment rules

### 7.1 Hard rules

- The HTML must be a single self-contained file directly openable in the browser: all CSS, charts, data, and any required interactive logic must be inlined in the same HTML.
- Do not leave external generator scripts, external CSS, CDN dependencies, build artifacts, or frontend project structure in the repo.
- If you need a temporary script to wrangle data, keep it in `/tmp` or use it once. **Do not** check it in as a deliverable.
- The final delivery should contain only the requested HTML and any necessary updates to the spec docs.
- The HTML must not depend on local relative paths, `file://` images, external fonts, external chart libraries, or any service that requires login or payment.
- External URLs are allowed *only* as data-source citations. Never as runtime style, generic script source, chart-library dependency, or market-data fetch endpoint.
- The generated HTML must not fetch market data at runtime. All latest-price retrieval happens at report generation time, and the HTML shows a static snapshot.
- If a value cannot be retrieved, render it as `n/a` and list it under **Sources & data gaps** — do not fill in by guesswork. A value you derived (e.g. P&L from your own cost basis) is fine; a guess at a market data point you could not source is `n/a`. See §9.6 for the two-glyph convention.

### 7.2 Inline JavaScript — restricted use

Inline `<script>` is allowed **only** for optional cell-popover ergonomics. Anything else must use SVG / CSS.

- **Cell popovers** — opens a hover/tap popover with per-lot detail on the Symbol and Price cells. Prefer the CSS-driven descendant popover pattern in §13.3; use a tiny inline script only if CSS cannot cover the target browser behavior.

Constraints:

- All script must be **inline** (`<script>...</script>`); no `<script src=...>`.
- No third-party libraries, no bundlers, no transpiled output. Hand-written ES2020 only.
- The HTML must remain valid and visually complete when JavaScript is disabled or the network is offline.
- No API keys, auth tokens, user-identifying headers, market-data endpoints, `fetch()`, `XMLHttpRequest`, polling timers, or runtime quote refresh logic in the generated HTML.
- API calls may be made only by the agent during report generation, using optional keys read from `SETTINGS.md`.

### 7.3 Self-containment grep

After producing the report, verify:

- No `<script src=...>`.
- No `<link rel="stylesheet"...>`.
- No `<script>` or `<link>` that pulls a chart library from a CDN.
- Inline `<style>`, inline SVG, inline tables, inline static data, and the optional popover-only inline JS are allowed.
- Prefer SVG / CSS over JavaScript. If `<script>` appears, confirm it does not contain `fetch`, `XMLHttpRequest`, API keys, or market-data endpoints.

Suggested check:

```sh
rg -n "<script\\s+src=|<link[^>]+stylesheet|href=.*\\.css" reports/*.html
```

For each hit, confirm it is purely a citation link; if it is anything else, inline it.

---

