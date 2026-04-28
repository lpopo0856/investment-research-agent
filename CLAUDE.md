# Guide

**README languages** · [English](README.md) · [繁體中文](docs/l10n/README.zh-Hant.md) · [简体中文](docs/l10n/README.zh-Hans.md) · [日本語](docs/l10n/README.ja.md) · [Tiếng Việt](docs/l10n/README.vi.md) · [한국어](docs/l10n/README.ko.md)

**CRITICAL** **MUST READ** READ AGENTS.md, README.md, /docs/* under root directory

## Temp files

All temporary files (smoke-test inputs, scratch JSON, intermediate prices/context fixtures, regen output for verification, etc.) **MUST** be written under `/tmp/` — never inside the repository working tree. The repo only stores canonical artifacts (`HOLDINGS.md`, `SETTINGS.md`, `reports/<dated>_portfolio_report.html`, source under `scripts/`, `docs/`). Anything ephemeral goes to `/tmp` and is cleaned up after use.
