from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_mode_policy import default_report_filename  # noqa: E402


def test_default_output_names_encode_type_and_scope():
    assert default_report_filename("2026-05-03_2130", "daily_report", "single_account").endswith("_single_account_daily_report.html")
    assert default_report_filename("2026-05-03_2130", "portfolio_report", "total_account").endswith("_total_account_portfolio_report.html")


def test_generate_report_requires_report_type_for_render_path():
    proc = subprocess.run(
        [sys.executable, "scripts/generate_report.py", "--snapshot", "/tmp/missing.json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "report_type is required" in proc.stderr


def test_cli_help_mentions_report_type_and_axis_naming():
    proc = subprocess.run(
        [sys.executable, "scripts/generate_report.py", "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "--report-type" in proc.stdout
    assert "single_account|total_account" in proc.stdout
