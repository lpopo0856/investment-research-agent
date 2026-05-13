#!/usr/bin/env python3
"""Static SQLite quarantine validator.

The final Markdown-ledger architecture allows SQLite only inside a small
legacy-import quarantine.  This validator is intentionally conservative and
machine-readable: ``final`` mode fails any runtime/documentation SQLite
reference outside the exact allowlist, while ``transition`` mode preserves a
compatibility allowlist for migration/import/archive surfaces still under audit.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


FINAL_ALLOWLIST: Dict[str, str] = {
    "scripts/legacy_sqlite_import.py": "quarantined legacy SQLite reader/converter",
    "tests/fixtures/legacy_sqlite_*": "legacy SQLite fixture builders/data only",
    "tests/test_legacy_sqlite_import*.py": "legacy importer tests only",
    "scripts/validate_no_sqlite.py": "static validator implementation pattern definitions only",
    "docs/migration_flow_agent_guidelines.md": "legacy/import/archive workflow references",
    "skills/migration-flow/SKILL.md": "migration gate wording only",
    "accounts/*/ledger/LEDGER_STATE.json": "account-local migration state/audit evidence only",
    "accounts/*/ledger/migrations/**": "account-local migration audit evidence only",
    "accounts/*/ledger/migrations/**/*": "account-local migration audit evidence only",
    "accounts/*/ledger/archive/legacy-sqlite/**": "archived legacy SQLite evidence only",
    "accounts/*/ledger/archive/legacy-sqlite/**/*": "archived legacy SQLite evidence only",
}

TRANSITION_EXTRA_ALLOWLIST: Dict[str, str] = {
    "scripts/transactions.py": "Markdown runtime with legacy-named db compatibility and migration evidence strings",
    "scripts/account.py": "account scaffold/resolver compatibility references",
    "scripts/fetch_history.py": "market-data cache compatibility references",
    "scripts/fetch_prices.py": "legacy-named ledger path compatibility references",
    "scripts/fill_history_gap.py": "market-cache compatibility references",
    "scripts/report_archive.py": "report archive compatibility references",
    "scripts/split_asset_account.py": "split workflow legacy-named path compatibility references",
    "scripts/portfolio_snapshot.py": "snapshot legacy-named path compatibility references",
    "scripts/generate_report.py": "report archive compatibility references",
    "scripts/validate_project_skills.py": "skill validation fixtures include legacy quarantine wording",
    "docs/*.md": "docs compatibility references under audit",
    "docs/**/*.md": "docs compatibility references under audit",
    "AGENTS.md": "safety-floor legacy compatibility references under audit",
    "skills/**/*.md": "skill compatibility references under audit",
    "tests/**/*.py": "tests and fixtures for compatibility/quarantine",
    "tests/*.py": "tests and fixtures for compatibility/quarantine",
    "tests/**/*.sh": "shell smokes for compatibility/quarantine",
    "tests/*.sh": "shell smokes for compatibility/quarantine",
    "demo/**/*.md": "demo docs use legacy-named --db path override",
    "demo/*.md": "demo docs use legacy-named --db path override",
    "demo/**/*.py": "demo scripts use legacy-named --db path override",
    "demo/*.py": "demo scripts use legacy-named --db path override",
}

PATTERNS: Sequence[tuple[str, re.Pattern[str]]] = (
    ("sqlite_import", re.compile(r"\bimport\s+sqlite3\b")),
    ("sqlite_api", re.compile(r"\bsqlite3\.")),
    ("transactions_db", re.compile(r"\btransactions\.db\b")),
    ("market_data_cache_db", re.compile(r"\bmarket_data_cache\.db\b")),
    ("demo_db_cli", re.compile(r"--db\s+demo/transactions\.db")),
    ("sql_table_transactions", re.compile(r"\b(?:CREATE|INSERT\s+INTO|UPDATE|DELETE\s+FROM|FROM)\s+transactions\b", re.I)),
    ("sql_table_lots", re.compile(r"\b(?:CREATE|INSERT\s+INTO|UPDATE|DELETE\s+FROM|FROM)\s+sell_lot_consumption\b", re.I)),
    ("sql_table_open_lots", re.compile(r"\b(?:CREATE|INSERT\s+INTO|UPDATE|DELETE\s+FROM|FROM)\s+open_lots\b", re.I)),
    ("sql_table_cash_balances", re.compile(r"\b(?:CREATE|INSERT\s+INTO|UPDATE|DELETE\s+FROM|FROM)\s+cash_balances\b", re.I)),
)

SCAN_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".sh"}
EXCLUDED_PARTS = {
    ".git",
    ".omx",
    ".omc",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "reports",
    ".pre-migrate-backup",
}
EXCLUDED_FILES: set[str] = set()


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    excerpt: str
    allowed: bool
    allow_reason: str | None = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "kind": self.kind,
            "excerpt": self.excerpt,
            "allowed": self.allowed,
            "allow_reason": self.allow_reason,
        }


def _path_matches(rel: str, pattern: str) -> bool:
    # Path.match handles ** and * while keeping the allowlist machine-readable.
    return Path(rel).match(pattern)


def _allow_reason(rel: str, allowlist: Dict[str, str]) -> str | None:
    for pattern, reason in allowlist.items():
        if _path_matches(rel, pattern):
            return reason
    return None


def iter_scan_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in EXCLUDED_PARTS for part in rel_parts):
            continue
        if path.relative_to(root).as_posix() in EXCLUDED_FILES:
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        yield path


def scan_file(path: Path, *, root: Path, allowlist: Dict[str, str]) -> List[Finding]:
    rel = path.relative_to(root).as_posix()
    reason = _allow_reason(rel, allowlist)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    findings: List[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in PATTERNS:
            if not pattern.search(line):
                continue
            excerpt = line.strip()
            findings.append(
                Finding(
                    path=rel,
                    line=line_no,
                    kind=kind,
                    excerpt=excerpt[:240],
                    allowed=reason is not None,
                    allow_reason=reason,
                )
            )
    return findings


def run_validation(*, root: Path, mode: str = "final") -> Dict[str, object]:
    if mode not in {"transition", "final"}:
        raise ValueError("mode must be 'transition' or 'final'")
    root = root.resolve()
    allowlist = dict(FINAL_ALLOWLIST)
    if mode == "transition":
        allowlist.update(TRANSITION_EXTRA_ALLOWLIST)
    findings: List[Finding] = []
    for path in iter_scan_files(root):
        findings.extend(scan_file(path, root=root, allowlist=allowlist))
    violations = [finding for finding in findings if not finding.allowed]
    return {
        "schema": "investment-ledger-no-sqlite-validation/v1",
        "mode": mode,
        "root": str(root),
        "ok": not violations,
        "allowlist": allowlist,
        "finding_count": len(findings),
        "violation_count": len(violations),
        "violations": [finding.as_dict() for finding in violations],
        "allowed_findings": [finding.as_dict() for finding in findings if finding.allowed],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path.cwd(), type=Path)
    parser.add_argument("--mode", choices=("transition", "final"), default="final")
    args = parser.parse_args(argv)
    result = run_validation(root=args.root, mode=args.mode)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
