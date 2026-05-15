"""Account discovery and path-safety primitives for the local UI.

Every entry point that takes an account name from the network goes through
:func:`resolve_account_path`, which validates the name against a strict
regex and asserts the resolved path is under :data:`ACCOUNTS_ROOT`.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from scripts import account as account_cli

REPO_ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_ROOT = (REPO_ROOT / "accounts").resolve()

ACCOUNT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_MARKERS = ("SETTINGS.md", "ledger", "reports")
_SYNTHETIC_ACCOUNTS = frozenset({"_total"})
_ARCHIVE_DIR_NAME = ".archived"


class AccountAdminError(ValueError):
    """Expected account-management failure safe to return to the UI."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


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


def real_accounts() -> list[str]:
    """Return account names that can be actively managed by the user."""
    return [name for name in discover_accounts() if name not in _SYNTHETIC_ACCOUNTS]


def active_account() -> str | None:
    """Return the persisted active account pointer when it targets a real account."""
    active = account_cli.read_active_pointer()
    if active and active in real_accounts():
        return active
    return None


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
    selectable = [name for name in accounts if name not in _SYNTHETIC_ACCOUNTS]
    if not selectable:
        return None
    active = active_account()
    if active and active in selectable:
        return active
    if "default" in selectable:
        return "default"
    return selectable[0]


def account_summaries() -> list[dict[str, str | bool]]:
    """Return UI-ready metadata for all discovered accounts."""
    active = active_account()
    out: list[dict[str, str | bool]] = []
    for name in discover_accounts():
        out.append(
            {
                "name": name,
                "description": ""
                if name in _SYNTHETIC_ACCOUNTS
                else account_cli.read_account_description(name),
                "active": name == active,
                "synthetic": name in _SYNTHETIC_ACCOUNTS,
            }
        )
    return out


def _ensure_account_admin_layout() -> None:
    """Block writes when the account layout needs migration/reconciliation."""
    state = account_cli.detect_legacy_layout()
    if state == "partial":
        raise AccountAdminError(
            "account layout is partial; reconcile the legacy/accounts layout before editing accounts",
            status_code=409,
        )
    if state == "migrate":
        raise AccountAdminError(
            "legacy root account detected; migrate it before creating or editing accounts",
            status_code=409,
        )


def _validate_real_account_name(name: str, *, for_create: bool = False) -> None:
    if name in _SYNTHETIC_ACCOUNTS:
        raise AccountAdminError(f"{name!r} is a read-only aggregate, not a real account")
    try:
        account_cli.validate_account_name(name, for_create=for_create)
    except account_cli.AccountNameError as exc:
        raise AccountAdminError(str(exc)) from exc


def create_account(name: str, *, set_active: bool = False) -> dict[str, object]:
    """Create a new account scaffold through the canonical account helper."""
    _ensure_account_admin_layout()
    _validate_real_account_name(name, for_create=True)
    base = account_cli._accounts_dir() / name  # noqa: SLF001 - canonical dynamic root
    if base.exists():
        raise AccountAdminError(f"account already exists: {name}", status_code=409)

    paths = account_cli.create_account_scaffold(name)
    should_set_active = set_active or account_cli.read_active_pointer() is None
    if should_set_active:
        account_cli.write_active_pointer(name)
    return {
        "account": paths.name,
        "settings": str(paths.settings),
        "ledger": str(paths.ledger),
        "reports": str(paths.reports_dir),
        "active": should_set_active,
        "onboarding": "settings_draft",
    }


def set_active_account(name: str) -> dict[str, object]:
    """Persist the active account pointer for future CLI/UI runs."""
    _ensure_account_admin_layout()
    _validate_real_account_name(name)
    if name not in real_accounts():
        raise AccountAdminError(f"account does not exist: {name}", status_code=404)
    account_cli.write_active_pointer(name)
    return {"account": name, "active": True}


def rename_account(old_name: str, new_name: str) -> dict[str, object]:
    """Rename an account directory without changing its ledger/settings content."""
    _ensure_account_admin_layout()
    _validate_real_account_name(old_name)
    _validate_real_account_name(new_name, for_create=True)
    if old_name == new_name:
        raise AccountAdminError("new account name must be different")

    accounts_root = account_cli._accounts_dir()  # noqa: SLF001 - canonical dynamic root
    old_path = accounts_root / old_name
    new_path = accounts_root / new_name
    if not old_path.is_dir():
        raise AccountAdminError(f"account does not exist: {old_name}", status_code=404)
    if new_path.exists():
        raise AccountAdminError(f"account already exists: {new_name}", status_code=409)

    was_active = account_cli.read_active_pointer() == old_name
    old_path.rename(new_path)
    try:
        if was_active:
            account_cli.write_active_pointer(new_name)
    except Exception:
        # Keep the filesystem and pointer consistent if the pointer write fails.
        try:
            new_path.rename(old_path)
        finally:
            raise
    return {"account": new_name, "old_account": old_name, "active": was_active}


def archive_account(name: str) -> dict[str, object]:
    """Reversibly remove an account from the active list by moving it aside."""
    _ensure_account_admin_layout()
    _validate_real_account_name(name)
    accounts = real_accounts()
    if name not in accounts:
        raise AccountAdminError(f"account does not exist: {name}", status_code=404)
    if account_cli.read_active_pointer() == name:
        raise AccountAdminError("set another active account before archiving this one", status_code=409)
    if len(accounts) <= 1:
        raise AccountAdminError("cannot archive the last account", status_code=409)

    accounts_root = account_cli._accounts_dir()  # noqa: SLF001 - canonical dynamic root
    src = accounts_root / name
    archive_root = accounts_root / _ARCHIVE_DIR_NAME
    archive_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = archive_root / f"{name}-{stamp}"
    suffix = 1
    while dst.exists():
        suffix += 1
        dst = archive_root / f"{name}-{stamp}-{suffix}"
    shutil.move(str(src), str(dst))
    return {"account": name, "archived": True, "archive_path": str(dst)}
