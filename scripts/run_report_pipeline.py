#!/usr/bin/env python3
"""Run the canonical single-account portfolio_report pipeline safely.

The wrapper removes shell-state hazards from agent runs: it owns the temporary
run directory, executes the snapshot-first pipeline in order, validates context,
renders HTML, runs self-containment checks, and deletes successful intermediates.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from account import resolve_account  # noqa: E402
from check_report_html import check_html_file  # noqa: E402
from report_mode_policy import describe_policy  # noqa: E402


WROTE_RE = re.compile(r"Wrote\s+(?P<path>/.+?\.html)\b")
FETCH_PRICES_TIMEOUT_SEC = 5 * 60
FETCH_HISTORY_TIMEOUT_SEC = 5 * 60


def _run(
    cmd: List[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
        timeout=timeout,
    )


def _print_completed(completed: subprocess.CompletedProcess[str]) -> None:
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)


def _extract_report_path(output: str) -> Optional[Path]:
    match = WROTE_RE.search(output)
    if not match:
        return None
    return Path(match.group("path"))


def run_single_account_portfolio_report(*, account: str, keep_run_dir: bool = False) -> Path:
    detect = _run([sys.executable, "scripts/transactions.py", "account", "detect"])
    detector_state = detect.stdout.strip()
    _print_completed(detect)
    if detector_state in {"partial", "migrate"}:
        raise RuntimeError(f"account layout state {detector_state!r} must be reconciled before report generation")
    if detector_state not in {"clean", "demo_only_at_root"}:
        raise RuntimeError(f"unexpected account layout state: {detector_state!r}")

    account_paths = resolve_account(argparse.Namespace(account=account, db=None, settings=None))
    policy = describe_policy("portfolio_report", "single_account")
    if policy["live_research_required"]:
        raise RuntimeError("portfolio_report unexpectedly requires live research")

    run_dir = Path(tempfile.mkdtemp(prefix="investments_portfolio_report_", dir="/tmp"))
    success = False
    try:
        prices = run_dir / "prices.json"
        snapshot = run_dir / "report_snapshot.json"
        context = run_dir / "report_context.json"

        for completed in [
            _run(
                [
                    sys.executable,
                    "scripts/fetch_prices.py",
                    "--account",
                    account,
                    "--output",
                    str(prices),
                ],
                timeout=FETCH_PRICES_TIMEOUT_SEC,
            ),
            _run(
                [
                    sys.executable,
                    "scripts/fetch_history.py",
                    "--account",
                    account,
                    "--merge-into",
                    str(prices),
                ],
                timeout=FETCH_HISTORY_TIMEOUT_SEC,
            ),
            _run(
                [
                    sys.executable,
                    "scripts/transactions.py",
                    "snapshot",
                    "--account",
                    account,
                    "--prices",
                    str(prices),
                    "--output",
                    str(snapshot),
                ]
            ),
            _run(
                [
                    sys.executable,
                    "scripts/build_portfolio_report_context.py",
                    "--snapshot",
                    str(snapshot),
                    "--settings",
                    str(account_paths.settings),
                    "--output",
                    str(context),
                ]
            ),
            _run(
                [
                    sys.executable,
                    "scripts/validate_report_context.py",
                    "--snapshot",
                    str(snapshot),
                    "--context",
                    str(context),
                    "--report-type",
                    "portfolio_report",
                    "--account-scope",
                    "single_account",
                ]
            ),
        ]:
            _print_completed(completed)

        render = _run(
            [
                sys.executable,
                "scripts/generate_report.py",
                "--report-type",
                "portfolio_report",
                "--account",
                account,
                "--snapshot",
                str(snapshot),
                "--context",
                str(context),
            ]
        )
        _print_completed(render)
        report_path = _extract_report_path(render.stdout)
        if report_path is None:
            raise RuntimeError("renderer did not print an output HTML path")

        self_check = _run([sys.executable, "scripts/generate_report.py", "--self-check"])
        _print_completed(self_check)
        locale = json.loads(snapshot.read_text(encoding="utf-8")).get("settings", {}).get("locale")
        errors = check_html_file(report_path, require_lang=locale)
        if errors:
            raise RuntimeError("rendered HTML failed checks: " + "; ".join(errors))

        context_data = json.loads(context.read_text(encoding="utf-8"))
        forbidden = set(policy["forbidden_context_keys"]).intersection(context_data)
        if forbidden:
            raise RuntimeError(f"portfolio_report context contains forbidden keys: {sorted(forbidden)}")

        success = True
        print(f"OK: wrote {report_path}")
        return report_path
    finally:
        if success and not keep_run_dir:
            shutil.rmtree(run_dir)
            print(f"Cleaned temporary report run directory: {run_dir}")
        elif not success:
            print(f"Kept failed report run directory for debugging: {run_dir}", file=sys.stderr)
        else:
            print(f"Kept report run directory: {run_dir}")


def _cli(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-type", choices=["portfolio_report"], default="portfolio_report")
    parser.add_argument("--account", default="default")
    parser.add_argument("--keep-run-dir", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _cli(argv)
    try:
        run_single_account_portfolio_report(account=args.account, keep_run_dir=args.keep_run_dir)
    except subprocess.CalledProcessError as exc:
        _print_completed(exc)
        return exc.returncode or 1
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
