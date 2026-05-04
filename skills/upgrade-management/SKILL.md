---
name: upgrade-management
description: Safely upgrade or update this investment repo without risking private portfolio data. Use when the user asks to upgrade, update, pull the latest version, install a new version, migrate after an update, or wants upgrade guidance; centralize the upgrade workflow so README files can stay brief.
---

# Upgrade Management

## Core Rule

Upgrade code and dependencies without overwriting private account data. This skill may update tracked repo code when the user asks to upgrade, but it must not edit or delete account `SETTINGS.md` or `transactions.db`. If an upgrade reveals an account-layout migration or any settings/ledger write, route to the matching account/settings/transaction skill and require that workflow's confirmation gate.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.

## Trigger Boundary

Use this skill for:

- upgrade / update this repo;
- pull latest / install newest version;
- upgrade guide / how do I update safely;
- post-upgrade migration checks;
- dependency refresh after updating the repo.

Do not use this skill for normal onboarding, report generation, investing advice, broker import, account switching, settings edits, or ledger writes except to route to the owning skill after the upgrade check.

## Safety Preflight

1. Inspect install mode and code state first:

```bash
git status --short
git remote -v
git branch --show-current
git describe --tags --exact-match
```

If this is not a Git checkout (`.git` is absent), treat it as an independent archive/zip copy and stop the automatic upgrade flow. Explain that this install has no Git history, so the assistant cannot safely align tags, branches, or local changes in place. Give natural-language manual update guidance: back up `accounts/` plus any root `SETTINGS.md` / `transactions.db`, download a fresh release copy, move the private account artifacts into the new copy only after checking the layout, then ask the assistant to run onboarding/post-upgrade checks. Recommend reinstalling with Git for future one-step upgrades.

If tracked source files have uncommitted changes in a Git checkout, do not pull or checkout over them. Summarize the conflict and ask whether the user wants to save, stash, discard, or handle those edits. Do not decide that branch for the user.

2. Before reading or backing up account files, run:

```bash
python scripts/transactions.py account detect
```

Apply the detector gate exactly:

- `partial`: hard stop; explain that account layout needs reconciliation before upgrade work touches account files.
- `migrate`: migration requires the account-management gate; finish code/dependency upgrade only when safe, then route to `skills/account-management/SKILL.md` for the gated migration.
- `clean` or `demo_only_at_root`: do not migrate.

3. Create a timestamped safety copy before code updates when private data exists. Prefer a directory under `/tmp`, for example `/tmp/investments_upgrade_backup_<timestamp>`, and copy only existing private artifacts:

```bash
accounts/
SETTINGS.md
transactions.db
```

This backup is protective copying, not permission to edit those files. Report the backup path.

## Install-Mode and Channel Rules

Preserve the user's installation channel unless the user explicitly asks to switch channels:

- **Git branch install on `main` / `master` / `trunk`:** update that branch from its upstream with fast-forward only. This is the default for users already on the rolling branch.
- **Git branch install on another branch:** update the current branch from its upstream with fast-forward only. If the branch has no upstream or appears custom/feature-only, stop and ask whether the user wants the current branch, latest stable tag, or `main`.
- **Git detached at a release tag:** stay on the release-tag channel. Fetch tags and move only to the latest stable release tag; do not switch to `main` by default.
- **Git checkout on a named release tag branch:** preserve that release channel unless the user asks for rolling `main`.
- **Release zip/archive install:** do not auto-update. This is an independent copy with no Git history, so safe tag/branch alignment is not available. Explain manual update steps and recommend Git for future updates.

Release selection:

- Prefer the latest non-prerelease semantic-version tag (`vX.Y.Z` / `X.Y.Z`) for stable release upgrades.
- Include prerelease tags only when the user asks for prerelease/beta/dev or the current install is already on a prerelease tag.
- If tags are not semantic versions, use the latest GitHub Release metadata when available; otherwise sort tags by creation date and report the heuristic.

Never use `git reset --hard`, force-pull, force-checkout, rebase, or overwrite archive installs as part of the automatic upgrade flow.

## Upgrade Workflow

1. **Update tracked code according to install mode.**

For Git branch installs with a clean tracked tree and a configured upstream, fetch first and then use a fast-forward-only update:

```bash
git fetch --tags --prune
git pull --ff-only
```

For Git tag installs, fetch tags and checkout the selected newer stable tag only when the working tree is clean:

```bash
git fetch --tags --prune
git checkout <latest-stable-tag>
```

For release zip/archive installs, stop before code changes. Do not download, replace, or merge archive code automatically. Provide the manual update guidance from Safety Preflight and recommend switching to Git.

If fast-forward or tag checkout cannot be done safely, do not force, rebase, reset, or improvise. Report the blocker and the safest next choice.

2. **Refresh runtime dependencies.** After the code update, refresh the small runtime dependency set:

```bash
python3 -m pip install --upgrade yfinance requests
```

If dependency installation fails, report the error and continue with read-only validation where possible.

3. **Run post-upgrade checks.** Use the smallest checks that prove the repo is usable:

```bash
python scripts/validate_project_skills.py
python scripts/transactions.py account detect
python scripts/transactions.py account list
```

If the detector prints `migrate` after the update, stop before migration and route to `skills/account-management/SKILL.md`; migration is allowed only when `account detect` prints exactly `migrate` and the user confirms that account-management write.

4. **Optional smoke check.** If the user wants confidence before touching real data, use the demo path through `skills/report-management/SKILL.md`. Keep demo artifacts isolated under `demo/` and `/tmp` according to `demo/README.md`.

## Output Contract

Report only concise upgrade evidence:

- code update result;
- backup path, or why no backup was needed;
- dependency refresh result;
- account detector state;
- validation/smoke-check result;
- whether a gated follow-up migration or data repair is needed.

Do not paste long command logs unless they explain a blocker.

## Stop Conditions

Stop and ask or route when:

- tracked local edits would be overwritten;
- the repo is an independent archive/zip copy rather than a Git checkout;
- no safe Git remote/update path exists;
- `account detect` prints `partial`;
- migration is needed (`migrate`) and the user has not confirmed the account-management migration gate;
- dependency installation or validation fails in a way that blocks normal use;
- any step would edit/delete `SETTINGS.md`, `transactions.db`, or derived ledger tables outside the owning workflow.
