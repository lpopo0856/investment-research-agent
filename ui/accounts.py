"""Account discovery and path-safety primitives for the local UI.

Every entry point that takes an account name from the network goes through
:func:`resolve_account_path`, which validates the name against a strict
regex and asserts the resolved path is under :data:`ACCOUNTS_ROOT`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_ROOT = (REPO_ROOT / "accounts").resolve()

ACCOUNT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_MARKERS = ("SETTINGS.md", "ledger", "reports")


def discover_accounts() -> list[str]:
    """Return sorted account names under :data:`ACCOUNTS_ROOT`.

    An entry is treated as an account if it is a directory and contains at
    least one of ``SETTINGS.md``, ``ledger/``, or ``reports/``. The OR rule
    matters so reports-only aggregate accounts like ``_total`` are listed.
    """
    if not ACCOUNTS_ROOT.is_dir():
        return []

    names: list[str] = []
    for entry in ACCOUNTS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        if not ACCOUNT_NAME_RE.match(entry.name):
            continue
        if any((entry / marker).exists() for marker in _MARKERS):
            names.append(entry.name)
    names.sort()
    return names


def resolve_account_path(name: str) -> Path:
    """Validate ``name`` and return the absolute account directory path.

    Raises :class:`ValueError` on any name that fails the regex or escapes
    :data:`ACCOUNTS_ROOT`.
    """
    if not isinstance(name, str) or not ACCOUNT_NAME_RE.match(name):
        raise ValueError(f"invalid account name: {name!r}")

    candidate = (ACCOUNTS_ROOT / name).resolve()
    try:
        common = os.path.commonpath([str(candidate), str(ACCOUNTS_ROOT)])
    except ValueError as exc:
        raise ValueError(f"invalid account path for {name!r}: {exc}") from exc
    if Path(common) != ACCOUNTS_ROOT:
        raise ValueError(f"account path escapes accounts root: {name!r}")
    if not candidate.is_dir():
        raise ValueError(f"account directory does not exist: {name!r}")
    return candidate


def default_account(accounts: list[str]) -> str | None:
    """Pick the default-selected account on first load."""
    if not accounts:
        return None
    if "default" in accounts:
        return "default"
    return accounts[0]
