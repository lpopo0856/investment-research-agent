# Settings (Example)

This is an **example** settings file. Copy it to `SETTINGS.md` and edit the fields below.

`SETTINGS.md` is git-ignored so your personal preferences never enter version control.

The agent reads this file on every run to set tone, language, and risk handling.

## Language

- english

(Other supported values: `traditional chinese`, `simplified chinese`, `japanese`, `bilingual: english + traditional chinese`. Pick one.)

## Investment Style

Describe how you want the agent to talk to you about risk and conviction. Examples — keep, edit, or replace:

- I can absorb large short-term losses and volatility.
- As long as the long-run expected value is positive, I am fine with deep drawdowns along the way.
- My temperament is steady; I do not need overly conservative risk reminders.
- I am willing to size up on high-probability or asymmetric reward setups.
- I do not want exaggerated optimism — every claim must be supported by theory and data.

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

## Market Data API Keys (optional fallback)

Latest prices are fetched first by the yfinance latest-price subagent. These keys are optional fallback sources when yfinance is missing, stale, unsupported, or invalid for a ticker.

- TWELVE_DATA_API_KEY:
- FINNHUB_API_KEY:
- COINGECKO_DEMO_API_KEY:
- ALPHA_VANTAGE_API_KEY:
- FMP_API_KEY:
- TIINGO_API_KEY:
- POLYGON_API_KEY:
- JQUANTS_REFRESH_TOKEN:
