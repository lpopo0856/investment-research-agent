# Settings (Example)

This is an **example** settings file. Copy it to `SETTINGS.md` and edit the fields below.

`SETTINGS.md` is git-ignored so your personal preferences never enter version control.

The agent reads this file on every run to set tone, language, and risk handling.

## Language

- english

(Stable built-in dictionaries: `english`, `traditional chinese`, `simplified chinese`. Other single-language values such as `japanese` are allowed, but the **executing agent** should translate `scripts/i18n/report_ui.en.json` and pass the translated overlay into `scripts/generate_report.py` via `--ui-dict` or `context["ui_dictionary"]`. Do not use bilingual values.)

## Investment Style

Describe how you want the agent to talk to you about risk and conviction. Examples — keep, edit, or replace:

- I can absorb large short-term losses and volatility.
- As long as the long-run expected value is positive, I am fine with deep drawdowns along the way.
- My temperament is steady; I do not need overly conservative risk reminders.
- I am willing to size up on high-probability or asymmetric reward setups.
- I do not want exaggerated optimism — every claim must be supported by theory and data.

## Style levers (optional, agent-inferred if omitted)

The agent reads the `Investment Style` bullets above and infers six behavioral levers from them. These levers actively reshape recommendations — they change *what* the agent recommends (kill-price width, position size, lot-trim ordering, contrarian latitude), not just phrasing. Pin a value here to override inference. Allowed values are shown in parentheses.

- Drawdown tolerance: medium        (low / medium / high)
- Conviction sizing: flat           (flat / kelly-lite / aggressive)
- Holding-period bias: investor     (trader / swing / investor / lifer)
- Confirmation threshold: medium    (low / medium / high)
- Contrarian appetite: selective    (none / selective / strong)
- Hype tolerance: low               (zero / low / medium)

Lever cheatsheet:

- **Drawdown tolerance** sets how wide the agent places kill prices and whether it scales into deep drawdowns.
- **Conviction sizing** sets the typical recommended `% of book` per name (flat ≈ equal weight; kelly-lite ≈ 2–8% by conviction; aggressive ≈ up to 8–15% if rails permit).
- **Holding-period bias** skews horizon and the lot-trim ordering when the agent recommends selling.
- **Confirmation threshold** decides whether the agent waits for breakout/earnings confirmation or is permitted to front-run setups.
- **Contrarian appetite** gates whether non-consensus calls may appear (`none` blocks them; `strong` welcomes top-of-page contrarian theses).
- **Hype tolerance** caps optimistic language and forecast multipliers (`zero` requires every upside number to be base/bull/bear bracketed).

The agent prints the resolved levers as a `Style readout` block at the top of every analysis — correct any wrong inference here. If both this section and `Investment Style` are omitted, neutral defaults apply (`medium / flat / investor / medium / selective / low`).

## Reporting cadence (optional)

- Default report frequency: ad-hoc (run on demand).
- Pre-market focus: US session.
- Time zone: Asia / Taipei.

## Position sizing rails (optional, used by the portfolio report agent)

- Single-name weight cap: 10% (warn above this).
- Theme concentration cap: 30% (warn above this).
- High-volatility bucket cap: 30% (warn above this).
- Cash floor: 10% (warn below this).
- Single-day move alert: ±8%.

## Base currency (optional, default USD)

The base currency every aggregate in the report is denominated in. Use a single ISO 4217 code (e.g. `USD`, `TWD`, `JPY`, `HKD`, `GBP`, `EUR`). When omitted, the agent defaults to `USD` (the historical hard-coded basis).

- Base currency: USD

Choose this once and keep it stable — switching base mid-stream will make today's report incomparable to yesterday's. Pick whatever currency matches how you actually evaluate your portfolio (most TW-based users want `TWD`; most globally-diversified investors want `USD`).

## Market Data API Keys (optional fallback)

Latest prices are fetched first by a market-aware latest-price subagent. Listed securities and FX use `yfinance` first; crypto should prefer Binance public spot and CoinGecko before any Yahoo-style fallback. These keys are optional fallback sources when the primary source is missing, stale, unsupported, or invalid for a ticker.

This repo **does not operate or endorse** any third-party API. If you add keys, **you** must comply with each provider’s **terms of service**, **rate limits**, and billing rules. Do not assume unlimited quota.

- TWELVE_DATA_API_KEY:
- FINNHUB_API_KEY:
- COINGECKO_DEMO_API_KEY:
- ALPHA_VANTAGE_API_KEY:
- FMP_API_KEY:
- TIINGO_API_KEY:
- POLYGON_API_KEY:
- JQUANTS_REFRESH_TOKEN:
