## 8. Latest-price retrieval pipeline

> **Account resolution.** All scripts in this section read positions from the active account's `transactions.db` (resolved via `--account <name>` or `accounts/.active`; fallback `accounts/default/`). The market-data cache (`market_data_cache.db`) is shared at the repo root and is **not** per-account. Demo runs use explicit `--db demo/transactions.db` — do not use `--account` for demo.

### 8.0 Subagent prerequisites — `yfinance` + `requests` (HARD)

`requests` is required (HTTP for the no-token tiers). `yfinance` is *preferred* but no longer required: when missing, both `scripts/fetch_prices.py` and `scripts/fetch_history.py` ask the operator once whether to `pip install yfinance` (interactive shells only); decline (or non-interactive) tiers down to web pages / no-token public sources per §8.3.1 without aborting. `--skip-yfinance` on `fetch_prices.py` forces the skip path.

Before ad-hoc yfinance code or a REPL quote probe (NOT needed when running the scripts themselves — they self-probe):

1. Probe: `python3 -c "import yfinance, requests"`.
2. If missing, run first successful command and audit log it:
   - `python3 -m pip install --quiet --upgrade yfinance requests`
   - `pip install --quiet --upgrade yfinance requests`
   - `uv pip install --quiet yfinance requests`
3. Re-probe. If still failing: report install error; mark unresolved tickers `price_source="n/a"` only after §8.5 tiers are walked; do not retry yfinance.
4. Log `yfinance.__version__` when present (`n/a` is acceptable when the operator declined install).
5. Add `subagent_prerequisites`: `installed=<bool>`, `version=<version|n/a>`, `install_command=<command|skipped|declined>`.

Do not: swallow `ImportError` in ad-hoc code; use non-quiet install; use `sudo` / `--user`; pin versions unless user asks; assume a previous install; stop at script `price_source="n/a"`. `n/a` or `agent_web_search:TODO_required` from the script is a handoff to the agent for tier 3 / tier 4; `fetch_prices.py` and `generate_report.py` must hard-fail on that marker unless the operator explicitly passes `--allow-incomplete-fallbacks` for debugging. A run with yfinance declined is **not** a hard fail by itself — the chain still produces values from the other tiers.

### 8.1 Source hierarchy + workflow gate

Asset-native first; never yfinance-first globally.

| Tier | Rule |
|---|---|
| 1 listed securities `[US/TW/TWO/JP/HK/LSE]` | Stooq JSON primary: `https://stooq.com/q/l/?s=<ticker>.<suffix>&f=sd2t2ohlcv&h&e=json`; after every hit verify currency via Yahoo v8 chart `chart.result[0].meta.currency`; then yfinance per-ticker secondary. |
| 1 FX | yfinance `<PAIR>=X` primary; Stooq does not cover FX. |
| 1 crypto | Binance public spot where pair exists → CoinGecko. Do not use yfinance / Stooq for crypto unless spec changes. |
| 2 | Reserved; authenticated/keyed providers have been removed. |
| 3 agent web search / quote pages | Mandatory after unresolved automated tiers. Search price **and trading currency**; read public pages; record source URL, retrieval time, timestamp / prior-close context. |
| 4 no-token public endpoints | Mandatory after tier 3 fails or blocks. Record as no-token fallback. |

Accept only values passing §8.7 Freshness gate. Conflict rule: prefer fresher credible timestamp + clearer market coverage; audit rejected source + reason.

**Render gate:** every non-cash ticker must have `latest_price` + source OR `fallback_chain` containing real tier 3 and tier 4 entries (`tier3:exhausted` / `tier4:exhausted` allowed). `agent_web_search:TODO_required` at `fetch_prices.py` output time or render time is a hard failure, because it means the agent stopped before completing tier 3 / tier 4.

### 8.2 Primary policy and required returned fields

- Listed securities: Stooq JSON primary → Yahoo v8 currency verify → yfinance per-ticker secondary → §8.5 fallbacks.
- FX: yfinance pair primary → Frankfurter / Open ExchangeRate-API / official reference → web if needed.
- Crypto: Binance → CoinGecko → web → no-token public endpoints.
- Company/event data priority: company IR, SEC / exchange filings, official releases, then StockAnalysis, Nasdaq, Yahoo Finance, Reuters, CNBC, MarketWatch.
- Refresh each holding for latest price, prior close / 24h ref, move %, timestamp/as-of, currency, exchange, market cap, valuation multiples (PE, forward PE, PS, EV/EBITDA where relevant), volume, next earnings date, imminent material event, failure reason.

### 8.3 yfinance pacing (HARD)

Applies only when yfinance fires (listed secondary or FX primary).

| Rule | Required detail |
|---|---|
| Per-ticker only | Use `yf.Ticker(symbol, session=session).history(period="5d", interval="1d", auto_adjust=False, timeout=12)`. No `yf.download(...)` batches. |
| Sequential | No internal threading / concurrent Yahoo calls. |
| Gap | `time.sleep(random.uniform(1.5, 2.5))`; never below 1.0s between Yahoo HTTP calls. |
| 429 / `YFRateLimitError` / empty history | **No retry on yfinance.** Mark `yfinance_rate_limited` immediately and tier down to the next source in §8.3.1. |
| Session | Reuse one `requests.Session`; Yahoo v8 currency probe reuses it. |
| Timeout | 10-15s. |
| Audit | `yfinance_request_started_at`, `yfinance_request_latency_ms`, `yfinance_retry_count` (counts §8.4 auto-correction attempts only — rate-limit failures never increment it). |

Rate-limit failures **do not** retry yfinance and never enter §8.4 symbol/format auto-correction; they tier down immediately. If the limiter trips, surface the offending request count + inter-call gap in Sources & data gaps and include a `建議更新 agent spec` pacing note so the next run widens the gap.

### 8.3.1 Rate-limit tier-down (HARD)

```
yfinance 429 / YFRateLimitError / throttled empty history
→ failure_reason=rate_limited (no retry on yfinance), skip §8.4
→ tier 3 web quote pages
→ tier 4 no-token APIs
→ only then price_source="n/a"
```

Rules: distinguish `rate_limited` from `symbol_not_found` / `empty_history` / `exception`; process per ticker; never treat batch failure as whole-book degradation; each walked tier appends `fallback_chain` (`tier3:yahoo_quote_page`, `tier4:stooq_json`, etc.) and updates `price_source`, `price_as_of`, `price_freshness`. Exhaustive `n/a` audit example: `yfinance:rate_limited · web:yahoo/google/nasdaq page-not-found · no-token:stooq empty,yahoo chart 401 · price_freshness:stale_after_exhaustive_search`.

### 8.4 yfinance symbol/format recovery (3 attempts)

Run only for non-rate-limit failures: exception, empty data, stale data, invalid currency/exchange metadata, symbol-not-found, Freshness-gate fail. Max 3 correction attempts after the first failed yfinance call; re-run §8.7 after each.

Allowed targeted fixes: Yahoo symbol normalization (`BRK.B` → `BRK-B`, crypto `BTC-USD`, Taiwan/Japan suffix repair), per-ticker retry after non-rate-limit batch fail, quote-metadata vs short-interval-history swap, shorter/longer period, timezone/calendar repair, small fixed retry after non-429 timeout.

On success record `price_source=yfinance`, `yfinance_auto_fix_applied=true`, attempt count, fix summary. On failure tier down §8.5 and audit original reason + fixes. New successful correction pattern → final reply `建議更新 agent spec` note with failure pattern, fix, proposed wording.

### 8.5 Fallback order and manual-source registry

| Asset / market | Fallback chain |
|---|---|
| US equities / ETFs | Stooq `<ticker>.us` → yfinance per-ticker → Yahoo Finance → Google Finance → Nasdaq → MarketWatch / CNBC / TradingView / StockAnalysis → Yahoo public chart / other no-token. |
| Crypto | Binance spot → CoinGecko public → CoinMarketCap → Coinbase → TradingView → Binance / Coinbase / CoinGecko no-token. |
| TW / TWO | Stooq `<code>.tw` → yfinance `<code>.TW` / `<code>.TWO` → TWSE MIS (`tse_<code>.tw`, `otc_<code>.tw`) → TWSE / TPEx → Yahoo Finance Taiwan → TradingView → TWSE OpenAPI / TPEx official. Currency TWD verified. |
| JP | Stooq `<code>.jp` → yfinance `<code>.T` → Yahoo Finance Japan/global → JPX / issuer pages → Google Finance → TradingView. Currency JPY verified. |
| HK | Stooq `<code>.hk` → yfinance `<code>.HK` → HKEx → Yahoo Finance HK → TradingView. Currency HKD verified. |
| LSE / UCITS | Stooq `<code>.uk` → yfinance `<code>.L` → Yahoo Finance UK → Google Finance → LSE site. Currency must be verified; `.UK` may be GBP shares or USD UCITS (e.g. VWRA). |
| FX / cash conversion | yfinance `<PAIR>=X` → Frankfurter (ECB-backed) → Open ExchangeRate-API → official reference feeds → Google Finance / Yahoo Finance / central bank pages. |

Web-search source priority: US `Yahoo → Google → Nasdaq → MarketWatch/CNBC/TradingView/StockAnalysis`; crypto `CoinGecko → CoinMarketCap → Binance → Coinbase → TradingView`; TW `TWSE/TPEx → Yahoo Taiwan → TradingView`; JP `Yahoo JP/global → JPX/issuer → Google`; LSE `Yahoo UK → Google → LSE`; FX `Google → Yahoo → official central bank`.

No-token samples: Stooq `https://stooq.com/q/l/?s=NVDA.US&f=sd2t2ohlcv&h&e=json`; Yahoo chart `https://query1.finance.yahoo.com/v8/finance/chart/NVDA?range=5d&interval=1d`; Binance `https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT`; Coinbase `https://api.exchange.coinbase.com/products/BTC-USD/ticker`; CoinGecko `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd`; TWSE MIS `https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_2330.tw`; TWSE daily `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_AVG_ALL`; ECB `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`.

Stooq currency rule: Stooq has no currency. Script verifies through Yahoo v8 chart and records `currency_verify:yahoo_chart`. Manual Stooq use must reproduce the lookup or web-verify exchange currency; examples `2330.TW` TWD, `7203.JP` JPY, `VWRA.UK` USD despite `.UK`, ADRs `.US` USD. Never infer currency from Stooq suffix alone.

### 8.6 No-token data sources only

Price retrieval uses only no-token public endpoints (Stooq, Yahoo public chart, Binance, CoinGecko, Frankfurter / ECB, Open ExchangeRate-API, TWSE / TPEx) and `yfinance`. There are no paid-source overrides; never leak tokens, authenticated URLs, or third-party credentials into HTML.

### 8.7 Freshness gate

Determine exchange calendar, timezone, local market date, regular-session state before accepting price.

| Market state | Accept | Reject until exhausted |
|---|---|---|
| Session open today | Same trading-date current/intraday latest; timestamp/page must not be prior close. | Prior-session close, EOD-only, clearly delayed. |
| Session closed today | Same trading-date latest/official close/closing auction; intraday timestamp must be today. | Previous trading-day close. |
| Today not opened yet | Previous opened trading-day official/credible close minimum. | Older closes. |
| Weekend/holiday/closed all day | Most recent opened trading-day official/credible close. | Older closes; if unverifiable `n/a`. |
| 24/7 crypto | Fresh spot with retrieval/source timestamp. | Stale snapshot when fresher source exists. |

Opened-market strictness: prior-session/stale value cannot be accepted until Stooq primary, yfinance secondary, up to 3 yfinance symbol fixes, web pages, and no-token fallbacks are exhausted. Degraded fallback after exhaustion: use freshest credible value only with `price_freshness=stale_after_exhaustive_search`, full attempted-source audit, visible data-gap/alert text. Unsourced numeric guesses forbidden; own derivations label `estimate`.

### 8.8 Stored fields per ticker

Persist: `latest_price`, `prior_close` or 24h ref, `move_pct`, `price_source`, `price_as_of`, `price_freshness`, `market_state_basis`, `currency`, `exchange`, failure reason, yfinance correction attempts/fix/final outcome, pacing retry fields from §8.3.

Persist FX under `prices.json["_fx"]`: `base`, `required_currencies`, `rates` keyed `<BASE>/<CCY>`, `details` with source/freshness/fallback audit for each pair. Do not source FX from `SETTINGS.md` or `report_context.json`.

### 8.9 Historical-data hard fill (`fetch_history.py`) — HARD

`fetch_history.py` runs the same tier-1/tier-2 chain (Stooq, yfinance, Binance, CoinGecko, Frankfurter, etc.) for the multi-day OHLC and FX series feeding §10.1.5 boundary lookups, and writes through `market_data_cache.db` so subsequent runs see hits. When a ticker or FX pair lands in `_history_meta.tickers_failed` / `fx_failed` AND has zero rows in the merged `_history` / `_fx_history` (i.e. no API result and no prior cache), the script exits 5 with a per-symbol gap list — same failure semantics as `fetch_prices.py` exit 5 in §8.0.

The agent must close every gap before downstream pipeline steps run. Use the **same** absolute `prices.json` path as the rest of the run — for deliverable reports that path is `$REPORT_RUN_DIR/prices.json` under `/tmp` (never the repo root); see main `portfolio_report_agent_guidelines.md` — Intermediate files.

1. Read the stderr block; for each failing ticker/FX pair, web-search the missing OHLC closes / FX rates for the lookback window using the source priorities in §8.5 (`Yahoo → Google → Stooq` for US, `TWSE/TPEx → Yahoo TW` for TW, `Binance/CoinGecko` for crypto, `Frankfurter / Open ER / central bank` for FX).
2. Apply the §8.7 Freshness gate to every researched value (no stale closes when a fresher credible source is reachable).
3. Inject the rows via `python scripts/fill_history_gap.py ticker --account default --ticker <T> --market <MKT> --rows-json '[{"date":"YYYY-MM-DD","close":N}, ...]' --merge-into "$REPORT_RUN_DIR/prices.json"` (or `fx --pair BASE/QUOTE --rows-json '[{"date":"...","rate":N}, ...]'`). The helper writes through `market_data_cache.db` with `source=agent_web_search` and merges the rows into the active prices file.
4. Re-run `python scripts/fetch_history.py --account default --merge-into "$REPORT_RUN_DIR/prices.json"`. Repeat until exit 0.

`--allow-incomplete` on `fetch_history.py` is debug-only (parallel to `--allow-incomplete-fallbacks` on `fetch_prices.py`); using it for a deliverable run is a workflow violation because §10.1.5 boundary scoring silently degrades to 0 for tickers without history. Manual rows must carry real source provenance: when the agent edits `_history_meta.tickers_ok` after a fill, the underlying cache row already records `source=agent_web_search` and the retrieval timestamp — that is the audit trail consumers should rely on.
