# Settings (Example)

This is an **example** settings file. Copy it to `SETTINGS.md` and edit the fields below.

`SETTINGS.md` is git-ignored so your personal preferences never enter version control.

The agent reads this file on every run to set tone, language, and risk handling.

## Language

- english

(Stable built-in dictionaries: `english`, `traditional chinese`, `simplified chinese`. Other single-language values such as `japanese` are allowed, but the **executing agent** should translate `scripts/i18n/report_ui.en.json` and pass the translated overlay into `scripts/generate_report.py` via `--ui-dict` or `context["ui_dictionary"]`. Do not use bilingual values.)

## Investment Style And Strategy

Describe **the kind of investor you are and the strategy you run**. The agent reads this **whole section** every run, internalises it, and from that point on **acts as you** — your voice, your risk appetite, your horizon, your entry and exit discipline, your no-go zones. The richer this section, the more the output reads like you wrote it yourself; vague descriptions produce generic output.

Useful things to cover (keep, edit, or replace):

- **Temperament & drawdown tolerance** — how much volatility you can absorb and what kind of risk-reminder language is useful vs. patronising.
- **Conviction & sizing** — flat-weight, kelly-lite, or aggressive concentration; whether you size up on asymmetric setups; how big a single name is allowed to get before you trim.
- **Holding-period bias** — trader, swing, multi-year investor, or generational holder; what makes you exit early vs. ride through.
- **Entry discipline** — wait for trigger confirmation (breakout / earnings beat / structural break) or front-run setups; minimum evidence threshold before adding.
- **Contrarian appetite** — welcome non-consensus calls, or only buy when the tape agrees.
- **Hype tolerance** — how much optimistic framing you accept; whether every upside number must be base / bull / bear bracketed.
- **Off-limits zones** — themes, structures, or position types you will not own (e.g. unprofitable biotech, single-stock options, illiquid OTC).
- **Decision style** — what you want from the agent (bullets first; flag data gaps explicitly; never pad action lists; etc.).

Examples — keep, edit, or replace:

- I can absorb large short-term losses and volatility.
- As long as the long-run expected value is positive, I am fine with deep drawdowns along the way.
- My temperament is steady; I do not need overly conservative risk reminders.
- I am willing to size up on high-probability or asymmetric reward setups.
- I do not want exaggerated optimism — every claim must be supported by theory and data.
- I run multi-year holds for high-conviction names and do not chase quarterly noise.
- I do not buy unprofitable biotech or single-stock options.

The agent opens every analysis with a short **Strategy readout** block — written in **first person, as you** — restating the working strategy it just internalised. If this section is empty, the agent falls back to a neutral PM persona and says so explicitly; recommendations will be generic until you fill it in.

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

## Benchmark ETFs (optional)

The report's profit-panel interval tables compare portfolio / market-bucket returns
against broad-market ETF benchmarks. Defaults are built in; edit these lines only
if you want a different comparison set.

- Global benchmark: VT
- US market benchmark: VTI
- Taiwan listed benchmark: 0050.TW
- Taiwan OTC benchmark: 00928.TW
- Japan market benchmark: EWJ
- Hong Kong market benchmark: EWH
- London market benchmark: EWU

Use `none` to disable a benchmark for a bucket. You may also provide a market tag
when the ticker itself is ambiguous, e.g. `0050.TW` or `VWRL [LSE]`.
