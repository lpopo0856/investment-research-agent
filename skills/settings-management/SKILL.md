---
name: settings-management
description: Safely set up, review, or edit an account SETTINGS.md through the canonical settings interview and diff-confirm workflow. Use when the user wants to change account description, language, base currency, time zone, investment strategy, rails, or asks what strategy is internalized; never invent strategy or store settings outside the account file.
---

# Settings Management

## Core Rule

Follow `docs/settings_agent_guidelines.md` end to end. Settings edits are user-authored configuration changes, not agent inference. Never invent account purpose, investment strategy, risk tolerance, sizing rails, or preferences the user did not state.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.

## Active Account Detection

Determine the target account before reading or editing settings; do not guess from repo paths or stale context. Use the user-named account when provided; otherwise use the current active account, falling back to `default` only when safely resolvable:

```bash
python scripts/transactions.py account detect
python scripts/transactions.py account list
```

Stop on `partial`. If the settings workflow needs an account scaffold, route to the account/onboarding workflow before editing settings.

## Bootstrap Rule

Bootstrap from `SETTINGS.example.md` only under the settings workflow in
`docs/settings_agent_guidelines.md`. For first creation, create
`accounts/<active>/SETTINGS.md` from the template only after the workflow has
established the active account and the user-facing settings path. Treat that
file as a scaffold/draft, not usable settings, until the user has supplied or
confirmed Account description, Language, Investment Style And Strategy, and
Base currency.

During onboarding/account creation, ask for those four fields with short
introductions and visible defaults. If the default/example Investment Style And
Strategy text is long, show only a brief summary unless the user asks for the
full text. Other defaults from `SETTINGS.example.md` may be carried forward,
but show them at the end and tell the user they can ask the agent to change any
value anytime. Account description may remain blank only when the user
explicitly confirms the blank value.

Never store strategy drafts or derived preferences outside SETTINGS.md except transient `/tmp` work files that are cleaned up.

## Diff-Confirm Edit Gate

Before confirmed edits to an existing settings file, back it up:

```bash
cp accounts/<active>/SETTINGS.md accounts/<active>/SETTINGS.md.bak
```

Then show the proposed full content or a unified diff.

Require explicit same-turn `yes` before writing. The confirmation prompt should be the settings workflow prompt, for example:

```text
Confirm and write? (yes / no / edit)
```

For a new strategy section or first creation, show the full proposed section/content instead of relying on a terse summary. If the user says `edit`, revise and repeat the diff-confirm gate. If the user says `no`, do not write.

## Safety Rules

- Backup before editing an existing `accounts/<active>/SETTINGS.md`; first creation is the only backup exception.
- Never rewrite strategy from defaults or market views; ask the user or leave neutral/default text as explicitly labeled fallback.
- Never place strategy or derived preferences in another file, project memory, report context, or ledger metadata.
- Keep account description/language/base currency/time zone changes inside `SETTINGS.md` and verify by re-reading the changed section after write.
- Do not edit `transactions.db`, `open_lots`, `cash_balances`, reports, or Python scripts as part of settings management.
