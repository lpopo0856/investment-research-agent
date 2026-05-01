# Settings — demo profile

This is the **synthetic SETTINGS** for the demo ledger. It exists so demo
report runs do **not** read the user's real `SETTINGS.md` at the repo root,
which would leak personal strategy, language, and (worst case) API keys
into the synthetic output.

Pass it explicitly to every pipeline step that reads SETTINGS:

```bash
python3 scripts/fetch_prices.py      --db demo/transactions.db --settings demo/SETTINGS.md ...
python3 scripts/fetch_history.py     --db demo/transactions.db --settings demo/SETTINGS.md ...
python3 scripts/transactions.py snapshot --db demo/transactions.db --settings demo/SETTINGS.md ...
python3 scripts/generate_report.py   --settings demo/SETTINGS.md ...
```

`transactions.py snapshot` bakes `locale` / `display_name` / `raw_language`
and `base_currency` into `report_snapshot.json`; the renderer reads those
from the snapshot, not from its own `--settings` flag, so missing this
flag here silently re-uses the root profile and the report renders in
the wrong language.

The demo runbook (`demo/README.md`) shows the full canonical command set.

## Language

- traditional chinese

## Investment Style And Strategy

I run a dual-currency demo book that mixes US megacap quality, Taiwan
foundry exposure, and a small crypto sleeve as a deliberate stress layout
for the report pipeline. Holding-period bias is multi-year on the core
US/TW names with explicit short-term sleeves carved out for tactical
trades; sizing is rail-aware (single-name, theme, high-vol, cash-floor)
and I prefer to trim the highest-cost lots first when reducing risk.
Tolerance for hype is low: every upside claim must be backed by base /
bull / bear bracketing, and I want data gaps surfaced explicitly rather
than papered over. This profile is **synthetic** — it reflects the demo
ledger's shape, not any real operator's mandate.

The agent should write its **Strategy readout** in first person from this
paragraph. Empty trading_psychology / theme_sector_audit / research
coverage are still rejected by `scripts/validate_report_context.py` —
the demo run must do the same live web research as a production run.

## Reporting cadence (optional)

- Default report frequency: on-demand (demo runs only).
- Pre-market focus: US session.
- Time zone: Asia / Taipei.

## Position sizing rails (optional, used by the portfolio report agent)

- Single-name weight cap: 10% (warn above this).
- Theme concentration cap: 30% (warn above this).
- High-volatility bucket cap: 30% (warn above this).
- Cash floor: 10% (warn below this).
- Single-day move alert: ±8%.

## Base currency (optional, default USD)

- Base currency: USD

The demo ledger funds in both USD and TWD with FX_CONVERT bridges; USD
is chosen as the report base so the masthead and aggregates match the
golden-path report we ship as a reference.

## Market Data API Keys (optional fallback)

Demo runs intentionally do **not** carry API keys — the fallback chain
(yfinance → Stooq → Binance → CoinGecko → ECB / Frankfurter) is enough
for the synthetic universe. Leave these blank; `parse_settings_keys`
treats empty values as "not configured" and the chain skips keyed APIs
silently.

- TWELVE_DATA_API_KEY:
- FINNHUB_API_KEY:
- COINGECKO_DEMO_API_KEY:
- ALPHA_VANTAGE_API_KEY:
- FMP_API_KEY:
- TIINGO_API_KEY:
- POLYGON_API_KEY:
- JQUANTS_REFRESH_TOKEN:
