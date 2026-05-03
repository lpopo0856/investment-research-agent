"""Shared report type / account scope policy for HTML reports.

The report taxonomy has two independent axes:

* report_type: content shape (``daily_report`` or ``portfolio_report``)
* account_scope: input aggregation (``single_account`` or ``total_account``)

Both renderer and validator import this module so skipped sections, validation
requirements, holdings Action-column behavior, and default filenames cannot drift.
"""

from __future__ import annotations

from typing import Optional

REPORT_TYPE_DAILY = "daily_report"
REPORT_TYPE_PORTFOLIO = "portfolio_report"
REPORT_TYPES = (REPORT_TYPE_DAILY, REPORT_TYPE_PORTFOLIO)

ACCOUNT_SCOPE_SINGLE = "single_account"
ACCOUNT_SCOPE_TOTAL = "total_account"
ACCOUNT_SCOPES = (ACCOUNT_SCOPE_SINGLE, ACCOUNT_SCOPE_TOTAL)

REPORT_TYPE_SKIPPED_RENDERERS = {
    REPORT_TYPE_DAILY: frozenset({
        "render_profit_panel",
        "render_performance_attribution",
        "render_discipline_check",
        "render_holding_period",
        "render_pnl_ranking",
    }),
    REPORT_TYPE_PORTFOLIO: frozenset({
        "render_alerts",
        "render_today_summary",
        "render_trading_psychology",
        "render_news",
        "render_events",
        "render_high_risk_opp",
        "render_adjustments",
        "render_actions",
    }),
}

# Existing --all-accounts overlay: suppress strategy-dependent/editorial sections
# while keeping math/position sections available. This is an account-scope policy,
# not a report type.
TOTAL_ACCOUNT_SKIPPED_RENDERERS = frozenset({
    "render_alerts",
    "render_today_summary",
    "render_news",
    "render_events",
    "render_adjustments",
    "render_actions",
    "render_trading_psychology",
    "render_theme_sector",
    "render_high_risk_opp",
    "render_performance_attribution",
    "render_trade_quality",
    "render_discipline_check",
    "render_report_accuracy",
    "render_sources",
})

_VALIDATION_RENDERERS = {
    "today_summary": ("render_today_summary",),
    "strategy_readout": ("render_sources",),
    "data_gaps": ("render_sources",),
    "theme_sector": ("render_theme_sector",),
    "adjustments": ("render_adjustments",),
    "high_opps": ("render_high_risk_opp",),
    "actions": ("render_actions",),
    "trading_psychology": ("render_trading_psychology",),
    "reviewer_pass": ("render_sources",),
}

_RESEARCH_COVERAGE_RENDERERS = ("render_news", "render_events", "render_high_risk_opp")


def _normalize_choice(value: Optional[str], choices: tuple[str, ...], label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required; expected one of: {', '.join(choices)}")
    normalized = value.strip().replace("-", "_")
    if normalized not in choices:
        raise ValueError(f"invalid {label} {value!r}; expected one of: {', '.join(choices)}")
    return normalized


def normalize_report_type(value: str) -> str:
    """Normalize and validate the content taxonomy axis."""
    return _normalize_choice(value, REPORT_TYPES, "report_type")


def normalize_account_scope(*, all_accounts: bool = False, value: str | None = None) -> str:
    """Normalize and validate the account aggregation axis.

    ``all_accounts=True`` is the CLI spelling for ``total_account``.  If both
    forms are supplied they must agree.
    """
    if value is None or value == "":
        return ACCOUNT_SCOPE_TOTAL if all_accounts else ACCOUNT_SCOPE_SINGLE
    normalized = _normalize_choice(value, ACCOUNT_SCOPES, "account_scope")
    if all_accounts and normalized != ACCOUNT_SCOPE_TOTAL:
        raise ValueError("--all-accounts conflicts with account_scope='single_account'")
    return normalized


def effective_skipped_renderers(report_type: str, account_scope: str) -> frozenset[str]:
    """Return renderer function names skipped by the effective mode policy."""
    rt = normalize_report_type(report_type)
    scope = normalize_account_scope(value=account_scope)
    skipped = set(REPORT_TYPE_SKIPPED_RENDERERS[rt])
    if scope == ACCOUNT_SCOPE_TOTAL:
        skipped.update(TOTAL_ACCOUNT_SKIPPED_RENDERERS)
    return frozenset(skipped)


def should_validate(section: str, report_type: str, account_scope: str) -> bool:
    """Whether a validator section is required under the effective policy."""
    skipped = effective_skipped_renderers(report_type, account_scope)
    if section == "research_coverage":
        return any(renderer not in skipped for renderer in _RESEARCH_COVERAGE_RENDERERS)
    renderers = _VALIDATION_RENDERERS.get(section)
    if renderers is None:
        raise ValueError(f"unknown validation section {section!r}")
    return any(renderer not in skipped for renderer in renderers)


def hide_holdings_action_column(report_type: str, account_scope: str) -> bool:
    """Return true when the holdings table/card Action surface must be hidden."""
    rt = normalize_report_type(report_type)
    skipped = effective_skipped_renderers(rt, account_scope)
    return (
        rt == REPORT_TYPE_PORTFOLIO
        or "render_adjustments" in skipped
        or "render_actions" in skipped
    )


def default_report_filename(timestamp: str, report_type: str, account_scope: str) -> str:
    """Build the default report filename that explicitly encodes both axes."""
    rt = normalize_report_type(report_type)
    scope = normalize_account_scope(value=account_scope)
    ts = str(timestamp).strip()
    if not ts:
        raise ValueError("timestamp must be non-empty")
    return f"{ts}_{scope}_{rt}.html"
