# Investment Research Agent

**README languages** · [English](README.md) · [繁體中文](docs/l10n/README.zh-Hant.md) · [简体中文](docs/l10n/README.zh-Hans.md) · [日本語](docs/l10n/README.ja.md) · [Tiếng Việt](docs/l10n/README.vi.md) · [한국어](docs/l10n/README.ko.md)

The English README is the canonical version. Other languages are convenience translations.

This repo is a local workspace for an AI investment research agent. In practice, it does three things:

1. Answers research questions using your settings and your transaction history.
2. Generates a daily HTML portfolio report.
3. Records new transactions (BUY / SELL / DEPOSIT / WITHDRAW / DIVIDEND / FEE / FX_CONVERT) from natural-language messages, CSV, or JSON files into a local SQLite database.

The repo is optimized for agent-driven use in tools such as OpenAI Codex, Claude Code, Gemini CLI, or similar environments that can read files and run commands.

**Model tier:** For reliable analysis and adherence to this repo's contracts (`AGENTS.md`, report and transactions guidelines), use **Claude Sonnet 4.6** with **High** reasoning effort — or any newer model tier at least as capable. Lighter models may skip checklist steps, misread transactions, or weaken research depth.

## What matters

- `AGENTS.md`: how the research agent should think and write.
- `SETTINGS.md`: your language, full `Investment Style And Strategy`, base currency, and sizing rails. Local only.
- `transactions.db`: local SQLite store of every transaction (buys, sells, deposits, withdrawals, dividends, fees, FX conversions) with rationale + tags. Holds two derived tables (`open_lots`, `cash_balances`) that are auto-rebuilt after every insert and act as the projected open-position view. **Drives realized P&L, unrealized P&L, and the profit panel.** Local only. See `docs/transactions_agent_guidelines.md`.
- `docs/portfolio_report_agent_guidelines.md`: report contract, including full news/event coverage, Strategy readout, and reviewer pass. The agent must also read every linked numbered part under `docs/portfolio_report_agent_guidelines/`.
- `docs/transactions_agent_guidelines.md`: the single transactions-ledger contract — DB schema, natural-language parse → plan → confirm → write workflow, ingestion paths for CSV / JSON / message, lot matching, profit panel, migration.
- `scripts/fetch_prices.py`: canonical latest-price and FX fetcher. Reads positions from `transactions.db`.
- `scripts/fetch_history.py`: companion historical close + FX history fetcher used by the profit panel (writes `_history` / `_fx_history` into prices.json). Reads positions from `transactions.db`.
- `scripts/transactions.py`: SQLite store + ingestion (CSV / JSON / message), replay engine, balance rebuild, realized + unrealized P&L, profit panel for 1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME.
- `scripts/generate_report.py`: canonical HTML report renderer; consumes `strategy_readout`, `reviewer_pass`, `profit_panel`, and `realized_unrealized` from `report_context.json`. Reads positions from `transactions.db`.
- `reports/`: generated output. Local only.

## First-time setup

```sh
cp SETTINGS.example.md SETTINGS.md
python scripts/transactions.py db init        # create transactions.db
```

Then either:

- **Bootstrap from a pre-existing `HOLDINGS.md`** (iteration-2 users):

  ```sh
  python scripts/transactions.py migrate --holdings HOLDINGS.md
  python scripts/transactions.py verify
  rm HOLDINGS.md HOLDINGS.md.bak HOLDINGS.example.md
  ```

  `migrate` synthesizes one BUY per existing lot and one DEPOSIT per cash currency, sized so the rebuild round-trips your seeded balances. After the verify passes, the markdown files are no longer needed.

- **Or import a broker statement** (CSV or JSON):

  ```sh
  python scripts/transactions.py db import-csv --input statements/2026-04-schwab.csv
  python scripts/transactions.py db import-json --input transactions.json
  ```

- **Or feed individual transactions** through the agent in plain English ("bought 30 NVDA at $185 yesterday"). The agent parses, shows you the canonical JSON, and on `yes` runs `db add`. See `docs/transactions_agent_guidelines.md` §3.

After every write, run `python scripts/transactions.py verify` to confirm the materialized `open_lots` + `cash_balances` tables match a fresh log replay.

`SETTINGS.md`, `transactions.db`, generated reports, and runtime files (`prices.json`, `report_context.json`, `temp/`) are git-ignored.

### Using `SETTINGS.md` and `transactions.db`

- Update `SETTINGS.md` whenever your preferred language, full investment strategy, base currency, sizing rails, or report defaults change.
- Write the whole `Investment Style And Strategy` section as the investor you want the agent to act as: temperament, drawdown tolerance, sizing, holding period, entry discipline, contrarian appetite, hype tolerance, off-limits zones, and decision style.
- Treat `transactions.db` as the single source of truth for your live positions and cash. Every new flow lands here through the agent or a CSV / JSON import; the derived `open_lots` + `cash_balances` views update automatically.
- After every completed trade, ask the agent to record the transaction immediately so analysis stays accurate.
- Before generating a report, quickly review `SETTINGS.md` and run `transactions.py db stats` to spot anything stale.

## Normal usage

Most users only need to ask the agent for one of these three workflows.

### 1. Research

Examples:

- "Analyze NVDA against my current portfolio."
- "What is my AI exposure now?"
- "Should I trim short-term positions before earnings?"

The agent reads the whole `Investment Style And Strategy` section in `SETTINGS.md`, loads positions from `transactions.db` (`open_lots` + `cash_balances`), then follows `AGENTS.md` in first person as your stated strategy.

### 2. Portfolio report

Examples:

- "Produce today's portfolio health check."
- "Run my pre-market report."

The deliverable is a single self-contained HTML file under `reports/`.

For `auto mode`, `routine`, or any other unattended environment, it is recommended that the agent obtain explicit consent before sending holdings tickers to external market-data sources for report generation. A clear confirmation example is: `I agree to let you send my holdings tickers to external market data sources to retrieve prices and generate today's report.`

A complete report run is phased: Gather data first, Think only after prices/metrics/news/events are collected, Review as a senior PM before rendering, then Render. The Gather phase includes live news and 30-day forward-event searches for every non-cash holding, not only top-weight positions. The Review phase annotates the user's analysis with reviewer notes where useful; it does not replace the user's content.

The agent should use the canonical scripts, not rewrite the workflow. All three reads from `transactions.db` automatically.

```sh
python scripts/fetch_prices.py --settings SETTINGS.md --output prices.json
# If any row still has agent_web_search:TODO_required, fetch_prices exits non-zero.
# Complete tier 3 / tier 4 quote fallbacks before rendering.

# Required for the profit panel: fetch daily closes + FX history
python scripts/fetch_history.py \
    --settings SETTINGS.md \
    --merge-into prices.json --output prices_history.json
# Uses market_data_cache.db by default; pass --no-cache for a one-off network-only run.

# Lifetime realized + unrealized snapshot
python scripts/transactions.py pnl \
    --prices prices.json --settings SETTINGS.md \
    > realized_unrealized.json

# Period profit panel (1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME)
python scripts/transactions.py profit-panel \
    --prices prices.json \
    --settings SETTINGS.md --output profit_panel.json

# Merge profit_panel.json + realized_unrealized.json into report_context.json
# under keys "profit_panel" and "realized_unrealized" before rendering.

python scripts/generate_report.py \
    --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

If the requested report language is not one of the built-in UI dictionaries (`english`, `traditional chinese`, `simplified chinese`), the executing agent should translate `scripts/i18n/report_ui.en.json` into a temporary overlay and pass it with `--ui-dict`.

`report_context.json` may include `strategy_readout` for the first-person Strategy readout and `reviewer_pass` for reviewer notes/summaries. The legacy `style_readout` key still renders, but new context should use `strategy_readout`.

### 3. Transaction recording

Examples:

- "I bought 30 NVDA at $185 yesterday."
- "Sold 10 TSLA at $400 today."
- "Q1 GOOG dividend, $80."
- "Deposited $5,000 to fund the next round of buys."
- "Here's my Schwab CSV — please import it."

Hard rule: the agent must not INSERT into `transactions.db` until it has shown the parsed plan, the canonical JSON blob(s), and received an explicit `yes` in the same turn. Every write is preceded by a backup to `transactions.db.bak`, followed by an automatic balance rebuild, followed by `verify`. See `docs/transactions_agent_guidelines.md` §3.

## Report output

Generated report filename:

```text
reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html
```

The HTML is standalone: no external CSS, JS, fonts, or chart libraries.

`reports/_sample_redesign.html` is the visual reference. Do not delete it.

## Editing behavior

Change these files when you want to change agent behavior:

- `AGENTS.md`
- `docs/portfolio_report_agent_guidelines.md`
- every linked part under `docs/portfolio_report_agent_guidelines/`
- `docs/transactions_agent_guidelines.md`

Do not put personal data into spec files.

## Privacy

Tracked in git:

- agent specs
- example templates
- Python scripts
- README files
- sample visual reference

Not tracked in git:

- `SETTINGS.md`
- `transactions.db`
- `transactions.db.bak`
- `market_data_cache.db`
- generated reports
- typical runtime files such as `prices.json`, `prices_history.json`, `report_context.json`, and `temp/`

## Third-party data

This project does not own or guarantee any market-data or FX source. The price workflow may use public endpoints (Stooq JSON, Yahoo's v8 chart endpoint, Binance, CoinGecko, Frankfurter / ECB, Open ExchangeRate-API, TWSE / TPEx MIS), optional API keys (Twelve Data, Finnhub, Alpha Vantage, FMP, Tiingo, Polygon, J-Quants, CoinGecko Demo), and wrappers such as `yfinance`. For Taiwan names, the no-token MIS fallback probes both listed (`tse_`) and OTC (`otc_`) channels to catch `[TW]` / `[TWO]` misclassification. You are responsible for provider terms, rate limits, attribution, and paid-access requirements.

## Disclaimer

This repo is for personal research only. It is not investment advice. Verify important facts independently before trading.
