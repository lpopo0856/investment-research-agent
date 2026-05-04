#!/usr/bin/env python3
"""Static validator for project-local workflow skills.

This script is intentionally stdlib-only and non-destructive.  It checks the
thin skill contracts approved in:
  .omx/plans/prd-skill-framework-onboarding-tx-account-settings-20260504.md
  .omx/plans/test-spec-skill-framework-onboarding-tx-account-settings-20260504.md

Default behavior runs built-in fixture self-tests first, then validates the
repository rooted at the current working directory (or --root).
"""

from __future__ import annotations

import argparse
import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence


EXPECTED_SKILLS = {
    "investment-help": {
        "path": "skills/investment-help/SKILL.md",
        "docs": [
            "docs/help_agent_guidelines.md",
            "skills/onboarding/SKILL.md",
            "skills/transaction-management/SKILL.md",
            "skills/account-management/SKILL.md",
            "skills/settings-management/SKILL.md",
            "skills/report-management/SKILL.md",
            "skills/investment-analysis/SKILL.md",
        ],
        "commands": [
            "python scripts/transactions.py account detect",
            "python scripts/transactions.py account list",
            "python scripts/transactions.py db stats",
        ],
        "phrases": [
            ["conversational", "front door"],
            ["state-aware", "menu"],
            ["do not", "record transactions"],
            ["do not", "CLI snippets"],
            ["25 lines"],
            ["route directly"],
            ["active/default account"],
        ],
    },
    "onboarding": {
        "path": "skills/onboarding/SKILL.md",
        "docs": [
            "docs/onboarding_agent_guidelines.md",
            "docs/settings_agent_guidelines.md",
            "docs/transactions_agent_guidelines.md",
        ],
        "commands": [
            "python3 --version",
            "python3 -m pip install yfinance requests",
            "python scripts/transactions.py account detect",
            "python scripts/transactions.py account migrate --yes",
            "python scripts/transactions.py account create <name>",
        ],
        "phrases": [
            ["router", "not", "absorber"],
            ["Environment Preflight"],
            ["agent owns the technical setup check"],
            ["Python", "missing", "older than 3.11"],
            ["installing or updating", "Python 3.11+"],
            ["explicit", "same-turn", "yes"],
            ["dependencies are missing", "install"],
            ["/tmp"],
            ["temp-researcher"],
            ["batch", "confirmation"],
            ["do not", "report generation"],
            ["active/default account workflow"],
        ],
    },
    "transaction-management": {
        "path": "skills/transaction-management/SKILL.md",
        "docs": ["docs/transactions_agent_guidelines.md"],
        "commands": [
            "python scripts/transactions.py db add --json '<canonical-json>' --account <name>",
            "python scripts/transactions.py db import-csv --input <path> --account <name>",
            "python scripts/transactions.py db import-json --input <path> --account <name>",
            "python scripts/transactions.py verify --account <name>",
            "python scripts/transactions.py db stats --account <name>",
            "python scripts/transactions.py self-check",
        ],
        "phrases": [
            ["parsed", "trades"],
            ["write plan"],
            ["canonical json"],
            ["resulting state preview"],
            ["sell", "realized"],
            ["Confirm and write? (yes / no / edit)"],
            ["Target Account Resolution"],
            ["resolved account name"],
            ["active account", "default"],
        ],
    },
    "account-management": {
        "path": "skills/account-management/SKILL.md",
        "docs": [
            "docs/onboarding_agent_guidelines.md",
            "docs/transactions_agent_guidelines.md",
        ],
        "commands": [
            "python scripts/transactions.py account detect",
            "python scripts/transactions.py account list",
            "python scripts/transactions.py account --help",
            "python scripts/transactions.py account use <name>",
            "python scripts/transactions.py account create <name>",
            "python scripts/transactions.py account migrate --yes",
        ],
        "phrases": [
            ["read-only"],
            ["write-capable", "gated"],
            ["forbidden"],
            ["partial", "hard stop"],
            ["clean", "do not migrate"],
            ["demo_only_at_root", "do not migrate"],
        ],
    },
    "split-asset-account": {
        "path": "skills/split-asset-account/SKILL.md",
        "docs": [
            "docs/transactions_agent_guidelines.md",
        ],
        "commands": [
            "python scripts/transactions.py account detect",
            "python scripts/transactions.py account list",
            "python scripts/split_asset_account.py",
            "python scripts/transactions.py verify --account <source>",
            "python scripts/transactions.py verify --account <target>",
        ],
        "phrases": [
            ["dry-run"],
            ["--apply"],
            ["backup"],
            ["verify_issues"],
            ["never edit derived balance tables"],
            ["Resolve the source account"],
            ["active account", "default"],
            ["partial", "hard stop"],
        ],
    },
    "settings-management": {
        "path": "skills/settings-management/SKILL.md",
        "docs": ["docs/settings_agent_guidelines.md"],
        "commands": [
            "cp accounts/<active>/SETTINGS.md accounts/<active>/SETTINGS.md.bak",
        ],
        "phrases": [
            ["active account"],
            ["SETTINGS.example.md"],
            ["unified diff"],
            ["same-turn", "yes"],
            ["never invent strategy"],
            ["Never store", "strategy", "outside SETTINGS.md"],
            ["target account before reading or editing settings"],
            ["active account", "default"],
        ],
    },
    "report-management": {
        "path": "skills/report-management/SKILL.md",
        "docs": [
            "docs/portfolio_report_agent_guidelines.md",
            "docs/portfolio_report_agent_guidelines/",
            "docs/portfolio_report_agent_guidelines/07-investment-content-and-checklist.md",
            "skills/investment-help/SKILL.md",
            "skills/investment-analysis/SKILL.md",
        ],
        "commands": [
            "python scripts/transactions.py account detect",
            "python scripts/fetch_prices.py --account <name> --output \"$REPORT_RUN_DIR/prices.json\"",
            "python scripts/fetch_history.py --account <name> --merge-into \"$REPORT_RUN_DIR/prices.json\"",
            "python scripts/transactions.py snapshot --account <name> --prices \"$REPORT_RUN_DIR/prices.json\" --output \"$REPORT_RUN_DIR/report_snapshot.json\"",
            "python scripts/validate_report_context.py --snapshot \"$REPORT_RUN_DIR/report_snapshot.json\" --context \"$REPORT_RUN_DIR/report_context.json\" --report-type <daily_report|portfolio_report>",
            "python scripts/generate_report.py --report-type <daily_report|portfolio_report> --account <name> --snapshot \"$REPORT_RUN_DIR/report_snapshot.json\" --context \"$REPORT_RUN_DIR/report_context.json\"",
            "python scripts/fill_history_gap.py",
        ],
        "phrases": [
            ["daily_report", "portfolio_report"],
            ["/tmp", "REPORT_RUN_DIR"],
            ["do not", "--allow-incomplete"],
            ["portfolio_report", "must not", "news"],
            ["validate_report_context.py"],
            ["rm -rf", "$REPORT_RUN_DIR"],
            ["demo", "demo/market_data_cache.db"],
            ["active/default account", "single-account"],
            ["scope is not", "resolve"],
        ],
    },
    "investment-analysis": {
        "path": "skills/investment-analysis/SKILL.md",
        "docs": [
            "docs/portfolio_report_agent_guidelines/07-investment-content-and-checklist.md",
            "skills/report-management/SKILL.md",
        ],
        "commands": [
            "python scripts/transactions.py account detect",
        ],
        "phrases": [
            ["ad hoc", "HTML report"],
            ["SETTINGS.md", "Investment Style And Strategy"],
            ["latest public information"],
            ["Consensus", "Variant", "Anchor"],
            ["unknown-consensus"],
            ["R:R", "Kill"],
            ["pp of NAV"],
            ["portfolio fit"],
            ["Reviewer pass"],
            ["do not edit", "SETTINGS.md", "transactions.db"],
            ["never fabricate"],
            ["account-bound", "active account"],
            ["portfolio/ledger context"],
            ["generic/non-personalized research"],
        ],
    },
    "context-economy": {
        "path": "skills/context-economy/SKILL.md",
        "docs": [
            "docs/context_drop_protocol.md",
            "docs/temp_researcher_contract.md",
        ],
        "commands": [],
        "phrases": [
            ["context hygiene", "gate"],
            ["5K", "raw tool output"],
            ["temp-researcher"],
            ["result_file", "summary", "audit"],
            ["do not paste raw findings"],
            ["/tmp"],
            ["jq . <path>"],
            ["parent reads artifacts lazily"],
            ["No artifact", "no drop"],
            ["portfolio_report", "news"],
        ],
    },
    "upgrade-management": {
        "path": "skills/upgrade-management/SKILL.md",
        "docs": [
            "skills/account-management/SKILL.md",
            "skills/report-management/SKILL.md",
            "demo/README.md",
        ],
        "commands": [
            "git status --short",
            "git remote -v",
            "git branch --show-current",
            "git describe --tags --exact-match",
            "python scripts/transactions.py account detect",
            "git fetch --tags --prune",
            "git pull --ff-only",
            "git checkout <latest-stable-tag>",
            "python3 -m pip install --upgrade yfinance requests",
            "python scripts/validate_project_skills.py",
            "python scripts/transactions.py account list",
        ],
        "phrases": [
            ["upgrade code", "without overwriting private account data"],
            ["must not edit or delete", "SETTINGS.md", "transactions.db"],
            ["tracked source files", "uncommitted changes", "do not pull"],
            ["partial", "hard stop"],
            ["migrate", "migration requires the account-management gate"],
            ["clean", "demo_only_at_root", "do not migrate"],
            ["backup", "path"],
            ["fast-forward-only"],
            ["Preserve the user's installation channel"],
            ["Git branch install", "main"],
            ["Git detached at a release tag", "latest stable release tag"],
            ["Release zip/archive install", "do not auto-update"],
            ["independent archive/zip copy"],
            ["Recommend", "Git", "future"],
            ["latest non-prerelease semantic-version tag"],
            ["validation", "smoke-check"],
        ],
    },
}

ACCOUNT_WRITE_COMMANDS = [
    "python scripts/transactions.py account use <name>",
    "python scripts/transactions.py account create <name>",
    "python scripts/transactions.py account migrate --yes",
]

TRANSACTION_WRITE_COMMANDS = [
    "python scripts/transactions.py db add --json '<canonical-json>' --account <name>",
    "python scripts/transactions.py db import-csv --input <path> --account <name>",
    "python scripts/transactions.py db import-json --input <path> --account <name>",
]

UNSAFE_PHRASES = [
    "skip confirmation",
    "migrate automatically",
    "edit transactions.db manually",
    "write without confirmation",
    "insert without confirmation",
    "no confirmation needed",
]

USER_FACING_EXECUTION_RULE = """\

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.
"""

USER_FACING_EXECUTION_TERMS = [
    ["Natural-Language User Interface"],
    ["natural language", "default user interface"],
    ["internal agent contracts", "audit evidence"],
    ["Execute", "steps", "yourself"],
    ["collect missing parameters conversationally"],
    ["Do not ask", "user", "run commands", "choose flags", "write JSON"],
    ["Confirmation gates", "natural language", "must not delegate command execution"],
]

PROHIBITION_CUES = (
    "forbid",
    "forbidden",
    "never",
    "do not",
    "don't",
    "must not",
    "no ",
    "avoid",
    "prohibit",
    "disallow",
)


@dataclass(frozen=True)
class ValidationError:
    path: str
    message: str

    def render(self) -> str:
        return f"{self.path}: {self.message}"


class SkillValidationFailed(Exception):
    def __init__(self, errors: Sequence[ValidationError]):
        self.errors = list(errors)
        super().__init__("; ".join(error.render() for error in self.errors))


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse simple YAML-like frontmatter without external dependencies."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + len("\n---") :]
    frontmatter: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        value = value.strip().strip('"').strip("'")
        frontmatter[key.strip()] = value
    return frontmatter, body


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def contains_all(text: str, words: Sequence[str]) -> bool:
    haystack = normalize(text)
    return all(word.lower() in haystack for word in words)


def line_is_prohibition(line: str) -> bool:
    lowered = line.lower()
    return any(cue in lowered for cue in PROHIBITION_CUES)


def command_pattern(command: str) -> re.Pattern[str]:
    """Build a tolerant regex for a canonical command string."""
    parts = re.split(r"(\s+)", command)
    pattern = ""
    for part in parts:
        if not part:
            continue
        if part.isspace():
            pattern += r"\s+"
        else:
            pattern += re.escape(part).replace(r"\'", "['\u2018\u2019]")
    return re.compile(pattern)


def has_command(text: str, command: str) -> bool:
    return bool(command_pattern(command).search(text))


def nearby_text(text: str, needle: str, window: int = 500) -> str:
    match = command_pattern(needle).search(text)
    if not match:
        return ""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    return text[start:end]


def require_terms(path: str, text: str, term_groups: Iterable[Sequence[str]], label: str) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for terms in term_groups:
        if isinstance(terms, str):
            present = terms in text
            rendered = terms
        else:
            present = contains_all(text, terms)
            rendered = " + ".join(terms)
        if not present:
            errors.append(ValidationError(path, f"missing {label}: {rendered}"))
    return errors


def validate_frontmatter(path: str, text: str) -> list[ValidationError]:
    frontmatter, _ = parse_frontmatter(text)
    errors: list[ValidationError] = []
    for key in ("name", "description"):
        if not frontmatter.get(key):
            errors.append(ValidationError(path, f"frontmatter missing non-empty {key}"))
    return errors


def validate_migrate_gate(path: str, text: str) -> list[ValidationError]:
    if "python scripts/transactions.py account migrate --yes" not in text:
        return []
    lowered = normalize(text)
    errors: list[ValidationError] = []
    for phrase in ("partial", "clean", "demo_only_at_root"):
        if phrase not in lowered:
            errors.append(ValidationError(path, f"migrate --yes missing detect-state restriction: {phrase}"))
    exact_migrate_patterns = [
        r"only\s+when\s+(?:python\s+scripts/transactions\.py\s+)?(?:account\s+)?detect\s+print(?:s|ed)\s+exactly\s+[`'\"]?migrate",
        r"only\s+when\s+.{0,120}account\s+detect.{0,40}print(?:s|ed)\s+exactly\s+[`'\"]?migrate",
        r"allowed\s+only\s+after\s+(?:python\s+scripts/transactions\.py\s+)?(?:account\s+)?detect\s+print(?:s|ed)\s+exactly\s+[`'\"]?migrate",
        r"unless\s+[`'\"]?account\s+detect[`'\"]?\s+print(?:s|ed)\s+exactly\s+[`'\"]?migrate",
    ]
    if not any(re.search(pattern, lowered) for pattern in exact_migrate_patterns):
        errors.append(ValidationError(path, "migrate --yes must be gated by exact detect output `migrate`"))
    for state in ("clean", "demo_only_at_root"):
        if not re.search(rf"{state}.{{0,120}}(must not|do not|don't|never|no).{{0,80}}migrat", lowered):
            errors.append(ValidationError(path, f"migrate --yes must not run on {state}"))
    if not re.search(r"partial.{0,120}(hard stop|stop)", lowered):
        errors.append(ValidationError(path, "partial detector state must be a hard stop"))
    return errors


def validate_account_write_gates(path: str, text: str) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for command in ACCOUNT_WRITE_COMMANDS:
        if not has_command(text, command):
            continue
        context = nearby_text(text, command)
        if command.endswith("migrate --yes"):
            errors.extend(validate_migrate_gate(path, text))
            continue
        if not any(word in path for word in ("account-management",)):
            continue
        if not contains_all(context, ["gated"]):
            errors.append(ValidationError(path, f"write-capable account command lacks nearby gated language: {command}"))
    return errors


def validate_transaction_write_gates(path: str, text: str) -> list[ValidationError]:
    if not any(has_command(text, command) for command in TRANSACTION_WRITE_COMMANDS):
        return []
    required_groups = [
        ["Confirm and write? (yes / no / edit)"],
        ["backup"],
        ["python scripts/transactions.py verify --account <name>"],
        ["roll"],
    ]
    return require_terms(path, text, required_groups, "transaction write gate")


def validate_settings_write_gates(path: str, text: str) -> list[ValidationError]:
    settings_markers = [
        "SETTINGS.md",
        "cp accounts/<active>/SETTINGS.md accounts/<active>/SETTINGS.md.bak",
    ]
    if not any(marker in text for marker in settings_markers):
        return []
    required_groups = [
        ["unified diff"],
        ["explicit", "same-turn", "yes"],
        ["backup"],
    ]
    return require_terms(path, text, required_groups, "settings write gate")


def validate_unsafe_wording(path: str, text: str) -> list[ValidationError]:
    errors: list[ValidationError] = []
    lowered = text.lower()
    for phrase in UNSAFE_PHRASES:
        if phrase in lowered:
            errors.append(ValidationError(path, f"unsafe wording present: {phrase}"))
    unconditional_patterns = [
        r"\balways\s+(?:run|execute|write|insert|import|migrate)\b",
        r"\b(?:run|execute)\s+.*migrate\s+--yes\s+without\s+detect",
        r"\b(?:write|insert|import)\s+.*without\s+(?:confirmation|backup|verify|verification)",
    ]
    for pattern in unconditional_patterns:
        match = re.search(pattern, lowered)
        if match:
            errors.append(ValidationError(path, f"unconditional live-write instruction: {match.group(0)}"))
    return errors


def validate_forbidden_mutation_language(path: str, text: str) -> list[ValidationError]:
    errors: list[ValidationError] = []
    mutation_patterns = [
        re.compile(r"\b(?:run|execute|use|issue|perform)\s+(?:raw\s+)?(?:sql\s+)?(?:update|delete)\b", re.I),
        re.compile(r"\b(?:update|delete)\s+(?:the\s+)?(?:ledger|ledger tables|transactions\.db|transactions|open_lots|cash_balances)\b", re.I),
        re.compile(r"\b(?:edit|modify|patch|write)\s+(?:the\s+)?(?:open_lots|cash_balances|derived tables?)\b", re.I),
        re.compile(r"\bdirect(?:ly)?\s+(?:edit|modify|write)\s+(?:open_lots|cash_balances|derived tables?)\b", re.I),
    ]
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line_is_prohibition(line):
            continue
        for pattern in mutation_patterns:
            match = pattern.search(line)
            if match:
                errors.append(
                    ValidationError(path, f"forbidden SQL/derived-table mutation language on line {line_number}: {match.group(0)}")
                )
    return errors


def validate_skill(root: Path, skill_key: str, spec: Mapping[str, object]) -> list[ValidationError]:
    rel_path = str(spec["path"])
    path = root / rel_path
    if not path.exists():
        return [ValidationError(rel_path, "missing expected skill file")]
    text = path.read_text(encoding="utf-8")
    errors: list[ValidationError] = []
    errors.extend(validate_frontmatter(rel_path, text))
    errors.extend(require_terms(rel_path, text, spec.get("docs", ()), "required source-doc reference"))
    for command in spec.get("commands", ()):  # type: ignore[union-attr]
        if not has_command(text, str(command)):
            errors.append(ValidationError(rel_path, f"missing canonical command: {command}"))
    errors.extend(require_terms(rel_path, text, spec.get("phrases", ()), "required workflow language"))
    errors.extend(require_terms(rel_path, text, USER_FACING_EXECUTION_TERMS, "user-facing execution rule"))
    errors.extend(validate_account_write_gates(rel_path, text))
    if skill_key == "transaction-management":
        errors.extend(validate_transaction_write_gates(rel_path, text))
    if skill_key == "settings-management":
        errors.extend(validate_settings_write_gates(rel_path, text))
    errors.extend(validate_unsafe_wording(rel_path, text))
    errors.extend(validate_forbidden_mutation_language(rel_path, text))
    return errors


def validate_root(root: Path) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for skill_key, spec in EXPECTED_SKILLS.items():
        errors.extend(validate_skill(root, skill_key, spec))
    return errors


def positive_fixture_text(skill_key: str) -> str:
    fixtures = {
        "investment-help": """---
name: investment-help
description: Render a state-aware investment capability menu.
---
# Investment Help
This skill is the conversational front door. Follow docs/help_agent_guidelines.md.
Route directly to skills/onboarding/SKILL.md, skills/transaction-management/SKILL.md,
skills/account-management/SKILL.md, skills/settings-management/SKILL.md,
skills/report-management/SKILL.md, skills/investment-analysis/SKILL.md, or AGENTS.md for research.
Use a state-aware menu for the active/default account. Run read-only checks:
`python scripts/transactions.py account detect`
`python scripts/transactions.py account list`
`python scripts/transactions.py db stats`
Do not record transactions, edit settings, onboard, research, or generate reports inside the help reply.
Do not include CLI snippets in the rendered menu. Keep it to 25 lines.
If the user asks a specific workflow, route directly to that workflow.
""",
        "onboarding": """---
name: onboarding
description: Route onboarding through source docs and canonical gated commands.
---
# Onboarding
This skill is a router, not an absorber. Use docs/onboarding_agent_guidelines.md,
docs/settings_agent_guidelines.md, and docs/transactions_agent_guidelines.md.
Environment Preflight: the agent owns the technical setup check. Run `python3 --version`.
If Python is missing or older than 3.11, ask before installing or updating Python 3.11+ and require explicit same-turn yes.
If dependencies are missing, install with `python3 -m pip install yfinance requests`.
Run layout preflight: `python scripts/transactions.py account detect`.
Run `python scripts/transactions.py account migrate --yes` only when detect prints exactly `migrate`.
`partial` is a hard stop. On `clean` or `demo_only_at_root`, do not migrate and must not trigger migration.
Create accounts when appropriate with `python scripts/transactions.py account create <name>`.
On clean layout continue with the active/default account workflow.
Use /tmp extraction discipline for statement parsing. Use a temp-researcher for large broker files.
Use a batch confirmation gate before inserts. Do not immediately offer report generation after onboarding.
""",
        "transaction-management": """---
name: transaction-management
description: Route transaction updates through docs/transactions_agent_guidelines.md.
---
# Transaction management
Reference docs/transactions_agent_guidelines.md.
Canonical commands:
- `python scripts/transactions.py db add --json '<canonical-json>' --account <name>`
- `python scripts/transactions.py db import-csv --input <path> --account <name>`
- `python scripts/transactions.py db import-json --input <path> --account <name>`
- `python scripts/transactions.py verify --account <name>`
- `python scripts/transactions.py db stats --account <name>`
- `python scripts/transactions.py self-check`
Target Account Resolution: before any write, resolve the active account or default and include the resolved account name.
Before any write show parsed trades / cash flows, write plan, exact canonical JSON blob or /tmp JSON path,
resulting state preview, and SELL realized P&L when relevant.
Literal prompt: Confirm and write? (yes / no / edit).
Backup before write. After write run `python scripts/transactions.py verify --account <name>`.
Rollback from backup on verify failure.
Forbid SQL UPDATE / DELETE on ledger tables. Never directly edit open_lots or cash_balances.
""",
        "account-management": """---
name: account-management
description: Classify account commands by side effect and route to canonical docs.
---
# Account management
References: docs/onboarding_agent_guidelines.md, docs/transactions_agent_guidelines.md.
Read-only / safe:
- `python scripts/transactions.py account detect`
- `python scripts/transactions.py account list`
- `python scripts/transactions.py account --help`
Write-capable / gated:
- `python scripts/transactions.py account use <name>` writes accounts/.active and is gated.
- `python scripts/transactions.py account create <name>` scaffolds account files and is gated.
- `python scripts/transactions.py account migrate --yes` migrates legacy root layout and is allowed only after detect prints exactly migrate.
Run migration only when detect prints exactly migrate. partial is a hard stop.
For clean or demo_only_at_root, do not migrate and must not trigger migration.
Forbidden: destructive file surgery outside canonical scripts.
""",
        "split-asset-account": """---
name: split-asset-account
description: Safely split an asset class out of one ledger into another account.
---
# Split asset account
This skill is ledger migration. Reference docs/transactions_agent_guidelines.md.
1. Detect layout: `python scripts/transactions.py account detect`. List with `python scripts/transactions.py account list`. partial is a hard stop.
2. Resolve the source account from the user name, active account, or default. Dry-run is the default for `python scripts/split_asset_account.py`. Use --apply only after reviewing the JSON summary and verify_issues are empty.
3. After --apply, run `python scripts/transactions.py verify --account <source>` and `python scripts/transactions.py verify --account <target>`.
Backup `transactions.db.bak` before --apply.
Never edit derived balance tables directly. Rebuild via the canonical import/replay path.
""",
        "settings-management": """---
name: settings-management
description: Route SETTINGS.md edits through the documented diff-confirm workflow.
---
# Settings management
Reference docs/settings_agent_guidelines.md.
Detect the target account before reading or editing settings using account commands; use active account or default and do not guess the active account.
Bootstrap from SETTINGS.example.md only under the settings workflow.
Before confirmed edits run `cp accounts/<active>/SETTINGS.md accounts/<active>/SETTINGS.md.bak`.
Show proposed full content or unified diff. Require explicit same-turn yes.
Backup except first creation. Never invent strategy. Never store strategy outside SETTINGS.md.
""",
        "report-management": """---
name: report-management
description: Gate report generation through the canonical pipeline.
---
# Report management
This skill references docs/portfolio_report_agent_guidelines.md, every numbered file under
docs/portfolio_report_agent_guidelines/, docs/portfolio_report_agent_guidelines/07-investment-content-and-checklist.md,
and skills/investment-help/SKILL.md.
Route ad hoc non-HTML research to skills/investment-analysis/SKILL.md.
Select daily_report or portfolio_report and single account or total scope before Phase A; if scope is not named, resolve active/default account for single-account scope.
Use /tmp only with REPORT_RUN_DIR.
Run `python scripts/transactions.py account detect` before account-reading report scripts.
Run:
- `python scripts/fetch_prices.py --account <name> --output "$REPORT_RUN_DIR/prices.json"`
- `python scripts/fetch_history.py --account <name> --merge-into "$REPORT_RUN_DIR/prices.json"`
- `python scripts/transactions.py snapshot --account <name> --prices "$REPORT_RUN_DIR/prices.json" --output "$REPORT_RUN_DIR/report_snapshot.json"`
- `python scripts/validate_report_context.py --snapshot "$REPORT_RUN_DIR/report_snapshot.json" --context "$REPORT_RUN_DIR/report_context.json" --report-type <daily_report|portfolio_report>`
- `python scripts/generate_report.py --report-type <daily_report|portfolio_report> --account <name> --snapshot "$REPORT_RUN_DIR/report_snapshot.json" --context "$REPORT_RUN_DIR/report_context.json"`
Use `python scripts/fill_history_gap.py` only for structured history gaps. Do not use --allow-incomplete.
portfolio_report must not gather news, actions, events, research targets, or trading psychology.
Validate context with validate_report_context.py. After success run `rm -rf "$REPORT_RUN_DIR"`.
Demo reports use demo/transactions.db and demo/market_data_cache.db.
""",
        "investment-analysis": """---
name: investment-analysis
description: Route ad hoc investment analysis through the strategy-bound research contract.
---
# Investment analysis
This skill handles ad hoc research that is not an HTML report. Route HTML output to skills/report-management/SKILL.md.
Use docs/portfolio_report_agent_guidelines/07-investment-content-and-checklist.md for detailed PM-grade fields.
Do not edit SETTINGS.md or transactions.db, reports, ledgers, or account state.
Ad hoc research is account-bound by default; run `python scripts/transactions.py account detect`, resolve the active account, then read SETTINGS.md and the Investment Style And Strategy section plus portfolio/ledger context.
Use latest public information and browse when facts may have changed. If account context is missing, label generic/non-personalized research.
Output Bottom line first with size in pp of NAV.
Include Consensus, Variant, Anchor; if unavailable say unknown-consensus.
Include R:R and Kill criteria, portfolio fit, operating playbook, and final verdict.
Run a Reviewer pass before finalizing. Never fabricate consensus, citations, anchors, prices, holdings, or rails.
""",
        "context-economy": """---
name: context-economy
description: Enforce context drop for research-class phases.
---
# Context economy
This is the context hygiene gate. Follow docs/context_drop_protocol.md and docs/temp_researcher_contract.md.
Use it for phases with more than 5K tokens of raw tool output.
Delegate to a temp-researcher when needed.
Return only result_file, summary, audit.
Do not paste raw findings back into the parent context.
Artifacts live under /tmp and validate JSON with `jq . <path>`.
The parent reads artifacts lazily. No artifact, no drop.
If portfolio_report forbids news research, skip the phase rather than delegating.
""",
        "upgrade-management": """---
name: upgrade-management
description: Safely upgrade or update this repo without risking private portfolio data.
---
# Upgrade management
Upgrade code without overwriting private account data. Must not edit or delete SETTINGS.md or transactions.db.
Route migrations to skills/account-management/SKILL.md and optional demo smoke checks to skills/report-management/SKILL.md; respect demo/README.md isolation.
Inspect code with `git status --short` and `git remote -v`.
Also inspect `git branch --show-current` and `git describe --tags --exact-match`.
If tracked source files have uncommitted changes, do not pull.
Before account backup or checks run `python scripts/transactions.py account detect`.
partial is a hard stop. If detect says migrate, migration requires the account-management gate.
For clean or demo_only_at_root, do not migrate.
Create a backup and report its path when private artifacts exist.
Preserve the user's installation channel: Git branch install on main updates main, Git detached at a release tag moves to the latest stable release tag, and Release zip/archive install must stop; do not auto-update because it is an independent archive/zip copy.
Recommend Git for future updates.
Prefer the latest non-prerelease semantic-version tag.
Use a fast-forward-only update with `git fetch --tags --prune` and `git pull --ff-only`, or `git checkout <latest-stable-tag>` for tag installs.
Refresh dependencies with `python3 -m pip install --upgrade yfinance requests`.
Validate with `python scripts/validate_project_skills.py` and inspect with `python scripts/transactions.py account list`.
Report validation and smoke-check results.
""",
    }
    return fixtures[skill_key] + USER_FACING_EXECUTION_RULE


def write_fixture(root: Path, overrides: Mapping[str, str] | None = None) -> None:
    overrides = overrides or {}
    for skill_key, spec in EXPECTED_SKILLS.items():
        rel_path = Path(str(spec["path"]))
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(overrides.get(skill_key, positive_fixture_text(skill_key)), encoding="utf-8")


@dataclass(frozen=True)
class NegativeCase:
    name: str
    skill_key: str
    replacement: str
    expected_substring: str


def run_self_tests() -> None:
    positive_cases = 0
    negative_cases = [
        NegativeCase(
            "missing doc citation",
            "onboarding",
            positive_fixture_text("onboarding").replace("docs/onboarding_agent_guidelines.md", "docs/missing.md"),
            "required source-doc reference",
        ),
        NegativeCase(
            "unsafe skip confirmation wording",
            "transaction-management",
            positive_fixture_text("transaction-management") + "\nAgents may skip confirmation for small inserts.\n",
            "unsafe wording present: skip confirmation",
        ),
        NegativeCase(
            "ungated migrate --yes",
            "account-management",
            positive_fixture_text("account-management").replace(
                "is allowed only after detect prints exactly migrate.",
                "can run during account setup.",
            ).replace(
                "Run migration only when detect prints exactly migrate. partial is a hard stop.\nFor clean or demo_only_at_root, do not migrate and must not trigger migration.\n",
                "Run it when useful.\n",
            ),
            "migrate --yes",
        ),
        NegativeCase(
            "forbidden SQL mutation",
            "transaction-management",
            positive_fixture_text("transaction-management") + "\nIf needed, run SQL UPDATE on ledger tables.\n",
            "forbidden SQL/derived-table mutation language",
        ),
        NegativeCase(
            "transaction write missing confirmation backup verify",
            "transaction-management",
            """---
name: transaction-management
description: Bad transaction write skill.
---
Reference docs/transactions_agent_guidelines.md.
Use `python scripts/transactions.py db add --json '<canonical-json>' --account <name>`.
Use `python scripts/transactions.py db import-csv --input <path> --account <name>`.
Use `python scripts/transactions.py db import-json --input <path> --account <name>`.
Use `python scripts/transactions.py verify --account <name>`.
Use `python scripts/transactions.py db stats --account <name>`.
Use `python scripts/transactions.py self-check`.
""",
            "transaction write gate",
        ),
        NegativeCase(
            "settings write missing diff confirm",
            "settings-management",
            """---
name: settings-management
description: Bad settings write skill.
---
Reference docs/settings_agent_guidelines.md.
Use SETTINGS.md for settings. Bootstrap from SETTINGS.example.md.
Run `cp accounts/<active>/SETTINGS.md accounts/<active>/SETTINGS.md.bak`.
Detect active account with active account commands.
Never invent strategy. Never store strategy outside SETTINGS.md.
""",
            "settings write gate",
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="validate_project_skills_selftest_") as tmp:
        root = Path(tmp)
        write_fixture(root)
        positive_errors = validate_root(root)
        if positive_errors:
            raise SkillValidationFailed(
                [replace(error, path=f"self-test positive/{error.path}") for error in positive_errors]
            )
        positive_cases += 1

    for case in negative_cases:
        with tempfile.TemporaryDirectory(prefix="validate_project_skills_selftest_") as tmp:
            root = Path(tmp)
            write_fixture(root, {case.skill_key: case.replacement})
            errors = validate_root(root)
            rendered = "\n".join(error.render() for error in errors)
            if not errors:
                raise AssertionError(f"self-test negative case did not fail: {case.name}")
            if case.expected_substring.lower() not in rendered.lower():
                raise AssertionError(
                    f"self-test negative case {case.name!r} failed for the wrong reason.\n"
                    f"Expected substring: {case.expected_substring}\nErrors:\n{rendered}"
                )
    print(f"Self-test: PASS ({positive_cases} positive fixture, {len(negative_cases)} negative fixtures)")


def print_errors(errors: Sequence[ValidationError]) -> None:
    print(f"Project skill validation: FAIL ({len(errors)} issue{'s' if len(errors) != 1 else ''})")
    for error in errors:
        print(f"- {error.render()}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate project-local workflow skill contracts.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root to validate (default: cwd).")
    parser.add_argument("--self-test", action="store_true", help="Run built-in fixture self-tests only.")
    parser.add_argument("--skip-self-test", action="store_true", help="Validate repository without running built-in self-tests first.")
    args = parser.parse_args(argv)

    try:
        if args.self_test:
            run_self_tests()
            return 0
        if not args.skip_self_test:
            run_self_tests()
        errors = validate_root(args.root)
        if errors:
            print_errors(errors)
            return 1
        print("Project skill validation: PASS")
        return 0
    except (AssertionError, SkillValidationFailed) as exc:
        print(f"Self-test: FAIL — {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
