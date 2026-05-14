"""Tests for ui.accounts — regex, discovery, path safety, default selection."""

import pytest

from ui.accounts import ACCOUNT_NAME_RE, default_account, discover_accounts, resolve_account_path


# ---------------------------------------------------------------------------
# ACCOUNT_NAME_RE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "..",
    "/",
    "",
    "default; rm -rf",
    "a/b",
    "a.b",
    "a b",
])
def test_account_name_re_rejects(name):
    assert ACCOUNT_NAME_RE.match(name) is None


@pytest.mark.parametrize("name", [
    "default",
    "_total",
    "crypto",
    "abc-123",
])
def test_account_name_re_accepts(name):
    assert ACCOUNT_NAME_RE.match(name) is not None


# ---------------------------------------------------------------------------
# discover_accounts
# ---------------------------------------------------------------------------

def test_discover_accounts_contains_expected():
    accounts = discover_accounts()
    assert isinstance(accounts, list)
    assert accounts == sorted(accounts), "accounts must be sorted"
    for expected in ("_total", "crypto", "default"):
        assert expected in accounts, f"expected {expected!r} in discovered accounts"


def test_discover_accounts_total_has_only_reports():
    """_total has only reports/ (no SETTINGS.md/ledger) — OR rule must include it."""
    accounts = discover_accounts()
    assert "_total" in accounts


# ---------------------------------------------------------------------------
# resolve_account_path
# ---------------------------------------------------------------------------

def test_resolve_account_path_rejects_traversal():
    with pytest.raises(ValueError):
        resolve_account_path("../etc")


def test_resolve_account_path_rejects_slash():
    with pytest.raises(ValueError):
        resolve_account_path("/etc/passwd")


def test_resolve_account_path_rejects_dotdot():
    with pytest.raises(ValueError):
        resolve_account_path("..")


def test_resolve_account_path_valid_returns_path():
    path = resolve_account_path("default")
    assert path.is_dir()
    assert path.name == "default"


# ---------------------------------------------------------------------------
# default_account
# ---------------------------------------------------------------------------

def test_default_account_prefers_default_name():
    assert default_account(["a", "b", "default", "z"]) == "default"


def test_default_account_falls_back_to_first():
    assert default_account(["a", "b"]) == "a"


def test_default_account_empty_returns_none():
    assert default_account([]) is None
