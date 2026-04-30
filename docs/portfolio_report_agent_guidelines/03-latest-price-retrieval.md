## 8. Latest-price retrieval pipeline

### 8.0 Subagent prerequisites — `yfinance` + `requests` (HARD)

Before `scripts/fetch_prices.py`, ad-hoc yfinance code, or a REPL quote probe:

1. Probe: `python3 -c "import yfinance, requests"`.
2. If missing, run first successful command and audit log it:
   - `python3 -m pip install --quiet --upgrade yfinance requests`
   - `pip install --quiet --upgrade yfinance requests`
   - `uv pip install --quiet yfinance requests`
3. Re-probe. If still failing: report install error; mark unresolved tickers `price_source="n/a"` only after §8.5 tiers are walked; do not retry yfinance.
4. Log `yfinance.__version__`.
5. Add `subagent_prerequisites`: `installed=<bool>`, `version=<version|n/a>`, `install_command=<command|skipped>`.

Do not: swallow `ImportError`; use non-quiet install; use `sudo` / `--user`; pin versions unless user asks; assume a previous install; stop at script `price_source="n/a"`. `n/a` or `agent_web_search:TODO_required` from the script is a handoff to the agent for tier 3 / tier 4; `fetch_prices.py` and `generate_report.py` must hard-fail on that marker unless the operator explicitly passes `--allow-incomplete-fallbacks` for debugging.

### 8.1 Source hierarchy + workflow gate

Asset-native first; never yfinance-first globally.

| Tier | Rule |
|---|---|
| 1 listed securities `[US/TW/TWO/JP/HK/LSE]` | Stooq JSON primary: `https://stooq.com/q/l/?s=<ticker>.<suffix>&f=sd2t2ohlcv&h&e=json`; after every hit verify currency via Yahoo v8 chart `chart.result[0].meta.currency`; then yfinance per-ticker secondary. |
| 1 FX | yfinance `<PAIR>=X` primary; Stooq does not cover FX. |
| 1 crypto | Binance public spot where pair exists → CoinGecko. Do not use yfinance / Stooq for crypto unless spec changes. |
| 2 keyed APIs | Use relevant optional keys from `SETTINGS.md`; missing / quota-limited keys are skipped. |
| 3 agent web search / quote pages | Mandatory after unresolved tiers 1-2. Search price **and trading currency**; read public pages; record source URL, retrieval time, timestamp / prior-close context. |
| 4 no-token APIs | Mandatory after tier 3 fails or blocks. Record as no-token fallback. |

Accept only values passing §8.7 Freshness gate. Conflict rule: prefer fresher credible timestamp + clearer market coverage; audit rejected source + reason.

**Render gate:** every non-cash ticker must have `latest_price` + source OR `fallback_chain` containing real tier 3 and tier 4 entries (`tier3:exhausted` / `tier4:exhausted` allowed). `agent_web_search:TODO_required` at `fetch_prices.py` output time or render time is a hard failure, because it means the agent stopped before completing tier 3 / tier 4.

### 8.2 Primary policy and required returned fields

- Listed securities: Stooq JSON primary → Yahoo v8 currency verify → yfinance per-ticker secondary → §8.5 fallbacks.
- FX: yfinance pair primary → keyed Twelve Data / Alpha Vantage → Frankfurter / Open ExchangeRate-API / official reference → web if needed.
- Crypto: Binance → CoinGecko → keyed CoinGecko / Alpha Vantage / FMP → web → no-token.
- Company/event data priority: company IR, SEC / exchange filings, official releases, then StockAnalysis, Nasdaq, Yahoo Finance, Reuters, CNBC, MarketWatch.
- Refresh each holding for latest price, prior close / 24h ref, move %, timestamp/as-of, currency, exchange, market cap, valuation multiples (PE, forward PE, PS, EV/EBITDA where relevant), volume, next earnings date, imminent material event, failure reason.

### 8.3 yfinance pacing (HARD)

Applies only when yfinance fires (listed secondary or FX primary).

| Rule | Required detail |
|---|---|
| Per-ticker only | Use `yf.Ticker(symbol, session=session).history(period="5d", interval="1d", auto_adjust=False, timeout=12)`. No `yf.download(...)` batches. |
| Sequential | No internal threading / concurrent Yahoo calls. |
| Gap | `time.sleep(random.uniform(1.5, 2.5))`; never below 1.0s between Yahoo HTTP calls. |
| 429 / `YFRateLimitError` / empty history | Backoff 30s → 60s → 120s → 300s, max 3 retries; then mark `yfinance_rate_limited` and tier down. |
| Session | Reuse one `requests.Session`; Yahoo v8 currency probe reuses it. |
| Timeout | 10-15s. |
| Audit | `yfinance_request_started_at`, `yfinance_request_latency_ms`, `yfinance_retry_count`. |

Rate-limit backoff has its own max-3 retry ceiling and never enters §8.4 symbol/format auto-correction. If limiter trips, surface offending request count + inter-call gap in Sources & data gaps and include a `建議更新 agent spec` pacing note.

### 8.3.1 Rate-limit tier-down (HARD)

```
yfinance 429 / YFRateLimitError / throttled empty history
→ §8.3 backoff max 3
→ if success: accept + audit retry_count
→ if fail: failure_reason=rate_limited, skip §8.4
→ tier 2 keyed APIs
→ tier 3 web quote pages
→ tier 4 no-token APIs
→ only then price_source="n/a"
```

Rules: distinguish `rate_limited` from `symbol_not_found` / `empty_history` / `exception`; process per ticker; never treat batch failure as whole-book degradation; each walked tier appends `fallback_chain` (`tier3:yahoo_quote_page`, `tier4:stooq_json`, etc.) and updates `price_source`, `price_as_of`, `price_freshness`. Exhaustive `n/a` audit example: `yfinance:rate_limited(3 backoff) · keyed:no key · web:yahoo/google/nasdaq page-not-found · no-token:stooq empty,yahoo chart 401 · price_freshness:stale_after_exhaustive_search`.

### 8.4 yfinance symbol/format recovery (3 attempts)

Run only for non-rate-limit failures: exception, empty data, stale data, invalid currency/exchange metadata, symbol-not-found, Freshness-gate fail. Max 3 correction attempts after the first failed yfinance call; re-run §8.7 after each.

Allowed targeted fixes: Yahoo symbol normalization (`BRK.B` → `BRK-B`, crypto `BTC-USD`, Taiwan/Japan suffix repair), per-ticker retry after non-rate-limit batch fail, quote-metadata vs short-interval-history swap, shorter/longer period, timezone/calendar repair, small fixed retry after non-429 timeout.

On success record `price_source=yfinance`, `yfinance_auto_fix_applied=true`, attempt count, fix summary. On failure tier down §8.5 and audit original reason + fixes. New successful correction pattern → final reply `建議更新 agent spec` note with failure pattern, fix, proposed wording.

### 8.5 Fallback order and manual-source registry

| Asset / market | Fallback chain |
|---|---|
| US equities / ETFs | Stooq `<ticker>.us` → yfinance per-ticker → Twelve Data → Finnhub → FMP → Tiingo → Alpha Vantage → Polygon → Yahoo Finance → Google Finance → Nasdaq → MarketWatch / CNBC / TradingView / StockAnalysis → Yahoo public chart / other no-token. |
| Crypto | Binance spot → CoinGecko public/demo → keyed CoinGecko → Alpha Vantage / FMP → CoinGecko → CoinMarketCap → Binance → Coinbase → TradingView → Binance / Coinbase / CoinGecko no-token. |
| TW / TWO | Stooq `<code>.tw` → yfinance `<code>.TW` / `<code>.TWO` → TWSE MIS (`tse_<code>.tw`, `otc_<code>.tw`) → Twelve Data / Finnhub / FMP → TWSE / TPEx → Yahoo Finance Taiwan → TradingView → TWSE OpenAPI / TPEx official. Currency TWD verified. |
| JP | Stooq `<code>.jp` → yfinance `<code>.T` → Twelve Data → Finnhub → J-Quants if token → Yahoo Finance Japan/global → JPX / issuer pages → Google Finance → TradingView. Currency JPY verified. |
| HK | Stooq `<code>.hk` → yfinance `<code>.HK` → HKEx → Yahoo Finance HK → TradingView. Currency HKD verified. |
| LSE / UCITS | Stooq `<code>.uk` → yfinance `<code>.L` → Yahoo Finance UK → Google Finance → LSE site. Currency must be verified; `.UK` may be GBP shares or USD UCITS (e.g. VWRA). |
| FX / cash conversion | yfinance `<PAIR>=X` → Twelve Data FX → Alpha Vantage FX → Frankfurter (ECB-backed) → Open ExchangeRate-API → official reference feeds → Google Finance / Yahoo Finance / central bank pages. |

Web-search source priority: US `Yahoo → Google → Nasdaq → MarketWatch/CNBC/TradingView/StockAnalysis`; crypto `CoinGecko → CoinMarketCap → Binance → Coinbase → TradingView`; TW `TWSE/TPEx → Yahoo Taiwan → TradingView`; JP `Yahoo JP/global → JPX/issuer → Google`; LSE `Yahoo UK → Google → LSE`; FX `Google → Yahoo → official central bank`.

No-token samples: Stooq `https://stooq.com/q/l/?s=NVDA.US&f=sd2t2ohlcv&h&e=json`; Yahoo chart `https://query1.finance.yahoo.com/v8/finance/chart/NVDA?range=5d&interval=1d`; Binance `https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT`; Coinbase `https://api.exchange.coinbase.com/products/BTC-USD/ticker`; CoinGecko `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd`; TWSE MIS `https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_2330.tw`; TWSE daily `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_AVG_ALL`; ECB `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`.

Stooq currency rule: Stooq has no currency. Script verifies through Yahoo v8 chart and records `currency_verify:yahoo_chart`. Manual Stooq use must reproduce the lookup or web-verify exchange currency; examples `2330.TW` TWD, `7203.JP` JPY, `VWRA.UK` USD despite `.UK`, ADRs `.US` USD. Never infer currency from Stooq suffix alone.

### 8.6 Optional API keys

Optional fallback only. Never block on missing keys. Never leak keys, tokenized URLs, authenticated payloads into HTML.

| Key | Use |
|---|---|
| `TWELVE_DATA_API_KEY` | US/global equities, FX; prefer price/quote; free tier rate-limited. |
| `FINNHUB_API_KEY` | US/some global equities quote. |
| `COINGECKO_DEMO_API_KEY` | Crypto price / 24h move. |
| `ALPHA_VANTAGE_API_KEY` | US fallback, FX, crypto; low quota. |
| `FMP_API_KEY` | US fallback, valuation/fundamentals; may be delayed/EOD. |
| `TIINGO_API_KEY` | US fallback; optional/rate-limited. |
| `POLYGON_API_KEY` | US fallback; may be delayed/EOD. |
| `JQUANTS_REFRESH_TOKEN` | Japan official delayed data; optional; any email/password fields must never be output. |

### 8.7 Freshness gate

Determine exchange calendar, timezone, local market date, regular-session state before accepting price.

| Market state | Accept | Reject until exhausted |
|---|---|---|
| Session open today | Same trading-date current/intraday latest; timestamp/page must not be prior close. | Prior-session close, EOD-only, clearly delayed. |
| Session closed today | Same trading-date latest/official close/closing auction; intraday timestamp must be today. | Previous trading-day close. |
| Today not opened yet | Previous opened trading-day official/credible close minimum. | Older closes. |
| Weekend/holiday/closed all day | Most recent opened trading-day official/credible close. | Older closes; if unverifiable `n/a`. |
| 24/7 crypto | Fresh spot with retrieval/source timestamp. | Stale snapshot when fresher source exists. |

Opened-market strictness: prior-session/stale value cannot be accepted until Stooq primary, yfinance secondary, up to 3 yfinance symbol fixes, configured APIs, web pages, and no-token fallbacks are exhausted. Degraded fallback after exhaustion: use freshest credible value only with `price_freshness=stale_after_exhaustive_search`, full attempted-source audit, visible data-gap/alert text. Unsourced numeric guesses forbidden; own derivations label `estimate`.

### 8.8 Stored fields per ticker

Persist: `latest_price`, `prior_close` or 24h ref, `move_pct`, `price_source`, `price_as_of`, `price_freshness`, `market_state_basis`, `currency`, `exchange`, failure reason, yfinance correction attempts/fix/final outcome, pacing retry fields from §8.3.

Persist FX under `prices.json["_fx"]`: `base`, `required_currencies`, `rates` keyed `<BASE>/<CCY>`, `details` with source/freshness/fallback audit for each pair. Do not source FX from `SETTINGS.md` or `report_context.json`.
