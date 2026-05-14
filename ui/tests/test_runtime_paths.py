"""Tests for source/frozen runtime path selection and first-run bootstrap."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_bootstrap_uses_env_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("INVESTMENTS_DATA_ROOT", str(tmp_path / "app-data"))

    import ui.runtime_paths as runtime_paths

    importlib.reload(runtime_paths)
    paths = runtime_paths.bootstrap_local_data()

    assert Path(paths["data_root"]) == (tmp_path / "app-data").resolve()
    assert Path(paths["accounts_root"]).is_dir()
    assert Path(paths["cache_root"]).is_dir()
    assert Path(paths["accounts_root"]).parent == Path(paths["data_root"])


def test_accounts_root_honors_env_override(monkeypatch, tmp_path):
    accounts_dir = tmp_path / "custom-accounts"
    monkeypatch.setenv("INVESTMENTS_ACCOUNTS_ROOT", str(accounts_dir))

    import ui.runtime_paths as runtime_paths

    importlib.reload(runtime_paths)
    assert runtime_paths.accounts_root() == accounts_dir.resolve()
    assert accounts_dir.is_dir()
