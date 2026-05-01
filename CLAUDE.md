# Guide

**README languages** · [English](README.md) · [繁體中文](docs/l10n/README.zh-Hant.md) · [简体中文](docs/l10n/README.zh-Hans.md) · [日本語](docs/l10n/README.ja.md) · [Tiếng Việt](docs/l10n/README.vi.md) · [한국어](docs/l10n/README.ko.md)

**CRITICAL** **MUST READ** READ AGENTS.md, README.md, /docs/* under root directory

## New users

If `SETTINGS.md` or `transactions.db` is missing, or the user asks to get started / onboard / import a statement in any format (PDF, CSV, JSON, XLSX, screenshot, pasted text), follow `docs/onboarding_agent_guidelines.md`. It is the brand-agnostic on-ramp; once the DB has rows, route to `docs/transactions_agent_guidelines.md`.

## Help — capability menu

If the user asks "help" / "what can I do here" / "now what" / similar overview requests, follow `docs/help_agent_guidelines.md`. It renders a state-aware four-item menu and routes to the right contract doc.

## Settings interview

If the user asks to set up / edit / review `SETTINGS.md` ("walk me through my settings", "set up my strategy", "review my SETTINGS", "change my base currency"), or onboarding §4 delegates to it, follow `docs/settings_agent_guidelines.md`.

## Temp files

All temporary files (smoke-test inputs, scratch JSON, intermediate prices/context fixtures, regen output for verification, etc.) **MUST** be written under `/tmp/` — never inside the repository working tree. Portfolio-report pipeline intermediates — including `prices.json` (with merged `_history` / `_fx_history`), `report_snapshot.json`, `report_context.json`, `fill_history_gap.py --merge-into` targets, and optional `--ui-dict` overlay JSON — **must** live under a single per-run directory such as `/tmp/investments_portfolio_report_<RUN>/`; after the HTML is written and checks pass, remove that directory (`rm -rf`). Production HTML goes under `reports/`; **demo-ledger** runs additionally use `--cache demo/market_data_cache.db` on `fetch_history.py` / `fill_history_gap.py` (default cache is root `market_data_cache.db`) and should write the final HTML under **`demo/reports/`** so demo output stays under `demo/`. Canonical user-local artifacts live at the repo root (`SETTINGS.md`, `transactions.db` with append-only log plus materialized `open_lots` / `cash_balances`, `reports/<dated>_portfolio_report.html`); tracked source and contracts live under `scripts/` and `docs/` (see `README.md`). Anything ephemeral goes to `/tmp` and is cleaned up after use.
