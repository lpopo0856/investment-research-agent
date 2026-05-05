# Investment Research Agent

**Do not edit/delete `SETTINGS.md` or `transactions.db` unless the user explicitly asks and the matching workflow confirmation gate is satisfied.**

This file is the top-level router and non-negotiable safety floor. Detailed workflow rules live in `skills/*/SKILL.md` and `docs/*.md`; do not duplicate them here. When a skill or doc is more specific, follow it.

## Natural-language user interface

The user-facing interface is natural language by default in every workflow. Command snippets, file paths, flags, schemas, and JSON blobs in skills/docs are **agent-internal execution contracts** or audit evidence, not instructions for the user to learn, compose, or run. For safe/read-only checks and already-authorized reversible work, run the commands yourself through the available tools, then report the result in natural language.

Do not ask the user to run `python ...`, copy shell snippets, remember canonical command names, choose flags, assemble files, or produce machine-formatted JSON unless they explicitly ask for CLI/API instructions or execution is blocked by missing credentials/authority. Collect missing parameters conversationally; translate internal commands into natural-language actions and offer to perform the next safe/gated step. Confirmation gates stay natural-language gates: describe the intended write and ask for the required `yes / no / edit`, without delegating command execution or machine formatting to the user.


## Active-account context gate

Any account-sensitive workflow must resolve the target account before producing account-bound output or touching account files. Account-sensitive workflows include investment research or advice, portfolio fit/sizing/risk work, reports, transaction or cash-flow changes, ledger inspection, settings review/edit, account split/migration, and help/status replies that depend on account state. If the user does not specify an account, use the current active account; if no active pointer exists but `default` is safely available, use `default`. Stop on `partial` or unsafe detector states and explain the reconciliation need in natural language.

Account-sensitive workflows also require usable account settings. If no
account is safely resolvable, or the target account is missing `SETTINGS.md` /
has only template-backed incomplete settings, stop before account-bound output
and guide the user through onboarding/settings completion first. Bootstrap
exceptions are limited to generic non-personalized education/news/research,
repo maintenance that does not read or depend on account files, safe account
detection/listing, and the onboarding/settings interview needed to finish
setup.

Generic market education/news and pure repo maintenance do not need account resolution unless the answer becomes personalized, reads `SETTINGS.md`/`transactions.db`, or affects account state. For personalized research, always load the resolved account's strategy and current portfolio/ledger context before making recommendations; if context cannot be resolved, provide only generic research and label it non-personalized.

## Workflow routing via project skills

At task start, scan root-level `skills/*/SKILL.md` frontmatter/descriptions and load the matching skill body. Skills are concise routers, safety gates, and canonical command contracts; the referenced docs are the full source of truth.

Core workflow skills:

- `skills/investment-help/SKILL.md` — capability menu for “help / what can I do here / now what”.
- `skills/onboarding/SKILL.md` — new users, missing account files, legacy-layout migration, statement import bootstrap.
- `skills/transaction-management/SKILL.md` — trades, cash flows, dividends, corrections, broker CSV/JSON imports.
- `skills/account-management/SKILL.md` — account detect/list/use/create/migrate, with side-effect classification.
- `skills/settings-management/SKILL.md` — `SETTINGS.md` setup/review/edit and strategy interview.
- `skills/report-management/SKILL.md` — `daily_report` / `portfolio_report` / all-accounts / demo HTML pipeline gate.
- `skills/investment-analysis/SKILL.md` — ad hoc stock / ETF / crypto / market / portfolio analysis without HTML generation.
- `skills/context-economy/SKILL.md` — context-drop / temp-researcher gate for large extraction or research phases.
- `skills/split-asset-account/SKILL.md` — auditable account split / sleeve migration.
- `skills/upgrade-management/SKILL.md` — safe repo upgrade/update flow with backup, dependency refresh, and account-layout migration gates.

Canonical docs behind those skills:

- `docs/help_agent_guidelines.md`
- `docs/onboarding_agent_guidelines.md`
- `docs/transactions_agent_guidelines.md`
- `docs/settings_agent_guidelines.md`
- `docs/portfolio_report_agent_guidelines.md`
- `docs/context_drop_protocol.md`
- `docs/temp_researcher_contract.md`

## Hard floors no skill may weaken

1. **Protected files:** do not edit/delete account `SETTINGS.md` or `transactions.db` unless the user explicitly asks and the matching skill/doc confirmation gate has passed.
2. **Multi-account preflight:** before any non-interactive script reads account `SETTINGS.md` or `transactions.db`, run `python scripts/transactions.py account detect`. Run migration only when the detector prints exactly `migrate`; stop on `partial`; do not migrate on `clean` or `demo_only_at_root`.
3. **Ledger writes:** use `skills/transaction-management/SKILL.md`. Never insert/import without parsed plan, canonical JSON or `/tmp` JSON path, resulting-state preview, explicit same-turn `yes`, backup, and verify. Never SQL-update/delete ledger rows or edit derived tables directly.
4. **Settings writes:** use `skills/settings-management/SKILL.md`. Never write without proposed content or unified diff, explicit same-turn `yes`, and backup for existing files. Never invent strategy or leak secrets.
5. **Report generation:** use `skills/report-management/SKILL.md`. Report intermediates stay under `/tmp`; final HTML only goes to the configured reports path; `portfolio_report` must not gather daily decision/news/action content.
6. **Skill drift check:** after changing project skills, run `python scripts/validate_project_skills.py`.
