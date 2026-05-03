from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_report as gr  # noqa: E402


def _snapshot():
    return SimpleNamespace(
        today="2026-05-03",
        base_currency="USD",
        aggregates={},
        prices={},
        config={},
        totals={"total_assets": 0.0, "invested": 0.0, "cash": 0.0, "pnl": 0.0},
        book_pacing={},
        risk_heat=[],
    )


def _settings():
    return SimpleNamespace(locale="en")


def _install_markers(monkeypatch):
    marker_fns = {
        "render_masthead": "MASTHEAD",
        "render_alerts": "ALERTS",
        "render_today_summary": "TODAY_SUMMARY",
        "render_dashboard": "DASHBOARD",
        "render_profit_panel": "PROFIT_PANEL",
        "render_report_accuracy": "REPORT_ACCURACY",
        "render_performance_attribution": "PERFORMANCE_ATTRIBUTION",
        "render_trade_quality": "TRADE_QUALITY",
        "render_discipline_check": "DISCIPLINE_CHECK",
        "render_trading_psychology": "TRADING_PSYCHOLOGY",
        "render_allocation_and_weight": "ALLOCATION",
        "render_pnl_ranking": "PNL_RANKING",
        "render_holding_period": "HOLDING_PERIOD",
        "render_theme_sector": "THEME_SECTOR",
        "render_news": "NEWS",
        "render_events": "EVENTS",
        "render_high_risk_opp": "HIGH_RISK_OPP",
        "render_adjustments": "ADJUSTMENTS",
        "render_actions": "ACTIONS",
        "render_sources": "SOURCES",
    }
    for name, marker in marker_fns.items():
        monkeypatch.setattr(gr, name, lambda *args, _marker=marker, **kwargs: _marker)

    def holdings(*args, hide_action_column=False, **kwargs):
        return "HOLDINGS_WITHOUT_ACTION" if hide_action_column else "HOLDINGS_WITH_ACTION"

    monkeypatch.setattr(gr, "render_holdings_table", holdings)


def _render(monkeypatch, report_type, account_scope):
    _install_markers(monkeypatch)
    return gr.render_html(_snapshot(), {}, "", _settings(), report_type=report_type, account_scope=account_scope)


def test_single_account_daily_render_matrix(monkeypatch):
    html = _render(monkeypatch, "daily_report", "single_account")
    for marker in ["ALERTS", "TODAY_SUMMARY", "NEWS", "EVENTS", "HIGH_RISK_OPP", "ADJUSTMENTS", "ACTIONS", "TRADING_PSYCHOLOGY", "HOLDINGS_WITH_ACTION"]:
        assert marker in html
    for marker in ["PROFIT_PANEL", "PERFORMANCE_ATTRIBUTION", "DISCIPLINE_CHECK", "HOLDING_PERIOD", "PNL_RANKING"]:
        assert marker not in html


def test_single_account_portfolio_render_matrix(monkeypatch):
    html = _render(monkeypatch, "portfolio_report", "single_account")
    for marker in ["HOLDINGS_WITHOUT_ACTION", "PROFIT_PANEL", "PNL_RANKING", "HOLDING_PERIOD"]:
        assert marker in html
    for marker in ["ALERTS", "TODAY_SUMMARY", "NEWS", "EVENTS", "HIGH_RISK_OPP", "ADJUSTMENTS", "ACTIONS", "TRADING_PSYCHOLOGY", "HOLDINGS_WITH_ACTION"]:
        assert marker not in html


def test_total_daily_render_matrix(monkeypatch):
    html = _render(monkeypatch, "daily_report", "total_account")
    for marker in ["PROFIT_PANEL", "PERFORMANCE_ATTRIBUTION", "DISCIPLINE_CHECK", "HOLDING_PERIOD", "PNL_RANKING", "ALERTS", "ACTIONS", "TRADING_PSYCHOLOGY", "HOLDINGS_WITH_ACTION"]:
        assert marker not in html
    assert "HOLDINGS_WITHOUT_ACTION" in html


def test_total_portfolio_render_matrix(monkeypatch):
    html = _render(monkeypatch, "portfolio_report", "total_account")
    for marker in ["ALERTS", "TODAY_SUMMARY", "NEWS", "EVENTS", "HIGH_RISK_OPP", "ADJUSTMENTS", "ACTIONS", "TRADING_PSYCHOLOGY", "HOLDINGS_WITH_ACTION"]:
        assert marker not in html
    assert "HOLDINGS_WITHOUT_ACTION" in html
