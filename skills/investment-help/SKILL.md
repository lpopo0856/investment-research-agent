---
name: investment-help
description: Render the repo's state-aware capability menu for investment workflows. Use when the user asks "help", "what can I do here", "what can you do", "show me what's possible", "now what", or does not know where to start; route specific requests directly to onboarding, transaction-management, settings-management, research, or report workflows instead of rendering the menu.
---

# Investment Help

## Core Rule

This skill is the conversational front door. Follow `docs/help_agent_guidelines.md`; render a short state-aware menu, then stop and let the user choose. Do not record transactions, edit settings, onboard, research, or generate reports inside the help reply.

Do not call this skill `help`; that conflicts with the global OMX help surface. This project skill is specifically the investment capability menu.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.

## Trigger Boundary

Use this skill for broad capability questions:

- "help"
- "what can I do here?"
- "what can you do?"
- "show me what's possible"
- "now what?"
- "I don't know where to start"

If the user already asks for a specific workflow, skip the menu and route directly:

- setup/import/new user → `skills/onboarding/SKILL.md`
- trade/cash/dividend/correction/import write → `skills/transaction-management/SKILL.md`
- account list/switch/create/migrate → `skills/account-management/SKILL.md`
- settings/strategy/language/base currency/API keys → `skills/settings-management/SKILL.md`
- report generation → `skills/report-management/SKILL.md`
- investment research → `skills/investment-analysis/SKILL.md`

## State Check

Before rendering the menu, gather only enough account state to tailor it, including the active/default account when safely resolvable. Prefer read-only checks:

```bash
python scripts/transactions.py account detect
python scripts/transactions.py account list
python scripts/transactions.py db stats
```

If those are unavailable during early setup, fall back to lightweight file presence checks described in `docs/help_agent_guidelines.md`. Do not write files, switch accounts, initialize DBs, or migrate from this skill.

## Menu Contract

Render the menu exactly as a menu, not as implementation:

1. Start with one sentence naming the detected state: cold start, legacy layout, empty DB, ready, or multiple accounts.
2. Show the four core capabilities from `docs/help_agent_guidelines.md`:
   - onboarding / import
   - record a transaction
   - research a name or portfolio
   - generate a report
3. Add the conditional total-account and switch-account notes only when multiple accounts exist.
4. Add the one-line settings customization pointer.
5. Close with one open-ended prompt asking what the user wants to do.

Do not include CLI snippets in the rendered menu; the user is asking the agent, not the shell. Keep the reply to 25 lines or fewer and use the `SETTINGS.md` language if safely available.

## Stop Conditions

- If `python scripts/transactions.py account detect` prints `partial`, say the repo needs reconciliation and route to `docs/onboarding_agent_guidelines.md`; do not continue to normal menu actions.
- If the user picks an item, stop using this skill and load the matching project skill or guideline.
- If the user asks for specific investment advice, route to the investment analysis contract; do not answer research inside the help menu.
