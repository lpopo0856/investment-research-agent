# Investment Research Agent

**README languages** · [English](README.md) · [繁體中文](docs/l10n/README.zh-Hant.md) · [简体中文](docs/l10n/README.zh-Hans.md) · [日本語](docs/l10n/README.ja.md) · [Tiếng Việt](docs/l10n/README.vi.md) · [한국어](docs/l10n/README.ko.md)

The English README is the canonical version. Other languages are reader-friendly translations.

A local workspace for an AI investment research assistant. Open this repo in **Claude Code, OpenAI Codex, Gemini CLI, or any agent that can read files and run commands** — then talk to it in plain language.

**Model tier:** Use **Claude Sonnet 4.6** with **High** reasoning effort, or any newer model at least as capable. Lighter models may skip steps or shallow out the analysis.

## Report Demo

**[Report Demo](https://lpopo0856.github.io/investment-research-agent/)**

## Just ask the agent

You don't need to learn any commands, schemas, or files. Pick whichever line below matches what you want and paste it.

**New here?**

> "Help me get started." *(or attach a brokerage statement in any format — PDF, CSV, JSON, XLSX, screenshot, pasted text — and say "onboard me")*

**Want to see what's possible?**

> "What can I do here?"

**Tune how the agent acts as you (risk appetite, sizing, off-limits, language, base currency):**

> "Walk me through my settings."
> "Review my SETTINGS." / "Change my base currency to TWD."

**Record a trade or cash flow:**

> "I bought 30 NVDA at $185 yesterday."
> "Sold 10 TSLA at $400 today."
> "Q1 GOOG dividend, $80."
> "Deposited $5,000."
> "Here's my Schwab CSV — please import it." *(other broker exports work too; see `docs/`)*

**Ask a research question:**

> "Analyze NVDA against my current portfolio."
> "What's my AI exposure now?"
> "Should I trim short-term positions before earnings?"

**Generate today's portfolio report:**

> "Produce today's portfolio health check."
> "Run my pre-market report."

The agent confirms before any write to your data, and follows the contract docs under `docs/` end-to-end. You describe what you want in everyday language; it handles the mechanics.

## Privacy

Your settings, your transactions database (SQLite), and every generated report stay local — none of them are tracked in git. Only the agent specs, example templates, and the Python scripts are in version control.

## Third-party data

The price workflow may use public market-data and FX endpoints (Stooq, Yahoo, Binance, CoinGecko, Frankfurter / ECB, Open ExchangeRate-API, TWSE / TPEx) and optional API keys you supply. This project does not operate or endorse any provider — you are responsible for terms, rate limits, and any paid access.

## Disclaimer

For personal research and record-keeping only. Not investment or legal advice. Verify important facts independently before trading; you own the decisions.
