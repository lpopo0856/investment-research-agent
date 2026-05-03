from __future__ import annotations

import copy
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from test_validate_report_context_horizon_v1 import _context, _snapshot  # noqa: E402
from validate_report_context import validate_report_context  # noqa: E402


def _errors(ctx, snap=None, *, report_type="daily_report", account_scope="single_account"):
    return validate_report_context(ctx, snap or _snapshot(), report_type=report_type, account_scope=account_scope)


def test_single_account_daily_remains_strict_for_included_editorial_fields():
    ctx = _context()
    for key in [
        "today_summary",
        "adjustments",
        "actions",
        "trading_psychology",
        "research_coverage",
        "reviewer_pass",
    ]:
        candidate = copy.deepcopy(ctx)
        candidate.pop(key, None)
        errors = _errors(candidate)
        assert errors, f"expected missing {key} to fail for single-account daily"


def test_single_account_portfolio_accepts_omitted_skipped_sections():
    ctx = _context()
    for key in [
        "today_summary",
        "news",
        "events",
        "adjustments",
        "actions",
        "high_opps",
        "trading_psychology",
        "research_coverage",
    ]:
        ctx.pop(key, None)
    ctx["reviewer_pass"]["reviewed_sections"] = ["strategy_readout", "theme_sector"]
    assert _errors(ctx, report_type="portfolio_report") == []


def test_total_account_modes_do_not_require_strategy_dependent_editorial_fields():
    ctx = {"title": "math-only total"}
    assert _errors(ctx, report_type="daily_report", account_scope="total_account") == []
    assert _errors(ctx, report_type="portfolio_report", account_scope="total_account") == []


def test_included_portfolio_sources_and_theme_still_fail_when_missing():
    ctx = _context()
    for key in ["theme_sector_html", "theme_sector_audit", "strategy_readout", "data_gaps", "reviewer_pass"]:
        ctx.pop(key, None)
    errors = _errors(ctx, report_type="portfolio_report")
    assert any("theme_sector" in err for err in errors)
    assert any("strategy_readout" in err for err in errors)
    assert any("data_gaps" in err for err in errors)
    assert any("reviewer_pass" in err for err in errors)
