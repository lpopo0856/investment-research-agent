# Investment Research Agent

**README languages** · [English](README.md) · [繁體中文](docs/l10n/README.zh-Hant.md) · [简体中文](docs/l10n/README.zh-Hans.md) · [日本語](docs/l10n/README.ja.md) · [Tiếng Việt](docs/l10n/README.vi.md) · [한국어](docs/l10n/README.ko.md)

The English README is the canonical version. Other languages are convenience translations.

This repo is a local workspace for an AI investment research agent. In practice, it does three things:

1. Answers research questions using your settings and holdings.
2. Generates a daily HTML portfolio report.
3. Updates `HOLDINGS.md` from natural-language trade instructions.

The repo is optimized for agent-driven use in tools such as OpenAI Codex, Claude Code, Gemini CLI, or similar environments that can read files and run commands.

**Model tier:** For reliable analysis and adherence to this repo’s contracts (`AGENTS.md`, report and holdings guidelines), use **Claude Sonnet 4.6** with **High** reasoning effort—or any newer model tier at least as capable. Lighter models may skip checklist steps, misread holdings, or weaken research depth.

## What matters

- `AGENTS.md`: how the research agent should think and write.
- `SETTINGS.md`: your language, risk style, and base currency. Local only.
- `HOLDINGS.md`: your positions. Local only.
- `docs/portfolio_report_agent_guidelines.md`: report contract. The agent must also read every linked numbered part under `docs/portfolio_report_agent_guidelines/`.
- `docs/holdings_update_agent_guidelines.md`: holdings-update contract.
- `scripts/fetch_prices.py`: canonical latest-price and FX fetcher.
- `scripts/generate_report.py`: canonical HTML report renderer.
- `reports/`: generated output. Local only.

## First-time setup

```sh
cp SETTINGS.example.md SETTINGS.md
cp HOLDINGS.example.md HOLDINGS.md
```

Then:

- Fill in `SETTINGS.md`.
- Fill in `HOLDINGS.md`.
- Keep the four buckets in `HOLDINGS.md`: `Long Term`, `Mid Term`, `Short Term`, `Cash Holdings`.
- Use one lot per line: `<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]`.
- Use `?` when cost basis or acquisition date is unknown.

Common market tags: `[US]`, `[TW]`, `[TWO]`, `[JP]`, `[HK]`, `[LSE]`, `[crypto]`, `[FX]`, `[cash]`.

`SETTINGS.md`, `HOLDINGS.md`, `HOLDINGS.md.bak`, generated reports, and common run artifacts are git-ignored.

### Using `SETTINGS.md` and `HOLDINGS.md`

- Update `SETTINGS.md` whenever your preferred language, risk style, base currency, or report defaults change.
- Treat `HOLDINGS.md` as the single source of truth for your live positions before asking for research or reports.
- After every completed trade, ask the agent to update `HOLDINGS.md` immediately so analysis stays accurate.
- Before generating a report, quickly review both files to avoid stale assumptions.

## Normal usage

Most users only need to ask the agent for one of these three workflows.

### 1. Research

Examples:

- "Analyze NVDA against my current portfolio."
- "What is my AI exposure now?"
- "Should I trim short-term positions before earnings?"

The agent reads `SETTINGS.md` and `HOLDINGS.md`, then follows `AGENTS.md`.

### 2. Portfolio report

Examples:

- "Produce today's portfolio health check."
- "Run my pre-market report."

The deliverable is a single self-contained HTML file under `reports/`.

For `auto mode`, `routine`, or any other unattended environment, it is recommended that the agent obtain explicit consent before sending holdings tickers to external market-data sources for report generation. A clear confirmation example is: `I agree to let you send my holdings tickers to external market data sources to retrieve prices and generate today's report.`

The agent should use the canonical scripts, not rewrite the workflow:

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

If the requested report language is not one of the built-in UI dictionaries (`english`, `traditional chinese`, `simplified chinese`), the executing agent should translate `scripts/i18n/report_ui.en.json` into a temporary overlay and pass it with `--ui-dict`.

### 3. Holdings update

Examples:

- "I bought 30 NVDA at $185 yesterday."
- "Sold 10 TSLA at $400 today."
- "Fix the GOOG lot from last September: 70 shares, not 75."

Hard rule: the agent must not write `HOLDINGS.md` until it has shown the parsed plan and unified diff, and received an explicit `yes` in the same turn. Every write must create `HOLDINGS.md.bak` first.

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
- `docs/holdings_update_agent_guidelines.md`

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
- `HOLDINGS.md`
- `HOLDINGS.md.bak`
- generated reports
- typical runtime files such as `prices.json` and `report_context.json`

## Third-party data

This project does not own or guarantee any market-data or FX source. The price workflow may use public endpoints (Stooq JSON, Yahoo's v8 chart endpoint, Binance, CoinGecko, Frankfurter / ECB, Open ExchangeRate-API, TWSE MIS), optional API keys (Twelve Data, Finnhub, Alpha Vantage, FMP, Tiingo, Polygon, J-Quants, CoinGecko Demo), and wrappers such as `yfinance`. You are responsible for provider terms, rate limits, attribution, and paid-access requirements.

## Disclaimer

This repo is for personal research only. It is not investment advice. Verify important facts independently before trading.
