## 8. Latest-price retrieval pipeline

### 8.0 Subagent prerequisites — install `yfinance` and `requests` (HARD REQUIREMENT)

Before the latest-price subagent runs `scripts/fetch_prices.py` (or any ad-hoc yfinance code), it **must** ensure the `yfinance` and `requests` packages are importable. The subagent owns this step — the main agent should not assume the host environment already has them. `requests` is required for the Stooq, Yahoo v8 chart (currency verification), and keyed-API branches; `yfinance` is required for the secondary fallback (listed securities) and the FX primary branch.

Required actions, in order, every run:

1. **Detect.** Try `python3 -c "import yfinance, requests"`. If both imports succeed, skip to step 4.
2. **Install if missing.** Run **one** of the following — pick the first that succeeds for the active environment, and capture the install log in the source audit:
   - `python3 -m pip install --quiet --upgrade yfinance requests`
   - `pip install --quiet --upgrade yfinance requests`
   - `uv pip install --quiet yfinance requests` (if `uv` is the active package manager)
3. **Re-detect.** Re-run the import probe from step 1. If it still fails, **stop**: report the install error to the user, mark every ticker `price_source = "n/a"`, and let the main agent fall through to the keyed-API / web-search / no-token tiers (§8.5) without retrying yfinance.
4. **Pin sanity.** Log the resolved `yfinance.__version__` once per run (informational only — the spec does not pin a version).
5. **Record.** Capture the prerequisite outcome in **Sources & data gaps** under a `subagent_prerequisites` line: `installed=<true|false>`, `version=<yfinance version or n/a>`, `install_command=<the command that succeeded or "skipped">`. This lets future runs notice when the host environment regressed.

Anti-patterns (do **not** do these):

- Silently swallow `ImportError` and continue with stale prices from model memory.
- Run `pip install` without `--quiet` (noisy output bleeds into the report log).
- Install with `sudo`, `--user`, or any flag that mutates a system path the user did not ask for.
- Skip the install probe because "yfinance was installed last week" — the subagent runs in a fresh process; assume nothing.
- Pin a specific yfinance version in the install command unless the user explicitly asked. Pinning forces re-resolution on every run; let pip resolve the latest compatible version.
- **Stop at the script's `price_source = "n/a"`.** The script handles the market-native primary branch (**Stooq JSON primary for listed securities, yfinance per-ticker secondary**; **yfinance primary for FX**; Binance / CoinGecko first for crypto), tier 2 (configured keyed APIs), and selected tier-4 stubs. After every Stooq hit the script also probes Yahoo's v8 chart endpoint to confirm the ticker quote currency (`fallback_chain` line `currency_verify:yahoo_chart`). **The agent owns tier 3 (web search) and any tier 4 entry that requires symbol mapping or source-specific handling the script cannot do.** A `n/a` from `scripts/fetch_prices.py` is a **handoff signal** — the agent must walk §8.1 tier 3 then tier 4 manually before declaring the ticker terminal. Generating a report with mass `n/a` for non-cash tickers when web search has not been attempted is a **workflow violation** (see §8.3.1).

This prerequisite is the same regardless of who calls yfinance: the canonical `scripts/fetch_prices.py`, an ad-hoc script the agent wrote, or a one-off REPL probe. The pacing rules in §8.3 still apply once yfinance is importable — install is **separate** from rate-limit handling.

### 8.1 Source hierarchy

Use the highest-priority source that returns a credible value. **The priority is asset-specific, not globally yfinance-first.** Listed securities use **Stooq JSON first**, then `yfinance` per-ticker history as the secondary fallback. **FX** uses `yfinance` per-pair first (Stooq does not cover FX). **Crypto** uses **Binance public spot / CoinGecko first** and skips yfinance altogether. After the market-native primary source, continue to configured keyed APIs, then agent web search / public quote pages, then free no-token APIs. If a source is delayed, EOD-only, or stale relative to another credible source, use the fresher higher-quality value when available and record the fallback / freshness in the source audit.

1. **Latest-price subagent using the market-native primary source** — before any other price-source work, delegate all holdings to a dedicated latest-price subagent. For **listed securities (US / TW / TWO / JP / HK / LSE)** the primary call is the **no-token Stooq JSON endpoint** (`https://stooq.com/q/l/?s=<ticker>.<suffix>&f=sd2t2ohlcv&h&e=json`) and the secondary fallback is **`yfinance` per-ticker history**. For **FX** the primary call is `yfinance` `<PAIR>=X`. For **crypto** start with Binance public spot and CoinGecko. After every Stooq success the agent / script **must** verify the ticker quote currency via Yahoo's v8 chart meta (`https://query1.finance.yahoo.com/v8/finance/chart/<symbol>` → `chart.result[0].meta.currency`) — Stooq does not return currency, and the suffix is not authoritative (`.UK` covers GBP shares **and** USD UCITS ETFs; `.US` covers ADRs whose underlying currencies vary). Accept only values that pass the **Freshness gate** (§8.7). Record `price_source`, as-of timestamp, currency, exchange / market basis when available, and any ticker-level failure reason. For yfinance branches that did fire (secondary fallback or FX primary), if the call fails the subagent must diagnose the failure and attempt automatic correction up to three times before the main agent moves the affected ticker to the next tier (§8.4).
2. **Configured keyed APIs** — if the primary source for that asset class still fails, lacks coverage, or returns a value that fails the freshness gate after the allowed correction attempts, use any relevant key / token present in `SETTINGS.md` according to the per-asset order in §8.5. Missing keys are not errors.
3. **Agent web search / public quote pages** *(MANDATORY continuation when tiers 1–2 fail)* — when prior tiers fail (including any failure mode of `scripts/fetch_prices.py` such as rate-limit, missing key, or empty response), the agent **must** search the web directly and read public quote pages. Make sure you search for currency of the trading pair specifically first so we can convert it correctly. This is not optional and is not gated on the `fetch_prices.py` exit code; the script writes `agent_web_search:TODO` precisely as a handoff signal. Prefer official exchanges and widely used quote pages with visible price, timestamp, and prior-close / 24h reference. Record the page source and retrieval time. See §8.3.1 for the per-market source priority.
4. **Free no-token APIs** *(MANDATORY continuation when tier 3 fails)* — when web search / quote pages fail or are blocked, use free public endpoints that require no token. Make sure you search for currency of the trading pair specifically first so we can convert it correctly. These can be unofficial, delayed, rate-limited, or CORS-sensitive, so they are the last fallback. Record them explicitly as no-token fallback sources. See §8.3.1 for the recommended endpoint registry (Stooq JSON for US/JP/LSE, TWSE MIS for TW, Binance / Coinbase / CoinGecko for crypto).

> **Conflict resolution:** When `yfinance` and another credible latest-price value conflict, prefer the source with the freshest timestamp and clearest market coverage; document the rejected source and reason in **Sources & data gaps**.

> **Workflow gate (HARD):** Before generating the HTML, every non-cash ticker must have either (a) a valid `latest_price` with a recorded source, or (b) a `fallback_chain` containing explicit tier 3 **and** tier 4 entries (with `tier3:exhausted` / `tier4:exhausted` markers when nothing worked). A ticker carrying `agent_web_search:TODO` without follow-through is a workflow violation; do not generate the report until §8.3.1 has been walked.

### 8.2 Primary source policy by asset class

- For **listed equities and ETFs (US / TW / TWO / JP / HK / LSE)** the primary source is the **no-token Stooq JSON endpoint**, with `yfinance` per-ticker history as the **secondary** fallback. After every Stooq quote, the agent / script verifies the ticker's quote currency via Yahoo's v8 chart endpoint (`currency_verify:yahoo_chart`); never trust the Stooq suffix alone.
- For **FX**, the primary source is `yfinance` per-pair (`<PAIR>=X`); Stooq does not provide FX. Fallback follows §8.5: keyed Twelve Data → Frankfurter (ECB) → Open ExchangeRate-API.
- The latest-price subagent must return per ticker: price, prior close / 24h reference, move %, timestamp / as-of, currency (verified), exchange, and any failure reason.
- For **crypto**, do **not** use `yfinance` or Stooq. Start with Binance public spot where the pair exists, then CoinGecko. Use yfinance only if the spec is later amended explicitly; the default policy is to skip it.
- If the primary source fails or returns invalid data, the subagent advances to the next tier in §8.5. Auto-correction (§8.4) applies to yfinance branches only when yfinance actually fired (i.e. the secondary fallback for listed securities, or the primary for FX).
- Always retrieve the latest market data at generation time. Never rely on stale model memory.
- Each holding must be refreshed for: latest price snapshot, day / 24h and recent move, market cap, valuation multiples (PE, Forward PE, PS, EV/EBITDA where relevant), volume, next earnings date, and any imminent material event.
- For company and event data, source priority remains: company IR, SEC / exchange filings, official press releases, then StockAnalysis, Nasdaq, Yahoo Finance, Reuters, CNBC, MarketWatch.

### 8.3 yfinance rate limiting & request pacing (HARD REQUIREMENT)

`yfinance` proxies Yahoo Finance's unofficial endpoints, which throttle aggressively and return `YFRateLimitError` / HTTP 429 / empty payloads when hit too fast. yfinance is now invoked **per-ticker** (as the secondary fallback for listed securities and the primary path for FX), so pacing is even more critical — a tripped limiter typically blocks the IP for 15–60 minutes and forces the entire run onto fallback sources. The latest-price subagent **must** pace every yfinance request that fires.

| Rule | Detail |
|---|---|
| Per-ticker, no batch | The canonical script calls `yf.Ticker(symbol, session=session).history(period="5d", interval="1d", auto_adjust=False, timeout=12)` for each ticker that fell through Stooq. Do not reintroduce `yf.download(...)` batches; per-ticker is what `_yfinance_per_ticker_history` and `_auto_correct` use. (Historic batch advice has been retired with the Stooq-primary refactor.) |
| No internal threading | Stay sequential. Concurrent yfinance requests are the fastest way to trip the limiter |
| Min inter-call gap | **1.5–2.0s** between successive yfinance HTTP calls. For per-ticker iteration use `time.sleep(random.uniform(1.5, 2.5))`. **Never go below 1.0s** |
| Backoff on 429 / `YFRateLimitError` / empty `history()` | Exponential: 30s → 60s → 120s → 300s, **max 3 retries**. After the third failure, mark the ticker `yfinance_rate_limited` and move to the next tier — do not keep hammering |
| Reuse session | Reuse a single `requests.Session` across calls (`yf.Ticker(t, session=session)`) so cookies / crumbs are not re-negotiated each request. The Yahoo v8 chart currency-verification probe also reuses the same session |
| HTTP timeout | 10–15s per request. A hung connection still consumes a rate-limit slot |
| Audit fields | Record per-ticker `yfinance_request_started_at`, `yfinance_request_latency_ms`, `yfinance_retry_count` in the source audit when yfinance was invoked |

The pacing/backoff retries are part of the §8.4 three-attempt budget — a 429 retry counts as one correction attempt, not a free retry. If a run still trips the limiter, surface the incident in **Sources & data gaps** with offending request count and inter-request gap, and include a **建議更新 agent spec** note proposing a tighter pacing constant.

### 8.3.1 Rate-limit handling — tier-down, not stop (HARD REQUIREMENT)

A 429 / `YFRateLimitError` / empty `history()` from yfinance is a **tier-down signal**, not a workflow stop. The chain in §8.1 is **mandatory continuation** for every affected ticker. The script handles part of it; the agent must finish the rest. Note that under the current Stooq-primary policy, **most listed-equity rate-limit hits never appear** because yfinance only fires when Stooq has already missed; rate-limit triage is most relevant for FX (yfinance primary) and the rare listed-security ticker that Stooq cannot price.

#### Decision tree on yfinance rate-limit failure

```
yfinance per-ticker call returns 429 / YFRateLimitError / empty history
  └── apply §8.3 backoff (30 → 60 → 120 → 300s, max 3 retries)
       ├── any retry succeeds → ticker accepted, record retry_count
       └── all 3 retries fail → ticker marked yfinance_rate_limited
            ├── §8.4 auto-correction is SKIPPED (rate-limit is not a symbol problem)
            ├── tier 2: configured keyed APIs (§8.5) → if any key applies and works, accept
            ├── tier 3: AGENT web search / public quote pages (mandatory) → record source URL
            └── tier 4: no-token APIs (mandatory) → see §8.5 + endpoint registry below
                 └── only after every tier above has been attempted
                     may the ticker be marked price_source = "n/a"
```

#### Concrete rules

1. **Skip §8.4 auto-correction when `failure_reason` is rate-limit.** Auto-correction is for symbol/format problems (`BRK.B → BRK-B`, suffix repair, period swap). Retrying yfinance during the rate-limit window wastes the §8.3 backoff budget and prolongs the limiter state. The script **must** distinguish `failure_reason = "rate_limited"` from `"symbol_not_found" / "empty_history" / "exception"` so this skip can fire deterministically.
2. **Continuation is per-ticker, not per-batch.** A failed batch does not mean the whole report is degraded — most tickers can still be priced via tiers 2/3/4. Process each ticker independently after the batch fails.
3. **Tier 3 (web search) is the agent's job, not the script's.** `scripts/fetch_prices.py` records `fallback_chain = ["agent_web_search:TODO"]` precisely so the agent knows it must take over. Make sure you search for currency of the trading pair specifically first so we can convert it correctly. Recommended sources by market:

   | Market | Web-search source priority |
   |---|---|
   | US equities / ETFs | Yahoo Finance quote page → Google Finance → Nasdaq → MarketWatch / CNBC / TradingView / StockAnalysis |
   | Crypto | CoinGecko → CoinMarketCap → Binance → Coinbase → TradingView |
   | TW (TWSE / TPEx) | TWSE / TPEx official quote → Yahoo Finance Taiwan → TradingView |
   | JP | Yahoo Finance Japan / Yahoo Finance global → JPX / issuer pages → Google Finance |
   | LSE | Yahoo Finance UK → Google Finance → London Stock Exchange site |
   | FX | Google Finance → Yahoo Finance → official central-bank reference |

4. **Tier 4 (no-token APIs) — recommended endpoint registry.** Use these when web pages are slow / unreliable / blocked. The script implements Binance and CoinGecko for crypto plus Stooq / TWSE MIS for selected markets; the rest the agent invokes via its HTTP tooling:

   | Market | No-token endpoint | Sample URL |
   |---|---|---|
   | US equities | Stooq JSON | `https://stooq.com/q/l/?s=NVDA.US&f=sd2t2ohlcv&h&e=json` |
   | US equities | Yahoo public chart | `https://query1.finance.yahoo.com/v8/finance/chart/NVDA?range=5d&interval=1d` |
| Crypto | Binance spot ticker | `https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT` |
| Crypto | Coinbase Exchange ticker | `https://api.exchange.coinbase.com/products/BTC-USD/ticker` |
| Crypto | CoinGecko simple price | `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd` |
   | TW | TWSE MIS public quote | `https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_2330.tw` |
   | TW | TWSE OpenAPI daily | `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_AVG_ALL` |
   | JP / global | Stooq JSON (`.JP`, `.UK` codes) | `https://stooq.com/q/l/?s=7203.JP&f=sd2t2ohlcv&h&e=json` |
   | LSE | Stooq JSON (`.UK`) | `https://stooq.com/q/l/?s=VWRA.UK&f=sd2t2ohlcv&h&e=json` |
   | FX | ECB daily reference rate | `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` |

   > **Stooq currency rule (mandatory).** Stooq JSON responses do **not** include a currency field — the price comes back as a bare number. `scripts/fetch_prices.py` automatically calls Yahoo's v8 chart endpoint (`https://query1.finance.yahoo.com/v8/finance/chart/<symbol>`) after every Stooq hit and reads `chart.result[0].meta.currency` to resolve the canonical trading currency, with the result cached and recorded in `fallback_chain` as `currency_verify:yahoo_chart`. When the agent walks Stooq manually outside the script (e.g. tier 4 tooling), it **must** reproduce that lookup: query the v8 chart endpoint (or web-search the listing exchange) and confirm the trading currency before recording the quote (e.g. `2330.TW` → TWD on TWSE; `7203.JP` → JPY on TSE; `VWRA.UK` → USD on LSE despite the `.UK` suffix; ADRs on `.US` → USD). Cite the verification source in `fallback_chain` (e.g. `tier4:stooq + currency_verify:yahoo_chart` or `tier4:stooq + currency_websearch:lse_official`). Never assume the currency from the Stooq suffix alone — `.UK` covers both GBP-denominated UK shares and USD-denominated UCITS ETFs, and `.US` covers ADRs whose underlying currencies vary.
5. **Audit every step.** Each tier the agent walks must add a row to the ticker's `fallback_chain` (e.g. `tier3:yahoo_quote_page`, `tier4:stooq_csv`) and update `price_source`, `price_as_of`, `price_freshness`. The **Sources & data gaps** table renders this trail.
6. **Workflow gate before report rendering.** Before the agent calls `scripts/generate_report.py`, run a check: any ticker still at `price_source = "n/a"` with `fallback_chain` containing `agent_web_search:TODO` and **without** a tier 3 or tier 4 entry is a workflow violation. Fix it (or, if web/no-token sources genuinely all failed, replace the TODO with `tier3:exhausted` and `tier4:exhausted` so the audit shows real attempts).

#### When `n/a` is acceptable

After tiers 1–4 have **all** been attempted for a ticker, `price_source = "n/a"` is allowed. In that case the source-audit row must read along the lines of:

> `yfinance: rate_limited (3 backoff retries) · keyed: no key configured · web: yahoo/google/nasdaq all returned page-not-found · no-token: stooq returned empty CSV, yahoo chart returned 401 · price_freshness: stale_after_exhaustive_search`

Anything less specific signals the chain was not actually exhausted.

### 8.4 yfinance failure recovery (3-attempt budget)

If the `yfinance` subagent returns an exception, empty data, stale data, invalid currency / exchange metadata, a symbol-not-found result, or a value that fails the **Freshness gate** (§8.7), do not immediately fall back. First read the failure reason and attempt automatic correction.

> **Exception — rate-limit failures skip auto-correction.** When `failure_reason ∈ {"rate_limited", "YFRateLimitError", "http_429", "batch_empty_throttled"}`, do **not** invoke this auto-correction loop. Auto-correction is for symbol / format problems; retrying yfinance during the rate-limit window wastes the §8.3 backoff budget and prolongs the limiter state. Apply §8.3.1 tier-down instead — go straight to keyed APIs / web / no-token.

- **Maximum attempts:** three correction attempts per failed ticker or batch failure class (when the failure is a symbol / format / freshness issue, **not** a rate-limit). Attempt count starts after the first failed `yfinance` call. Do not loop indefinitely.
- **Targeted corrections.** Match the attempt to the observed failure reason. Examples:
  - Normalize Yahoo symbols (`BRK.B` → `BRK-B`, crypto → `BTC-USD`, Taiwan / Japan suffixes).
  - Retry as per-ticker calls after a failed batch (only when the batch failure was *not* rate-limit).
  - Switch between quote metadata and short interval history.
  - Request a shorter / longer period.
  - Repair timezone / calendar interpretation.
  - Brief retry after a transient timeout that is *not* a 429 (timeouts use a small fixed delay, not the §8.3 backoff schedule).
- **Re-gate after each attempt.** If the corrected value passes the Freshness gate, use it and record `price_source = yfinance`, `yfinance_auto_fix_applied = true`, attempt count, and the successful fix summary.
- **All 3 attempts fail.** Move that ticker to keyed APIs, then web search / quote pages, then no-token APIs. Record the original failure reason and all attempted fixes in **Sources & data gaps**.
- **Spec-update note.** If a new correction pattern succeeds during a run, do **not** silently treat it as permanent spec knowledge. In the final user reply, include a short **建議更新 agent spec** note with the failure pattern, the fix that worked, and concise wording that could be added to this spec.

### 8.5 Per-asset fallback order

| Asset / market | Latest-price fallback order |
|---|---|
| US equities / ETFs | **First (primary):** Stooq JSON (`<ticker>.us`). **Second (secondary fallback):** `yfinance` per-ticker history. **Keyed APIs:** Twelve Data → Finnhub → FMP → Tiingo → Alpha Vantage → Polygon. **Web search / pages:** Yahoo Finance → Google Finance → Nasdaq → MarketWatch / CNBC / TradingView / StockAnalysis → other credible quote pages. **No-token APIs:** Yahoo public chart endpoint → other credible no-token endpoints. **Currency verification:** Yahoo v8 chart meta after every Stooq hit |
| Crypto | **First:** Binance public spot ticker where the pair exists → CoinGecko Demo/public. **Keyed APIs:** CoinGecko Demo → Alpha Vantage / FMP if configured. **Web search / pages:** CoinGecko → CoinMarketCap → Binance → Coinbase → TradingView. **No-token APIs:** Binance public spot ticker → Coinbase Exchange ticker → CoinGecko public simple price |
| Taiwan listed / OTC equities | **First (primary):** Stooq JSON (`<code>.tw`). **Second:** `yfinance` per-ticker (`<code>.TW` / `<code>.TWO`). **Third:** TWSE MIS public quote (`tse_<code>.tw` for listed, `otc_<code>.tw` for OTC). **Keyed APIs:** Twelve Data / Finnhub / FMP when coverage exists. **Web search / pages:** TWSE / TPEx quote pages → Yahoo Finance Taiwan → TradingView → other credible quote pages. **No-token APIs:** TWSE OpenAPI daily / after-market data → TPEx official no-token data. **Currency:** TWD (TW listings) — verified via Yahoo v8 chart |
| Japan equities | **First (primary):** Stooq JSON (`<code>.jp`). **Second:** `yfinance` per-ticker (`<code>.T`). **Keyed APIs:** Twelve Data → Finnhub → J-Quants when token is present. **Web search / pages:** Yahoo Finance Japan / Yahoo Finance global → JPX / issuer pages where price is visible → Google Finance → TradingView. **No-token APIs:** other credible no-token endpoints. **Currency:** JPY — verified via Yahoo v8 chart |
| Hong Kong equities | **First (primary):** Stooq JSON (`<code>.hk`). **Second:** `yfinance` per-ticker (`<code>.HK`). **Web search / pages:** HKEx → Yahoo Finance HK → TradingView. **Currency:** HKD — verified via Yahoo v8 chart |
| London / LSE equities & UCITS ETFs | **First (primary):** Stooq JSON (`<code>.uk`). **Second:** `yfinance` per-ticker (`<code>.L`). **Web search / pages:** Yahoo Finance UK → Google Finance → London Stock Exchange site. **Currency:** **must** be verified via Yahoo v8 chart — `.UK` covers both GBP shares and USD UCITS ETFs (e.g. VWRA → USD) |
| FX / cash conversion | **First:** `yfinance` subagent using Yahoo FX symbols (`<PAIR>=X`). **Keyed APIs:** Twelve Data FX → Alpha Vantage currency exchange rate. **No-token APIs:** Frankfurter (ECB-backed) → Open ExchangeRate-API → official daily reference-rate feeds. **Web search / pages:** Google Finance → Yahoo Finance → official central-bank / ECB / Fed reference pages |

### 8.6 Optional fallback API keys

All market-data keys in `SETTINGS.md` are **optional fallback sources**. Never block a report because a key is missing. If a key is present, use that keyed API for tickers where the **Stooq → yfinance** primary pair (or yfinance-primary FX) is missing, stale, unsupported, or invalid, before web search; if the key is missing, quota-limited, or unusable for the ticker, skip that provider and continue to the next fallback. **Do not put API keys, tokens, request URLs containing keys, or authenticated response payloads in the generated HTML.**

| Setting key | Primary use | Notes |
|---|---|---|
| `TWELVE_DATA_API_KEY` | US equities / ETFs, global equities where covered, FX | Free tier is suitable for snapshots but rate-limited. Prefer `/price` or quote endpoints when available |
| `FINNHUB_API_KEY` | US equities / ETFs, some global equities | Free key required. Use quote endpoint for current / previous close fields |
| `COINGECKO_DEMO_API_KEY` | Crypto latest price and 24h move | Demo key is optional; public shared access may work but is less reliable |
| `ALPHA_VANTAGE_API_KEY` | US equities fallback, FX, crypto fallback | Free tier is low-quota; use after higher-priority sources |
| `FMP_API_KEY` | US equities fallback, valuation / fundamentals where free tier allows | Free plan can be delayed / EOD; mark freshness accordingly |
| `TIINGO_API_KEY` | US equities fallback | Free token is optional and rate-limited |
| `POLYGON_API_KEY` | US equities fallback | Free plan may be delayed / EOD; mark freshness accordingly |
| `JQUANTS_REFRESH_TOKEN` | Japan official delayed market data | Optional for Japanese equities; useful as official delayed data, not necessarily the latest trade. If an implementation uses email / password to obtain the token, those fields are also optional and must never be written into outputs |

### 8.7 Freshness gate

Before accepting any latest price, determine the ticker's market calendar, exchange timezone, current local market date, and whether the regular session has already opened. Apply this gate before the source is considered valid:

| Market state at generation time | Acceptable price | Rejection rule |
|---|---|---|
| Regular session is open today | Same trading date, current / intraday latest price from a credible source. Timestamp or page context must indicate it is not just the prior close | Reject prior-session close, EOD-only, or clearly delayed values and continue to the next source |
| Regular session already closed today | Same trading date latest / official close / closing auction value. If only intraday timestamp is available, it must be from today's session | Reject previous trading day's close unless every source has been exhausted |
| Today's regular session has not opened yet | Previous opened trading day's official / credible close at minimum | Reject prices older than the previous opened trading day |
| Weekend / holiday / exchange closed all day | Most recent opened trading day's official / credible close | Reject older closes unless every source has been exhausted; if even that cannot be verified, render `n/a` |
| 24/7 assets such as major crypto | Fresh spot price from a credible source, with retrieval time or source timestamp | Reject stale snapshots when another source can provide a fresher spot price |

**Strict rule for opened markets:** Once a market's regular session has opened for the current exchange trading date, do **not** accept a prior-session close or stale delayed value until the **Stooq primary** result, the **`yfinance` per-ticker secondary** result, up to three yfinance auto-correction attempts, and every configured API, web-search/page source, and no-token fallback has been exhausted. If the market has not opened yet, the minimum acceptable price is the previous opened trading day's official / credible close.

**Degraded fallback:** If the market has opened and all sources are exhausted without a same-date latest price, use the freshest credible value only as an explicit degraded fallback. Mark `price_freshness` as `stale_after_exhaustive_search`, list every attempted source category in **Sources & data gaps**, and make the stale-price condition visible in the report's data-gap / alert text. **Do not silently treat that fallback as current.** If even the previous opened trading day's close cannot be sourced, render the cell as `n/a`.

If a credible source cannot be found, render the field as `n/a` (per §9.6). If a number is your own derivation, label it `estimate`. **Never silently guess.**

### 8.8 Stored fields per ticker

Persist these fields for every ticker at generation time. The HTML embeds only the static fields below; it never embeds provider credentials, provider request URLs with keys, or retry / polling code.

- `latest_price`
- `prior_close` or 24h reference (when available)
- `move_pct`
- `price_source`
- `price_as_of`
- `price_freshness`
- `market_state_basis`
- `currency` (when available)
- `exchange` (when available)
- If `yfinance` auto-correction was attempted: failure reason, attempts, applied fix when successful, final outcome
- If pacing retries fired: `yfinance_request_started_at`, `yfinance_request_latency_ms`, `yfinance_retry_count`

Persist automatic FX conversion data under `prices.json["_fx"]`: `base`, `required_currencies`, `rates` keyed `<BASE>/<CCY>`, and `details` containing the same source / freshness / fallback audit fields for each FX pair. Do not source FX conversion from `SETTINGS.md` or `report_context.json`.

---

## 9. Computations & missing-value glyphs
