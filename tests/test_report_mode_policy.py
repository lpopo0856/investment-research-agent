from __future__ import annotations

import pytest

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_mode_policy import (  # noqa: E402
    TOTAL_ACCOUNT_SKIPPED_RENDERERS,
    default_report_filename,
    effective_skipped_renderers,
    hide_holdings_action_column,
    normalize_report_type,
)


def test_daily_single_skips_exact_daily_math_sections():
    assert effective_skipped_renderers("daily_report", "single_account") == frozenset({
        "render_profit_panel",
        "render_performance_attribution",
        "render_discipline_check",
        "render_holding_period",
        "render_pnl_ranking",
    })


def test_portfolio_single_skips_exact_daily_editorial_sections():
    assert effective_skipped_renderers("portfolio_report", "single_account") == frozenset({
        "render_alerts",
        "render_today_summary",
        "render_trading_psychology",
        "render_news",
        "render_events",
        "render_high_risk_opp",
        "render_adjustments",
        "render_actions",
    })


def test_total_scope_adds_total_overlay_to_report_type_skips():
    single = effective_skipped_renderers("daily_report", "single_account")
    total = effective_skipped_renderers("daily_report", "total_account")
    assert single < total
    assert TOTAL_ACCOUNT_SKIPPED_RENDERERS <= total


@pytest.mark.parametrize(
    ("report_type", "scope", "expected"),
    [
        ("daily_report", "single_account", False),
        ("portfolio_report", "single_account", True),
        ("daily_report", "total_account", True),
        ("portfolio_report", "total_account", True),
    ],
)
def test_holdings_action_column_policy(report_type, scope, expected):
    assert hide_holdings_action_column(report_type, scope) is expected


def test_default_report_filename_encodes_both_axes():
    ts = "2026-05-03_2130"
    assert default_report_filename(ts, "daily_report", "single_account") == f"{ts}_single_account_daily_report.html"
    assert default_report_filename(ts, "portfolio_report", "single_account") == f"{ts}_single_account_portfolio_report.html"
    assert default_report_filename(ts, "daily_report", "total_account") == f"{ts}_total_account_daily_report.html"
    assert default_report_filename(ts, "portfolio_report", "total_account") == f"{ts}_total_account_portfolio_report.html"


@pytest.mark.parametrize("value", [None, "", "total_report", "daily"])
def test_report_type_is_required_and_strict(value):
    with pytest.raises(ValueError):
        normalize_report_type(value)  # type: ignore[arg-type]
