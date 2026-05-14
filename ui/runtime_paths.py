"""Runtime path helpers for source checkouts and frozen UI builds.

The development UI keeps using the repository checkout by default so the
existing tests and local workflow remain unchanged. A frozen executable (or a
test that sets ``INVESTMENTS_USE_APP_DATA=1`` / ``INVESTMENTS_DATA_ROOT``)
stores mutable files under a per-user app-data directory instead.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_data_path

APP_NAME = "Investments"
APP_AUTHOR = "Investments"

_ENV_DATA_ROOT = "INVESTMENTS_DATA_ROOT"
_ENV_ACCOUNTS_ROOT = "INVESTMENTS_ACCOUNTS_ROOT"
_ENV_USE_APP_DATA = "INVESTMENTS_USE_APP_DATA"


def is_frozen() -> bool:
    """Return ``True`` when running from a PyInstaller-style frozen app."""

    return bool(getattr(sys, "frozen", False))


def source_root() -> Path:
    """Return the repository/source root in development mode."""

    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    """Return the read-only resource root for the current runtime."""

    return Path(getattr(sys, "_MEIPASS", source_root())).resolve()


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def use_app_data_by_default() -> bool:
    """Whether mutable data should default to OS app-data storage."""

    return is_frozen() or os.environ.get(_ENV_USE_APP_DATA) == "1"


def app_data_root(*, ensure: bool = True) -> Path:
    """Return the mutable application data root.

    Precedence:
    1. ``INVESTMENTS_DATA_ROOT`` explicit override
    2. OS app-data directory for frozen builds or explicit app-data tests
    3. Source root for normal development checkouts
    """

    root = _env_path(_ENV_DATA_ROOT)
    if root is None:
        if use_app_data_by_default():
            root = user_data_path(APP_NAME, APP_AUTHOR, ensure_exists=ensure)
        else:
            root = source_root()
    if ensure:
        root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def accounts_root(*, ensure: bool = True) -> Path:
    """Return the root directory containing account folders."""

    root = _env_path(_ENV_ACCOUNTS_ROOT) or (app_data_root(ensure=ensure) / "accounts")
    if ensure:
        root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def resource_path(*parts: str) -> Path:
    """Return a bundled read-only resource path."""

    return bundle_root().joinpath(*parts)


def terminal_working_dir(*, ensure: bool = True) -> Path:
    """Return the working directory for embedded optional terminal sessions."""

    return app_data_root(ensure=ensure) if use_app_data_by_default() else source_root()


def bootstrap_local_data() -> dict[str, str]:
    """Create the empty mutable workspace required by first-run packaged apps."""

    data_root = app_data_root(ensure=True)
    accounts = accounts_root(ensure=True)
    cache = data_root / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return {
        "data_root": str(data_root),
        "accounts_root": str(accounts),
        "cache_root": str(cache),
    }
