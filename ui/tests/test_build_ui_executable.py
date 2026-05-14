"""Tests for the PyInstaller command wrapper."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from scripts import build_ui_executable


def test_build_command_is_onefile_and_excludes_user_data(tmp_path):
    args = Namespace(
        name="investments-ui",
        distpath=tmp_path / "dist",
        workpath=tmp_path / "build",
        specpath=tmp_path / "spec",
        print_command=True,
    )

    cmd = build_ui_executable.build_command(args)
    joined = " ".join(cmd)

    assert "--onefile" in cmd
    assert "--add-data" in cmd
    assert "ui/static" in joined
    assert "scripts/run_packaged_ui.py" in joined
    assert "accounts" not in [Path(part).name for part in cmd]
    assert "market_data_cache" not in joined
