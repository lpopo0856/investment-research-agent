"""Shared UI test fixtures."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_accounts_root(monkeypatch, tmp_path):
    """Run UI tests against tracked fixture accounts, not private local data."""

    source = Path(__file__).parent / "fixtures" / "accounts"
    accounts_root = tmp_path / "accounts"
    shutil.copytree(source, accounts_root)

    import ui.accounts as accounts

    monkeypatch.setattr(accounts, "ACCOUNTS_ROOT", accounts_root.resolve())
    yield accounts_root.resolve()
