import argparse
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_report_pipeline  # noqa: E402


def test_fetch_prices_pipeline_step_has_five_minute_timeout(monkeypatch):
    calls = []

    def fake_run(cmd, *, cwd=run_report_pipeline.REPO_ROOT, timeout=None):
        calls.append((cmd, timeout))
        if cmd[:3] == [sys.executable, "scripts/transactions.py", "account"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="clean\n", stderr="")
        if cmd[:2] == [sys.executable, "scripts/fetch_prices.py"]:
            raise RuntimeError("stop after fetch_prices")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(run_report_pipeline, "_run", fake_run)
    monkeypatch.setattr(
        run_report_pipeline,
        "resolve_account",
        lambda _args: argparse.Namespace(settings=Path("/tmp/test-settings.md")),
    )
    monkeypatch.setattr(
        run_report_pipeline,
        "describe_policy",
        lambda *_args: {"live_research_required": False},
    )

    with pytest.raises(RuntimeError, match="stop after fetch_prices"):
        run_report_pipeline.run_single_account_portfolio_report(account="default")

    fetch_price_calls = [
        timeout
        for cmd, timeout in calls
        if cmd[:2] == [sys.executable, "scripts/fetch_prices.py"]
    ]
    assert fetch_price_calls == [300]


def test_fetch_history_pipeline_step_has_five_minute_timeout(monkeypatch):
    calls = []

    def fake_run(cmd, *, cwd=run_report_pipeline.REPO_ROOT, timeout=None):
        calls.append((cmd, timeout))
        if cmd[:3] == [sys.executable, "scripts/transactions.py", "account"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="clean\n", stderr="")
        if cmd[:2] == [sys.executable, "scripts/fetch_history.py"]:
            raise RuntimeError("stop after fetch_history")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(run_report_pipeline, "_run", fake_run)
    monkeypatch.setattr(
        run_report_pipeline,
        "resolve_account",
        lambda _args: argparse.Namespace(settings=Path("/tmp/test-settings.md")),
    )
    monkeypatch.setattr(
        run_report_pipeline,
        "describe_policy",
        lambda *_args: {"live_research_required": False},
    )

    with pytest.raises(RuntimeError, match="stop after fetch_history"):
        run_report_pipeline.run_single_account_portfolio_report(account="default")

    fetch_history_calls = [
        timeout
        for cmd, timeout in calls
        if cmd[:2] == [sys.executable, "scripts/fetch_history.py"]
    ]
    assert fetch_history_calls == [300]
