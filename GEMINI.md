# Guide

**README languages** · [English](README.md) · [繁體中文](docs/l10n/README.zh-Hant.md) · [简体中文](docs/l10n/README.zh-Hans.md) · [日本語](docs/l10n/README.ja.md) · [Tiếng Việt](docs/l10n/README.vi.md) · [한국어](docs/l10n/README.ko.md)

**CRITICAL** **MUST READ** READ AGENTS.md, README.md, /docs/* under root directory

## Multi-account model

This repo uses a multi-account layout: each account owns its files under `accounts/<name>/` (e.g. `accounts/default/SETTINGS.md`, `accounts/default/transactions.db`, `accounts/default/reports/`). Pass `--account <name>` to any script to target a specific account; omitting the flag resolves via `accounts/.active` → `accounts/default/` → error. The shared price/FX cache (`market_data_cache.db`) and `demo/` directory live at the repo root and are never account-scoped. Agents running non-interactively MUST run a layout preflight (`python scripts/transactions.py account detect`) before any script that reads SETTINGS.md or transactions.db; invoke `python scripts/transactions.py account migrate --yes` only when the detector prints `migrate`. If it prints `clean` or `demo_only_at_root`, do not run migration. If it prints `partial`, stop and follow the onboarding reconciliation path. See `docs/onboarding_agent_guidelines.md` for the full migration and onboarding flow.

## Project skills

Root-level `skills/<skill-name>/SKILL.md` files are project-local workflow contracts shared across Codex, Claude, Gemini, and other agents. At task start, scan `skills/*/SKILL.md` frontmatter and descriptions; when the user request matches a skill trigger, read that skill body and follow it. Prefer any reusable repo code named by the skill under `scripts/`.

## New users

If `accounts/<active>/SETTINGS.md` or `accounts/<active>/transactions.db` is missing (or the legacy root layout is detected), or the user asks to get started / onboard / import a statement in any format (PDF, CSV, JSON, XLSX, screenshot, pasted text), follow `docs/onboarding_agent_guidelines.md`. It is the brand-agnostic on-ramp; once the DB has rows, route to `docs/transactions_agent_guidelines.md`.

## Help — capability menu

If the user asks "help" / "what can I do here" / "now what" / similar overview requests, follow `docs/help_agent_guidelines.md`. It renders a state-aware four-item menu and routes to the right contract doc.

## Settings interview

If the user asks to set up / edit / review `SETTINGS.md` ("walk me through my settings", "set up my strategy", "review my SETTINGS", "change my base currency"), or onboarding §4 delegates to it, follow `docs/settings_agent_guidelines.md`. The settings file for the active account lives at `accounts/<active>/SETTINGS.md` (not at the repo root).

## Context drop (token economy)

Multi-stage workflows must minimize cumulative input tokens by keeping research-class data **out of the parent agent's context by construction**. Full rules: `docs/context_drop_protocol.md`. Brand-agnostic temp-researcher execution contract: `docs/temp_researcher_contract.md`. Pipeline applications: `docs/context_drop_pipeline_audit.md`. Short version: any phase whose deliverable is a file or short summary AND whose internal work involves > 5K tokens of tool output (WebSearch dumps, PDF/image extraction, large-file reads) **must** be delegated to a temp-researcher using the runtime's isolation primitive (for Gemini CLI: a subagent invocation or a fresh session). The temp-researcher writes findings to a result file and returns only `{result_file, summary, audit}` — never paste raw findings back into the parent. The result file is the only thing that crosses the phase boundary. Canonical applications: §10.5 news/events research, onboarding §6.2 statement extraction, large bulk-import parsing.
