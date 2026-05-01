#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_report.py — Portfolio HTML report renderer template.

Implements the structural and visual contract of `docs/portfolio_report_agent_guidelines.md`:

  §10  — 11 HTML sections in order, plus High-priority alerts banner
  §13  — Symbol & Price popovers
  §14  — Visual design standard (tokens, typography, RWA, anti-patterns)

The script is **deterministic for the structural / numeric parts** (totals, weights, P&L,
holding period, period-strip buckets, fallbacks) and **agent-driven for the editorial
parts** (today's verdict, news prose, action list, recommended adjustments).
Editorial content comes from a JSON context file the agent prepares per-run.

USAGE
-----
    python scripts/generate_report.py \
        --settings SETTINGS.md \
        --snapshot report_snapshot.json \
        --context report_context.json \
        --output reports/2026-04-28_1330_portfolio_report.html

The CSS / layout chrome is read from `reports/_sample_redesign.html` (the canonical
visual reference per §14.9). To change the look, edit that file — never duplicate the
styles here.

CONTEXT FILE SHAPE  (report_context.json)
-----------------------------------------
    {
      "language":      "繁體中文",
      "title":         "投資組合健康檢查 · 2026-04-28",
      "subtitle":      "...",
      "next_event":    "01-03 央行決議",
      "today_summary": ["paragraph 1", "paragraph 2"],
      "alerts":        ["bullet 1", "bullet 2"],
      "news":          [{"ticker": "DELT", "date": "2026-04-27", "headline": "...",
                          "url": "...", "source": "Reuters", "impact": "neg"}, ...],
      "events":        [{"date": "01-08", "topic": "DELT", "event": "本季財報",
                          "impact_label": "高", "impact_class": "warn", "watch": "..."},
                         ...],
      "high_opps":     [{"ticker": "ZETA", "actionable": false,
                          "why": "...", "trigger": "260 突破才研究是否加碼"}, ...],
      "adjustments":   [{"ticker": "KAPA", "current_pct": 4.5, "action": "trim",
                          "action_label": "減碼 20%", "why": "...", "trigger": "..."},
                         ...],          // non-empty list required — validate_report_context rejects []
      "holdings_actions": {"BTC": "長線續抱；50–55k 分批加碼", ...},
      "actions":       {"must_do": [{"ticker": "NVDA", "action": "add",
                                      "why": "...", "trigger": "...",
                                      "sized_pp_delta": 1.0,
                                      "variant_tag": "variant",
                                      "consensus": "...", "variant": "...",
                                      "anchor": "...", "entry_price": 1,
                                      "target_price": 2, "stop_price": 0.8,
                                      "failure_mode": "...",
                                      "kill_trigger": "...",
                                      "kill_action": "cut"}],
                         "may_do": [], "avoid": ["..."], "need_data": ["..."]},
      "transaction_analytics": {
        "performance_attribution": {...},
        "trade_quality": {...},
        "discipline_check": {...}
      },                  // optional override; generated automatically from transactions.db when absent
      "theme_sector_html": "<div class=\"cols-2\">...</div>",
      "theme_sector_audit": {
        "tickers": {
          "NVDA": {"sector": "半導體", "themes": {"AI 算力": 1.0}, "sources": ["..."]}
        }
      },
      "research_coverage": {
        "tickers": {
          "NVDA": {"news": {"count": 1}, "events": {"count": 1}}
        }
      },
      "trading_psychology": {
        "headline": "...",
        "observations": [{"behavior": "...", "evidence": "snapshot.transaction_analytics...", "tone": "warn"}],
        "improvements": [{"issue": "...", "suggestion": "...", "priority": "high"}],
        "strengths": ["..."]
      },                  // mandatory; full context validated by scripts/validate_report_context.py before render
      "reviewer_pass": {
        "completed": true,
        "reviewed_sections": ["alerts", "watchlist", "adjustments", "actions",
                              "strategy_readout", "trading_psychology",
                              "theme_sector", "news_events"],
        "summary": [],
        "by_section": {}
      },
      "data_gaps":     [{"summary": "ALPH 成本基礎缺失",
                          "detail": "transactions.db open_lots row for ALPH lacks cost basis"}, ...],
      "spec_update_note": "...",
    }

REQUIRED EDITORIAL HTML — `theme_sector_html` (spec §10.4.2)
-------------------------------------------------------------
The agent **must** auto-classify each holding by sector / theme each run,
pre-render the bar chart as a string of HTML, and provide `theme_sector_audit`.
The script does NOT compute this because the classification depends on current
public-data context, not just the ticker. Missing theme fields fail the
pre-render context validator.

The full deterministic contract — closed-list sectors, fixed-order theme master
list, ETF look-through rules, bar color rules, bucket-note thresholds, and the
self-check items — lives in `docs/portfolio_report_agent_guidelines/`
`04-computations-to-static-snapshot.md` §10.4.2 (HARD REQUIREMENT). Following
that contract produces identical output across runs given the same inputs.

Top-level markup must match `_sample_redesign.html` lines 1267-1300:

    <div class="cols-2">
      <div>
        <div class="eyebrow" style="margin-bottom:10px">主題</div>
        <div class="bars">
          <div class="bar-row">
            <div class="bar-label">AI 算力</div>
            <div class="bar-track"><div class="bar warn" style="width:100%"></div></div>
            <div class="bar-value">15.5%</div>
          </div>
          ... (themes — sorted per §10.4.2 F)
        </div>
      </div>
      <div>
        <div class="eyebrow" style="margin-bottom:10px">行業</div>
        <div class="bars">
          ... (sectors — exclusive primary industry, sums to 100%)
        </div>
      </div>
    </div>
    <div class="bucket-note" style="margin-top:18px">
      <b>集中度警示：</b>...
    </div>

Bar color modifiers per §10.4.2 E: `bar warn` (concentration alert), `bar info`
(cross-cutting), `bar pos` / `bar neg` (rare, thesis-aligned only). Weights are
base-currency based (§9.0). Bucket-note thresholds are configurable via SETTINGS.md.

Every other field is optional; missing fields render as `n/a` per §9.6 with no
guesses.

The "Sources & data gaps" audit table is built mechanically from `prices.json`,
including auto-fetched FX conversion rates under `prices.json["_fx"]`. The agent
does not author FX rates in SETTINGS.md or the editorial context.

DEPENDENCIES
------------
    Python 3.10+. No external packages required. (yfinance is only used by
    `fetch_prices.py`; the renderer reads its JSON output.)
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import html
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reuse the lot shape + market routing from the sister script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_prices import (                                    # noqa: E402
    Lot,
    MarketType,
    find_todo_required_hard_failures,
    format_todo_required_hard_failures,
)

# Pure-compute pipeline stage. The renderer no longer owns the math — it
# imports the dataclasses, helpers, and snapshot serializer from
# portfolio_snapshot.py so `python scripts/transactions.py snapshot` and the
# legacy `--prices --db` fallback share one implementation.
from portfolio_snapshot import (                              # noqa: E402
    BASE_CURRENCY_PATTERN,
    BookPacing,
    CASH_STABLECOIN_USD,
    CheckResult,
    DEFAULT_BASE_CURRENCY,
    DEFAULTS,
    DISPLAY_NAME_BY_LOCALE,
    LANGUAGE_ALIASES,
    LANGUAGE_QUOTE_CHARS,
    MARKET_DEFAULT_CCY,
    RAIL_PATTERNS,
    RISK_REASONS_EN,
    RiskHeatItem,
    SCHEMA_VERSION as SNAPSHOT_SCHEMA_VERSION,
    SettingsProfile,
    Snapshot,
    TickerAggregate,
    _bucket_key,
    _bucket_priority,
    _days_label,
    _fx_to_base,
    aggregate,
    auto_fx_from_prices,
    book_pacing,
    build_risk_heat_items,
    compute_snapshot,
    compute_totals,
    deserialize_snapshot,
    find_missing_fx,
    hold_period_label,
    merge_prices,
    parse_settings_profile,
    serialize_snapshot,
    settings_profile_for_snapshot,
    special_checks,
    write_snapshot,
)
from validate_report_context import validate_report_context    # noqa: E402
from report_archive import archive_report as _archive_report   # noqa: E402


# Legacy alias kept for any out-of-tree caller that imported this name from
# generate_report. The canonical implementation lives in portfolio_snapshot.
_auto_fx_from_prices = auto_fx_from_prices


# ----------------------------------------------------------------------------- #
# PM-grade indicators & strategy binding
#
# Canonical implementation of the calculation logic introduced by AGENTS.md
# and `/docs/portfolio_report_agent_guidelines/07-investment-content-and-checklist.md`
# §§15.4–15.7. The agent must use these helpers (or pass raw inputs through
# `report_context.json` and let the renderer call them) so every report uses
# the same math:
#
#   - Strategy readout is supplied by the agent via
#     `context["strategy_readout"]` (legacy alias `context["style_readout"]`
#     still accepted). The agent reads the whole `## Investment Style And
#     Strategy` section in SETTINGS.md, internalises it, and writes the
#     readout in first person as the user. The renderer slots the prose
#     verbatim under §10.11 — there is no structured lever block, no keyword
#     inference, and no template formatter on the script side. Behavior that
#     used to route through structured levers (kill-price width, sizing band,
#     lot-trim ordering, contrarian latitude, hype cap) now flows from the
#     agent's reading of the strategy text per §15.7.
#   - StyleLevers / validate_style_levers / suggest_stop_pct_band /
#     suggest_size_pp_band are retained as legacy helpers for callers that
#     want a structured value-band lookup, but they are no longer mandated
#     by the spec. The agent is free to derive these values directly from
#     the user's strategy text and pass them straight into the recommendation.
#   - compute_rr_ratio() / format_rr_string()  — §15.4 Reward-to-risk asymmetry
#   - check_rails() / format_portfolio_fit_line()  — §15.6 sizing-rail gate
#   - length_budget_status() / validate_recommendation_block()  — §15.6.2 / A.11
#
# Determinism is enforced by exact-string outputs and tested via `--self-check`.
# ----------------------------------------------------------------------------- #

# Neutral defaults (per §15.7 — single source of truth in this module).
LEVER_DEFAULT = {
    "drawdown_tolerance": "medium",
    "conviction_sizing": "flat",
    "holding_period_bias": "investor",
    "confirmation_threshold": "medium",
    "contrarian_appetite": "selective",
    "hype_tolerance": "low",
}

LEVER_ALLOWED = {
    "drawdown_tolerance": ("low", "medium", "high"),
    "conviction_sizing": ("flat", "kelly-lite", "aggressive"),
    "holding_period_bias": ("trader", "swing", "investor", "lifer"),
    "confirmation_threshold": ("low", "medium", "high"),
    "contrarian_appetite": ("none", "selective", "strong"),
    "hype_tolerance": ("zero", "low", "medium"),
}


@dataclass
class StyleLevers:
    """Legacy structured-lever helper (retained for backward compatibility).

    The §15.7 spec no longer mandates a structured lever resolution: the agent
    reads the whole `## Investment Style And Strategy` section in SETTINGS.md
    and acts as the user. This dataclass remains available for callers that
    still want a value-band lookup (e.g. mapping a textual conviction posture
    to a sizing band). It is not consumed by the renderer's report flow.

    `sources[lever]` is a free-form provenance tag (e.g. ``bullet "<text>"``,
    ``"default"``) preserved for callers that mirror the legacy readout format.

    Validation: pass through `validate_style_levers()` to enforce that every
    field's value is in `LEVER_ALLOWED[field]`.
    """

    drawdown_tolerance: str = LEVER_DEFAULT["drawdown_tolerance"]
    conviction_sizing: str = LEVER_DEFAULT["conviction_sizing"]
    holding_period_bias: str = LEVER_DEFAULT["holding_period_bias"]
    confirmation_threshold: str = LEVER_DEFAULT["confirmation_threshold"]
    contrarian_appetite: str = LEVER_DEFAULT["contrarian_appetite"]
    hype_tolerance: str = LEVER_DEFAULT["hype_tolerance"]
    sources: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, str]:
        return {
            "drawdown_tolerance": self.drawdown_tolerance,
            "conviction_sizing": self.conviction_sizing,
            "holding_period_bias": self.holding_period_bias,
            "confirmation_threshold": self.confirmation_threshold,
            "contrarian_appetite": self.contrarian_appetite,
            "hype_tolerance": self.hype_tolerance,
        }


def validate_style_levers(levers: "StyleLevers") -> List[str]:
    """Return list of invalid lever values (out of LEVER_ALLOWED). Empty = ok."""

    bad: List[str] = []
    for field_name, allowed in LEVER_ALLOWED.items():
        value = getattr(levers, field_name, None)
        if value not in allowed:
            bad.append(f"{field_name}={value!r} not in {allowed}")
    return bad


# --------------------------------------------------------------------------- #
# §15.4 Reward-to-risk asymmetry
# --------------------------------------------------------------------------- #


def compute_rr_ratio(
    target: Optional[float],
    entry: Optional[float],
    stop: Optional[float],
) -> Optional[float]:
    """Return R:R as a positive float (target_distance / stop_distance), or None
    when inputs are missing or degenerate. Sign-aware: long if target > entry > stop,
    short if target < entry < stop. Returns None for inverted setups."""

    if target is None or entry is None or stop is None:
        return None
    upside = target - entry
    downside = entry - stop
    # Long: upside > 0 and downside > 0. Short: upside < 0 and downside < 0.
    if upside == 0 or downside == 0:
        return None
    if (upside > 0) != (downside > 0):
        return None  # inverted — likely operator error
    rr = abs(upside) / abs(downside)
    return round(rr, 2)


def format_rr_string(
    target: Optional[float],
    entry: Optional[float],
    stop: Optional[float],
    horizon_label: Optional[str] = None,
    *,
    binary: bool = False,
    rebalance: bool = False,
    hedged: bool = False,
    structural_reason: Optional[str] = None,
) -> str:
    """Canonical R:R string per §15.4.

    Output examples:
      "Target $260 (+30%) / Stop $185 (-7%) → R:R = 4.3:1 over 9 months"
      "R:R = n/a (binary outcome — see kill criteria)"
      "R:R = n/a (rebalance)"
      "Target $260 (+30%) / Stop = n/a (hedged structure — see kill action)"
    """

    if rebalance:
        return "R:R = n/a (rebalance)"
    if binary:
        return "R:R = n/a (binary outcome — see kill criteria)"
    if hedged and target is not None and entry is not None:
        upside_pct = (target - entry) / entry * 100.0
        return (
            f"Target ${target:g} ({upside_pct:+.0f}%) / "
            f"Stop = n/a (hedged structure — see kill action)"
        )
    if structural_reason:
        return f"R:R = n/a ({structural_reason})"

    rr = compute_rr_ratio(target, entry, stop)
    if rr is None or target is None or entry is None or stop is None:
        return "R:R = n/a (inputs incomplete)"

    upside_pct = (target - entry) / entry * 100.0
    downside_pct = (stop - entry) / entry * 100.0
    horizon = f" over {horizon_label}" if horizon_label else ""
    return (
        f"Target ${target:g} ({upside_pct:+.0f}%) / "
        f"Stop ${stop:g} ({downside_pct:+.0f}%) → R:R = {rr:g}:1{horizon}"
    )


# --------------------------------------------------------------------------- #
# §15.5 / §15.6 lever-driven suggestion bands
# --------------------------------------------------------------------------- #

# Drawdown tolerance → (-low_pct, -high_pct) suggested stop-distance range.
STOP_PCT_BAND_BY_DRAWDOWN: Dict[str, Tuple[float, float]] = {
    "low":    (7.0, 10.0),
    "medium": (12.0, 18.0),
    "high":   (20.0, 30.0),
}

# Conviction sizing → (min_pp, max_pp) recommended pp-of-NAV per single name.
SIZE_PP_BAND_BY_CONVICTION: Dict[str, Tuple[float, float]] = {
    "flat":       (0.0, 5.0),
    "kelly-lite": (2.0, 8.0),
    "aggressive": (8.0, 15.0),
}


def suggest_stop_pct_band(drawdown_tolerance: str) -> Tuple[float, float]:
    """Return (low%, high%) magnitude — both positive numbers; subtract from entry."""
    return STOP_PCT_BAND_BY_DRAWDOWN.get(drawdown_tolerance, STOP_PCT_BAND_BY_DRAWDOWN["medium"])


def suggest_size_pp_band(conviction_sizing: str) -> Tuple[float, float]:
    """Return (min_pp, max_pp) recommended position-size band per name."""
    return SIZE_PP_BAND_BY_CONVICTION.get(conviction_sizing, SIZE_PP_BAND_BY_CONVICTION["flat"])


# --------------------------------------------------------------------------- #
# §15.6 sizing-rail gate
# --------------------------------------------------------------------------- #


@dataclass
class RailReport:
    """Outcome of checking a proposed action against SETTINGS sizing rails."""

    single_name_pct_after: float
    single_name_warn: float
    single_name_breach: bool
    theme_pct_after: Optional[float]
    theme_warn: float
    theme_breach: bool
    high_vol_pct_after: Optional[float]
    high_vol_warn: float
    high_vol_breach: bool
    cash_pct_after: Optional[float]
    cash_floor_warn: float
    cash_floor_breach: bool

    @property
    def any_breach(self) -> bool:
        return self.single_name_breach or self.theme_breach or self.high_vol_breach or self.cash_floor_breach

    def breached_rails(self) -> List[str]:
        out = []
        if self.single_name_breach:
            out.append("single-name")
        if self.theme_breach:
            out.append("theme")
        if self.high_vol_breach:
            out.append("high-vol bucket")
        if self.cash_floor_breach:
            out.append("cash floor")
        return out


def check_rails(
    config: Dict[str, float],
    *,
    current_pct: float,
    delta_pp: float,
    theme_pct_after: Optional[float] = None,
    high_vol_pct_after: Optional[float] = None,
    cash_pct_after: Optional[float] = None,
) -> RailReport:
    """Apply the §15.6 rail gate. All percentages are pp of NAV (incl cash).

    `delta_pp` is signed: + adds to position, − trims. The single-name `pct_after`
    is computed; theme / high-vol / cash values are passed in by the caller because
    the renderer cannot infer them without the agent's classification.
    """

    sn_warn = config.get("single_name_weight_warn_pct", DEFAULTS["single_name_weight_warn_pct"])
    th_warn = config.get("theme_concentration_warn_pct", DEFAULTS["theme_concentration_warn_pct"])
    hv_warn = config.get("high_vol_bucket_warn_pct", DEFAULTS["high_vol_bucket_warn_pct"])
    cash_warn = config.get("cash_floor_warn_pct", DEFAULTS["cash_floor_warn_pct"])

    sn_after = max(current_pct + delta_pp, 0.0)

    return RailReport(
        single_name_pct_after=sn_after,
        single_name_warn=sn_warn,
        single_name_breach=sn_after > sn_warn,
        theme_pct_after=theme_pct_after,
        theme_warn=th_warn,
        theme_breach=theme_pct_after is not None and theme_pct_after > th_warn,
        high_vol_pct_after=high_vol_pct_after,
        high_vol_warn=hv_warn,
        high_vol_breach=high_vol_pct_after is not None and high_vol_pct_after > hv_warn,
        cash_pct_after=cash_pct_after,
        cash_floor_warn=cash_warn,
        cash_floor_breach=cash_pct_after is not None and cash_pct_after < cash_warn,
    )


def format_portfolio_fit_line(
    *,
    sized_pp: float,
    correlated_with: Optional[List[str]] = None,
    theme_overlap: Optional[List[str]] = None,
    rails: Optional[RailReport] = None,
) -> str:
    """One-line `Portfolio fit — ...` annotation per §15.6."""

    parts: List[str] = [f"sized {sized_pp:+.1f}pp of NAV"]
    if correlated_with:
        parts.append(f"correlated with {', '.join(correlated_with)}")
    if theme_overlap:
        parts.append(f"theme overlap with {', '.join(theme_overlap)}")
    if rails is not None:
        if rails.any_breach:
            breached = ", ".join(rails.breached_rails())
            parts.append(f"BREACHES rails: {breached}")
        else:
            parts.append("rails OK")
        parts.append(
            f"single-name {rails.single_name_pct_after:.1f}% vs warn {rails.single_name_warn:.1f}%"
        )
        if rails.cash_pct_after is not None:
            parts.append(
                f"cash {rails.cash_pct_after:.1f}% vs floor {rails.cash_floor_warn:.1f}%"
            )
    return "Portfolio fit — " + "; ".join(parts) + "."


# --------------------------------------------------------------------------- #
# §15.6.2 length budget + §A.11 validation
# --------------------------------------------------------------------------- #


def length_budget_status(
    text: str,
    *,
    max_words: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """Word/char count + over-budget warning. Used by Appendix A.11 self-check."""

    words = len(text.split())
    chars = len(text)
    over = False
    reasons: List[str] = []
    if max_words is not None and words > max_words:
        over = True
        reasons.append(f"words {words} > {max_words}")
    if max_chars is not None and chars > max_chars:
        over = True
        reasons.append(f"chars {chars} > {max_chars}")
    return {"words": words, "chars": chars, "over": over, "reasons": reasons}


REBALANCE_VARIANT_TAGS = {"rebalance"}
ACTIONABLE_ACTIONS = {
    "add", "buy", "trim", "sell", "cut", "reduce", "increase", "short", "cover", "hedge"
}
PM_FIELD_KEYS = {
    "variant_tag", "consensus", "variant", "anchor",
    "entry_price", "target_price", "stop_price", "horizon_label",
    "binary_catalyst", "hedged_structure", "rr_structural_reason",
    "failure_mode", "kill_trigger", "kill_action",
    "sized_pp_delta", "target_pct", "correlated_with", "theme_overlap",
    "theme_pct_after", "high_vol_pct_after", "cash_pct_after",
}


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolved_sized_pp_delta(adj: Dict[str, Any], current_pct: Optional[float] = None) -> Optional[float]:
    """Resolve action size as pp of total NAV.

    The canonical denominator is total NAV including cash. Agents may pass either
    an explicit `sized_pp_delta` or a `target_pct`; when `target_pct` is used the
    renderer computes the delta from the actual current weight, not a context-
    supplied current_pct string.
    """

    direct = _float_or_none(adj.get("sized_pp_delta"))
    if direct is not None:
        return direct
    target = _float_or_none(adj.get("target_pct"))
    if target is not None and current_pct is not None:
        return target - current_pct
    return None


def is_actionable_recommendation(adj: Dict[str, Any], current_pct: Optional[float] = None) -> bool:
    """A report row is actionable only when it changes NAV or explicitly names a trade.

    Hold / no-add / watch / avoid rows are status guidance. They may carry a
    trigger, but they should not be forced into fake R:R or kill fields.
    """

    delta = _resolved_sized_pp_delta(adj, current_pct)
    if delta is not None and abs(delta) > 1e-9:
        return True
    action = str(adj.get("action") or "").strip().lower()
    return action in ACTIONABLE_ACTIONS


def validate_recommendation_block(adj: Dict[str, Any]) -> List[str]:
    """Return list of A.11 / §15 violations for a single adjustment dict.

    Empty list = compliant. The agent should fix or downgrade any item that
    returns non-empty findings before publishing the report.
    """

    findings: List[str] = []
    variant_tag = (adj.get("variant_tag") or "").lower()
    is_rebalance = variant_tag in REBALANCE_VARIANT_TAGS
    is_actionable = is_actionable_recommendation(adj)
    has_pm_fields = any(adj.get(k) not in (None, "", []) for k in PM_FIELD_KEYS)

    if not is_actionable and not has_pm_fields:
        return findings

    if is_actionable and not is_rebalance:
        if not adj.get("variant_tag"):
            findings.append("variant_tag missing (§15.4)")
        elif variant_tag not in ("consensus-aligned", "variant", "contrarian"):
            findings.append(f"variant_tag invalid: {variant_tag!r} (§15.4)")

        if not adj.get("consensus"):
            findings.append("consensus missing — write `unknown-consensus (...)` if no public consensus (§15.4)")
        if variant_tag in ("variant", "contrarian") and not adj.get("anchor"):
            findings.append("anchor missing for variant/contrarian call — downgrade to `consensus-aligned` (§15.4)")

        # R:R fields — required unless explicit binary/hedged/rebalance escape.
        has_rr_inputs = all(adj.get(k) is not None for k in ("entry_price", "target_price", "stop_price"))
        binary = bool(adj.get("binary_catalyst"))
        hedged = bool(adj.get("hedged_structure"))
        if not (has_rr_inputs or binary or hedged):
            findings.append("R:R inputs missing (entry/target/stop) and no binary/hedged escape (§15.4)")

        # Kill criteria triplet — required for non-rebalance.
        if not adj.get("kill_trigger"):
            findings.append("kill_trigger missing (§15.5)")
        if not adj.get("kill_action"):
            findings.append("kill_action missing (§15.5)")
        if not adj.get("failure_mode"):
            findings.append("failure_mode missing (§15.5)")

    if is_actionable and _resolved_sized_pp_delta(adj) is None:
        findings.append("sized_pp_delta or target_pct missing (§15.3 / §15.6)")

    return findings


# Module-level export so the agent can import helpers without digging into
# private names.
__all__ = [
    "StyleLevers", "validate_style_levers",
    "compute_rr_ratio", "format_rr_string",
    "suggest_stop_pct_band", "suggest_size_pp_band",
    "RailReport", "check_rails", "format_portfolio_fit_line",
    "length_budget_status", "validate_recommendation_block",
    "LEVER_DEFAULT", "LEVER_ALLOWED",
    "STOP_PCT_BAND_BY_DRAWDOWN", "SIZE_PP_BAND_BY_CONVICTION",
]


# ----------------------------------------------------------------------------- #
# Stable dictionaries (EN / zh-Hant / zh-Hans)
# Canonical source lives in scripts/i18n/*.json. For any other locale, the
# executing agent should translate report_ui.en.json and pass the overlay via
# --ui-dict or context["ui_dictionary"].
# ----------------------------------------------------------------------------- #

BUILTIN_UI_LOCALES = ("en", "zh-Hant", "zh-Hans")
I18N_DIR = Path(__file__).resolve().parent / "i18n"


def _load_json_ui_dict(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_builtin_ui_text() -> Dict[str, Dict[str, Any]]:
    loaded: Dict[str, Dict[str, Any]] = {}
    for locale in BUILTIN_UI_LOCALES:
        path = I18N_DIR / f"report_ui.{locale}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing built-in UI dictionary: {path}. Restore scripts/i18n/*.json "
                "before generating reports."
            )
        loaded[locale] = _load_json_ui_dict(path)
    return loaded


STABLE_UI_TEXT = _load_builtin_ui_text()

ACTIVE_UI: Dict[str, Any] = copy.deepcopy(STABLE_UI_TEXT["en"])
# `LANGUAGE_QUOTE_CHARS` is imported from portfolio_snapshot at module top.


def _ui(path: str, **kwargs: Any) -> str:
    node: Any = ACTIVE_UI
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return path
        node = node[part]
    if not isinstance(node, str):
        return path
    return node.format(**kwargs) if kwargs else node


def _set_active_ui(bundle: Dict[str, Any]) -> None:
    global ACTIVE_UI
    ACTIVE_UI = bundle


# Active base currency — set by render_html() before any display function runs so
# `_fmt_money`, popover footers, and the audit warning all use the configured base
# instead of hard-coded USD.
ACTIVE_BASE_CURRENCY: str = DEFAULT_BASE_CURRENCY


def _set_active_base_currency(ccy: str) -> None:
    global ACTIVE_BASE_CURRENCY
    ACTIVE_BASE_CURRENCY = (ccy or DEFAULT_BASE_CURRENCY).upper()


def _base_prefix() -> str:
    """Return the currency prefix for the active base currency (e.g. `$`, `NT$`)."""
    return CURRENCY_PREFIX.get(ACTIVE_BASE_CURRENCY, f"{ACTIVE_BASE_CURRENCY} ")


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def resolve_ui_bundle(
    settings: SettingsProfile,
    ui_dict_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if settings.locale in STABLE_UI_TEXT:
        bundle = copy.deepcopy(STABLE_UI_TEXT[settings.locale])
    else:
        bundle = copy.deepcopy(STABLE_UI_TEXT["en"])
    if ui_dict_override:
        bundle = _deep_merge_dict(bundle, ui_dict_override)
    bundle["meta"]["language_name"] = settings.display_name
    bundle["meta"]["html_lang"] = settings.locale
    return bundle


# ----------------------------------------------------------------------------- #
# CSS extraction from the canonical sample (§14.9)
# ----------------------------------------------------------------------------- #

_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)

# §15.8 — reviewer-pass styling. Visually distinct from the user's prose so
# annotations are obviously the reviewer's voice, not the user's. Appended to
# the loaded sample CSS via `_REVIEWER_CSS` in the rendered HTML.
_REVIEWER_CSS = """
.reviewer-note-block { margin-top: 12px; padding: 10px 12px; border-left: 3px solid #94a3b8; background: rgba(148, 163, 184, 0.08); border-radius: 4px; }
.reviewer-note-block ul { margin: 0; padding-left: 0; list-style: none; }
.reviewer-note-block li { font-style: italic; color: #475569; font-size: 0.9em; line-height: 1.5; padding: 2px 0; }
.reviewer-note-block li b { font-style: normal; color: #334155; margin-right: 4px; }
.reviewer-note-inline { margin-top: 8px; padding: 6px 8px; border-left: 2px solid #94a3b8; background: rgba(148, 163, 184, 0.08); border-radius: 3px; font-style: italic; color: #475569; font-size: 0.88em; line-height: 1.45; }
.reviewer-note-inline b { font-style: normal; color: #334155; margin-right: 4px; }
li.reviewer-note, li.reviewer-summary { font-style: italic; color: #475569; }
li.reviewer-note b, li.reviewer-summary b { font-style: normal; color: #334155; }
li.reviewer-summary { margin-top: 8px; padding-top: 8px; border-top: 1px dashed #cbd5e1; }
/* §10.1.7 trading psychology — same typographic scale as .prose / body (§14.9 tokens) */
.psych-headline { margin-bottom: 14px; }
.psych-headline p {
  margin: 0;
  color: var(--ink-soft);
  font-size: clamp(13.5px, 0.35vw + 12.4px, 14.5px);
  line-height: 1.7;
  font-weight: 650;
}
.psych-list { margin: 0; padding-left: 0; list-style: none; }
.psych-list li {
  margin: 0 0 10px 0;
  padding: 0;
  color: var(--ink-soft);
  font-size: clamp(13.5px, 0.35vw + 12.4px, 14.5px);
  line-height: 1.7;
}
.psych-list li:last-child { margin-bottom: 0; }
.psych-list .psych-li-main { display: inline; }
.psych-evidence {
  margin-top: 6px;
  font-size: clamp(11.5px, 0.2vw + 10.8px, 12.5px);
  color: var(--muted);
  letter-spacing: 0.04em;
  line-height: 1.45;
}
.psych-ev-prefix { font-style: italic; margin-right: 4px; }
.psych-suggestion {
  margin-top: 6px;
  color: var(--ink-soft);
  font-size: clamp(13.5px, 0.35vw + 12.4px, 14.5px);
  line-height: 1.65;
}
.psych-suggestion-label { font-weight: 650; margin-right: 6px; }
.psych-strengths-wrap { margin-top: 18px; }
.tag.info { color: var(--info); border-color: #b8c9e8; background: #f4f7fd; }
.tag.neu { color: var(--muted); border-color: var(--hairline-2); background: var(--surface-2); }
/* §10.1.5a report accuracy — one KPI uses full width (avoid 4-col grid squeezing) */
.kpis.kpis-solo { grid-template-columns: minmax(0, 1fr); }
.kpis.kpis-solo .kpi { padding-left: 0; }
"""


def load_canonical_css(sample_path: Path) -> str:
    """Read the <style>...</style> block from `reports/_sample_redesign.html`."""
    if not sample_path.exists():
        raise FileNotFoundError(
            f"Canonical sample not found at {sample_path}. The sample is the "
            "single source of styles per §14.9 — restore it before generating reports."
        )
    text = sample_path.read_text(encoding="utf-8")
    m = _STYLE_RE.search(text)
    if not m:
        raise ValueError(f"No <style> block found in {sample_path}")
    return m.group(1)


# ----------------------------------------------------------------------------- #
# Metrics — TickerAggregate, BookPacing, RiskHeatItem, CheckResult, aggregate(),
# merge_prices(), book_pacing(), build_risk_heat_items(), special_checks() and
# the FX helpers all live in `portfolio_snapshot` so the snapshot and the
# renderer share one implementation. Imported at the top of this file.
# ----------------------------------------------------------------------------- #


def _translate_bucket(bucket: str) -> str:
    bucket_key = _bucket_key(bucket)
    translated = _ui(f"bucket.{bucket_key}")
    if translated != f"bucket.{bucket_key}":
        return translated
    return bucket


def _translate_freshness(label: Optional[str]) -> str:
    if label is None:
        return _ui("common.na")
    translated = _ui(f"freshness.{label}")
    return translated if translated != f"freshness.{label}" else label


def _translate_market_state(label: Optional[str]) -> str:
    if label is None:
        return _ui("common.na")
    translated = _ui(f"market_state.{label}")
    return translated if translated != f"market_state.{label}" else label


def _translate_market(label: Optional[str]) -> str:
    if label is None:
        return _ui("common.na")
    translated = _ui(f"market.{label}")
    return translated if translated != f"market.{label}" else label


# ----------------------------------------------------------------------------- #
# HTML helpers
# ----------------------------------------------------------------------------- #

def _esc(s: Any) -> str:
    return html.escape(str(s) if s is not None else "")


def _fmt_money(value: Optional[float], currency_prefix: Optional[str] = None) -> str:
    if currency_prefix is None:
        currency_prefix = _base_prefix()
    if value is None:
        return f'<span class="na">{_ui("common.na")}</span>'
    sign = "−" if value < 0 else ""
    return f"{sign}{currency_prefix}{abs(value):,.0f}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return f'<span class="na">{_ui("common.na")}</span>'
    return f"{value:+.1f}%"


def _fmt_signed(value: Optional[float], pct: Optional[float]) -> str:
    """Return signed P&L wrapped in a <span> — used by callers that style at span level.

    For table cells where the canonical sample applies the color class directly to
    `<td class="num pos-txt">`, prefer `_fmt_signed_parts()` instead.
    """
    if value is None:
        return f'<span class="na">{_ui("common.na")}</span>'
    cls = "pos-txt" if value >= 0 else "neg-txt"
    sign = "+" if value >= 0 else "−"
    pct_str = f" / {sign}{abs(pct):.1f}%" if pct is not None else ""
    return f'<span class="{cls}">{sign}{_base_prefix()}{abs(value):,.0f}{pct_str}</span>'


def _fmt_signed_parts(value: Optional[float], pct: Optional[float]) -> Tuple[str, str]:
    """Return (extra_td_class, inner_html) so callers can apply pos-txt/neg-txt to the <td>.

    Matches the canonical sample's `<td class="num pos-txt">+$12,993 / +43.3%</td>` shape,
    with the prefix swapped for the active base currency (e.g. `NT$`, `¥`).
    """
    if value is None:
        return "", f'<span class="na">{_ui("common.na")}</span>'
    cls = "pos-txt" if value >= 0 else "neg-txt"
    sign = "+" if value >= 0 else "−"
    pct_str = f" / {sign}{abs(pct):.1f}%" if pct is not None else ""
    return cls, f"{sign}{_base_prefix()}{abs(value):,.0f}{pct_str}"


def _format_years(value: float) -> str:
    suffix = _ui("holding_period.years_suffix")
    if suffix in {"年"}:
        return f"{value} {suffix}"
    return f"{value}{suffix}"


# ----------------------------------------------------------------------------- #
# Section renderers
#
# Each function returns a string of HTML for its section. Order is preserved by
# the master `render_html` function. Anything the agent must author appears in
# `context`; numeric / structural content comes from `aggs`, `prices`, `config`.
# ----------------------------------------------------------------------------- #

def _format_fx_masthead(context: Dict[str, Any]) -> str:
    rates = context.get("fx") or {}
    details = context.get("fx_details") or {}
    if not isinstance(rates, dict) or not rates:
        return _ui("common.na")
    parts = []
    for pair, rate in sorted(rates.items()):
        detail = details.get(pair, {}) if isinstance(details, dict) else {}
        as_of = detail.get("price_as_of") if isinstance(detail, dict) else None
        suffix = f" @ {as_of}" if as_of else ""
        parts.append(f"{pair} {rate}{suffix}")
    return " · ".join(parts)


def render_masthead(context: Dict[str, Any]) -> str:
    lang = _esc(context.get("language", _ui("meta.language_name")))
    title = _esc(context.get("title", _ui("masthead.title")))
    subtitle = _esc(context.get("subtitle", ""))
    fx_str = _format_fx_masthead(context)
    next_event = _esc(context.get("next_event", _ui("common.na")))
    generated = context.get("generated_at") or _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""\
  <header class="masthead">
    <div class="eyebrow">{_esc(_ui("masthead.eyebrow"))} · {lang}</div>
    <h1>{title}</h1>
    <p class="dek">{subtitle}</p>
    <div class="masthead-meta">
      <span><b>{_esc(_ui("common.generated_at"))}</b>　{_esc(generated)}</span>
      <span><b>{_esc(_ui("common.benchmark_fx"))}</b>　{_esc(fx_str)}</span>
      <span><b>{_esc(_ui("common.next_event"))}</b>　{next_event}</span>
    </div>
  </header>"""


def _reviewer_pass(context: Dict[str, Any]) -> Dict[str, Any]:
    """Return the §15.8 reviewer-pass payload, normalising shape.

    Accepted shapes (any combination):
      context["reviewer_pass"] = {
        "summary": [str, ...],
        "by_section": {"alerts": [...], "watchlist": [...],
                       "adjustments": [...], "actions": [...],
                       "strategy_readout": [...]}
      }

    Returns ``{"summary": [...], "by_section": {...}}`` with safe defaults.
    """
    rp = context.get("reviewer_pass") or {}
    if not isinstance(rp, dict):
        return {"summary": [], "by_section": {}}
    summary = rp.get("summary") or []
    by_section = rp.get("by_section") or {}
    if not isinstance(summary, list):
        summary = []
    if not isinstance(by_section, dict):
        by_section = {}
    return {"summary": summary, "by_section": by_section}


def _render_reviewer_notes(notes, label: str) -> str:
    """Render a list of reviewer notes as an aside block.

    Returns an empty string when ``notes`` is falsy (empty notes are the
    correct treatment per §15.8.4 — never render a placeholder).
    """
    if not notes:
        return ""
    if isinstance(notes, str):
        notes = [notes]
    items = "".join(
        f'<li><b>{_esc(label)}:</b> {_esc(n)}</li>'
        for n in notes if isinstance(n, str) and n.strip()
    )
    if not items:
        return ""
    return f'<aside class="reviewer-note-block"><ul>{items}</ul></aside>'


def render_alerts(context: Dict[str, Any]) -> str:
    alerts = context.get("alerts") or []
    if not alerts:
        return ""
    items = "\n      ".join(f"<li>{_esc(a)}</li>" for a in alerts)
    rp_notes = _reviewer_pass(context)["by_section"].get("alerts") or []
    reviewer_block = _render_reviewer_notes(rp_notes, _ui("reviewer.note_label"))
    return f"""\
  <section class="callout">
    <div class="ctitle"><span class="badge">{_esc(_ui("alerts.badge"))}</span>{_esc(_ui("alerts.title"))}</div>
    <ul>
      {items}
    </ul>
    {reviewer_block}
  </section>"""


def render_today_summary(context: Dict[str, Any]) -> str:
    paragraphs = context.get("today_summary") or [_ui("summary.placeholder")]
    cols = ["<div>" + "".join(f"<p>{_esc(p)}</p>" for p in paragraphs[:1]) + "</div>"]
    if len(paragraphs) > 1:
        cols.append("<div>" + "".join(f"<p>{_esc(p)}</p>" for p in paragraphs[1:]) + "</div>")
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("summary.title"))}</h2>
      <span class="sub">{_esc(_ui("summary.subtitle"))}</span>
    </div>
    <div class="prose cols-2">{''.join(cols)}</div>
  </section>"""


def render_dashboard(
    aggs: Dict[str, TickerAggregate],
    total_assets: float,
    invested: float,
    cash: float,
    pnl: Optional[float],
) -> str:
    if total_assets <= 0:
        return ""
    invested_pct = invested / total_assets * 100.0
    cash_pct = cash / total_assets * 100.0
    bp = _base_prefix()
    pnl_html = (f'<div class="delta {"pos" if pnl >= 0 else "neg"}">{"+" if pnl >= 0 else "−"}{bp}{abs(pnl):,.0f}</div>'
                if pnl is not None else f'<div class="delta">{_ui("common.na")}</div>')
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("dashboard.title"))}</h2>
      <span class="sub">{_esc(_ui("dashboard.subtitle", base=ACTIVE_BASE_CURRENCY))}</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="k">{_esc(_ui("dashboard.total_assets"))}</div><div class="v">{bp}{total_assets:,.0f}</div><div class="delta">{_esc(_ui("dashboard.total_assets_note"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("dashboard.invested"))}</div><div class="v">{bp}{invested:,.0f}</div><div class="delta">{_esc(_ui("dashboard.invested_note", pct=invested_pct))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("dashboard.cash"))}</div><div class="v">{bp}{cash:,.0f}</div><div class="delta">{_esc(_ui("dashboard.cash_note", pct=cash_pct))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("dashboard.known_pnl"))}</div><div class="v">{_fmt_money(pnl)}</div><div class="delta">{_esc(_ui("dashboard.pnl_note"))}</div>{pnl_html}</div>
    </div>

    <div style="margin-top:22px">
      <div class="cash-bar" aria-label="{_esc(_ui("dashboard.cash_bar_label"))}">
        <span class="seg risk" style="width:{invested_pct:.1f}%"></span>
        <span class="seg cash" style="width:{cash_pct:.1f}%"></span>
      </div>
      <div class="cash-legend">
        <span><i style="background:var(--ink)"></i>{_esc(_ui("dashboard.risk_legend", pct=invested_pct, value=invested).replace("$", _base_prefix(), 1))}</span>
        <span><i style="background:var(--accent-warm)"></i>{_esc(_ui("dashboard.cash_legend", pct=cash_pct, value=cash).replace("$", _base_prefix(), 1))}</span>
      </div>
    </div>
  </section>"""


_PROFIT_PANEL_PERIOD_KEYS = (
    ("1D",      "profit_panel.period_1d"),
    ("7D",      "profit_panel.period_7d"),
    ("MTD",     "profit_panel.period_mtd"),
    ("1M",      "profit_panel.period_1m"),
    ("YTD",     "profit_panel.period_ytd"),
    ("1Y",      "profit_panel.period_1y"),
    ("ALLTIME", "profit_panel.period_alltime"),
)


def _profit_panel_signed_money(value: Optional[float]) -> Tuple[str, str]:
    """Return (td_class, inner_text) for a signed money cell in the profit panel."""
    if value is None:
        return "", f'<span class="na">{_ui("common.na")}</span>'
    cls = "pos-txt" if value >= 0 else "neg-txt"
    sign = "+" if value >= 0 else "−"
    return cls, f"{sign}{_base_prefix()}{abs(value):,.0f}"


def _profit_panel_pct(value: Optional[float]) -> Tuple[str, str]:
    if value is None:
        return "", f'<span class="na">{_ui("common.na")}</span>'
    cls = "pos-txt" if value >= 0 else "neg-txt"
    sign = "+" if value >= 0 else "−"
    return cls, f"{sign}{abs(value):.2f}%"


def _profit_panel_net_flows_cell(
    value: Optional[float],
    *,
    null_as_dash: bool,
) -> Tuple[str, str]:
    """Flows column: n/a for missing aggregate; em dash when per-market flows are undefined (v1)."""
    if value is None and null_as_dash:
        return "muted", f'<span class="muted">{_esc(_ui("common.dash"))}</span>'
    return _profit_panel_signed_money(value)


def _profit_panel_thead_html() -> str:
    return f"""\
        <thead>
          <tr>
            <th>{_esc(_ui("profit_panel.col_period"))}</th>
            <th class="num">{_esc(_ui("profit_panel.col_pnl"))}</th>
            <th class="num">{_esc(_ui("profit_panel.col_return"))}</th>
            <th class="num">{_esc(_ui("profit_panel.col_realized"))}</th>
            <th class="num">{_esc(_ui("profit_panel.col_unrealized"))}</th>
            <th class="num">{_esc(_ui("profit_panel.col_flows"))}</th>
          </tr>
        </thead>"""


def _profit_panel_row_cells_for_source(
    row: Dict[str, Any],
    ui_key: str,
    boundary_html: str,
    *,
    flows_null_as_dash: bool,
    market: Optional[str] = None,
) -> str:
    """One <tr> for profit-panel table; `market` selects per_market_detail[market] when set."""
    if market is None:
        pnl_cls, pnl_html = _profit_panel_signed_money(row.get("pnl"))
        ret_cls, ret_html = _profit_panel_pct(row.get("return_pct"))
        rea_cls, rea_html = _profit_panel_signed_money(row.get("realized"))
        unr_cls, unr_html = _profit_panel_signed_money(row.get("unrealized_delta"))
        flw_cls, flw_inner = _profit_panel_net_flows_cell(row.get("net_flows"), null_as_dash=flows_null_as_dash)
    else:
        detail_root = row.get("per_market_detail") or {}
        src = detail_root.get(market) if isinstance(detail_root, dict) else None
        if not isinstance(src, dict):
            legacy_pm = row.get("per_market") or {}
            if market in legacy_pm:
                src = {
                    "pnl": legacy_pm.get(market),
                    "return_pct": None,
                    "realized": None,
                    "unrealized_delta": None,
                    "net_flows": None,
                }
            else:
                src = {
                    "pnl": None,
                    "return_pct": None,
                    "realized": None,
                    "unrealized_delta": None,
                    "net_flows": None,
                }
        pnl_cls, pnl_html = _profit_panel_signed_money(src.get("pnl"))
        ret_cls, ret_html = _profit_panel_pct(src.get("return_pct"))
        rea_cls, rea_html = _profit_panel_signed_money(src.get("realized"))
        unr_cls, unr_html = _profit_panel_signed_money(src.get("unrealized_delta"))
        flw_cls, flw_inner = _profit_panel_net_flows_cell(src.get("net_flows"), null_as_dash=flows_null_as_dash)

    return f"""\
      <tr>
        <td>{_esc(_ui(ui_key))}{boundary_html}</td>
        <td class="num {pnl_cls}">{pnl_html}</td>
        <td class="num {ret_cls}">{ret_html}</td>
        <td class="num {rea_cls}">{rea_html}</td>
        <td class="num {unr_cls}">{unr_html}</td>
        <td class="num {flw_cls}">{flw_inner}</td>
      </tr>"""


def _build_profit_panel_table_body_rows(
    rows: List[Dict[str, Any]],
    *,
    flows_null_as_dash: bool,
    market: Optional[str] = None,
) -> List[str]:
    body_rows: List[str] = []
    for key, ui_key in _PROFIT_PANEL_PERIOD_KEYS:
        row = next((r for r in rows if r.get("period") == key), None)
        if row is None:
            continue
        boundary = row.get("boundary")
        boundary_html = ""
        if boundary:
            boundary_html = (
                f' <span class="muted">({_esc(_ui("profit_panel.boundary_prefix"))} '
                f'{_esc(boundary)})</span>'
            )
        body_rows.append(
            _profit_panel_row_cells_for_source(
                row, ui_key, boundary_html,
                flows_null_as_dash=flows_null_as_dash,
                market=market,
            )
        )
    return body_rows


def render_profit_panel(context: Dict[str, Any]) -> str:
    """§10.1.5 — Profit panel: period P&L for 1D/7D/MTD/1M/YTD/1Y/ALLTIME.

    Consumes context['profit_panel'], normally copied from report_snapshot.json.
    When profit-panel rows are absent, the section is omitted; transaction
    analytics carry the primary performance view.
    """
    panel = context.get("profit_panel") or {}
    realized_unrealized = context.get("realized_unrealized") or {}

    rows = panel.get("rows") or []
    if not rows:
        return ""

    # KPI strip with lifetime realized + open unrealized when available.
    kpi_html = ""
    if realized_unrealized:
        realized = realized_unrealized.get("realized")
        unrealized = realized_unrealized.get("unrealized")
        r_cls, r_inner = _profit_panel_signed_money(realized if realized is not None else None)
        u_cls, u_inner = _profit_panel_signed_money(unrealized if unrealized is not None else None)
        kpi_html = f"""
    <div class="kpis">
      <div class="kpi"><div class="k">{_esc(_ui("profit_panel.lifetime_realized_label"))}</div>
        <div class="v {r_cls}">{r_inner}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("profit_panel.lifetime_unrealized_label"))}</div>
        <div class="v {u_cls}">{u_inner}</div></div>
    </div>"""

    body_rows = _build_profit_panel_table_body_rows(rows, flows_null_as_dash=False, market=None)

    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("profit_panel.title"))}</h2>
      <span class="sub">{_esc(_ui("profit_panel.subtitle", base=ACTIVE_BASE_CURRENCY))}</span>
    </div>{kpi_html}
    <div class="tbl-wrap" style="margin-top:14px">
      <table class="holdings-tbl">
{_profit_panel_thead_html()}
        <tbody>
{chr(10).join(body_rows)}
        </tbody>
      </table>
    </div>
  </section>"""


def _format_report_accuracy_detail(dim_id: str, detail: Any) -> str:
    if not isinstance(detail, dict):
        return ""
    if dim_id == "quote_coverage" or dim_id == "quote_freshness":
        w = int(detail.get("with_price") or 0)
        n = int(detail.get("tickers") or 0)
        return _ui(
            "report_accuracy.detail.quote_counts",
            with_price=w,
            total=n,
            fresh=int(detail.get("fresh") or 0),
            delayed=int(detail.get("delayed") or 0),
            stale=int(detail.get("stale") or 0),
        )
    if dim_id == "profit_boundary":
        return _ui(
            "report_accuracy.detail.boundary_counts",
            a=int(detail.get("no_historical_close") or 0),
            b=int(detail.get("no_close_and_no_latest") or 0),
            c=int(detail.get("missing_price") or 0),
            d=int(detail.get("unrealized_excluded") or 0),
            e=int(detail.get("using_current_latest") or 0),
            f=int(detail.get("no_fx_history") or 0),
        )
    if dim_id == "profit_reconciliation":
        mag = detail.get("max_abs_gap")
        mrg = detail.get("max_rel_gap")
        try:
            mag_f = float(mag) if mag is not None else 0.0
        except (TypeError, ValueError):
            mag_f = 0.0
        try:
            mrg_f = float(mrg) if mrg is not None else 0.0
        except (TypeError, ValueError):
            mrg_f = 0.0
        return _ui("report_accuracy.detail.recon", max_abs=mag_f, max_rel=mrg_f)
    if dim_id == "pipeline":
        return _ui("report_accuracy.detail.pipeline", n=int(detail.get("hard_errors") or 0))
    return ""


def render_report_accuracy(context: Dict[str, Any]) -> str:
    """§10.1.5a — Data quality scores (snapshot-computed, deterministic)."""
    block = context.get("report_accuracy")
    if not isinstance(block, dict):
        return ""
    overall = block.get("overall") or {}
    try:
        score = float(overall.get("score"))
    except (TypeError, ValueError):
        return ""
    band = str(overall.get("band") or "low")
    band_cls = {"high": "pos", "medium": "info", "low": "warn"}.get(band, "warn")
    band_key = f"report_accuracy.band.{band}"
    dims = block.get("dimensions") or []
    rows_html: List[str] = []
    for d in dims:
        if not isinstance(d, dict):
            continue
        did = str(d.get("id") or "")
        if not did:
            continue
        try:
            ds = float(d.get("score"))
        except (TypeError, ValueError):
            ds = float("nan")
        if ds != ds:  # NaN
            ds_str = _ui("common.na")
        else:
            ds_str = f"{ds:.1f}"
        title = _ui(f"report_accuracy.dim.{did}")
        detail = _format_report_accuracy_detail(did, d.get("detail"))
        rows_html.append(
            f"""<tr><td>{_esc(title)}</td><td class="num">{_esc(ds_str)}</td><td>{_esc(detail)}</td></tr>"""
        )
    if not rows_html:
        return ""
    meta = block.get("meta") if isinstance(block.get("meta"), dict) else {}
    miss_fx = meta.get("missing_fx_currencies") or []
    fx_note = ""
    if miss_fx:
        fx_note = (
            f'<div class="bucket-note"><b>{_esc(_ui("report_accuracy.missing_fx_label"))}:</b> '
            f"{_esc(', '.join(str(x) for x in miss_fx))}</div>"
        )
    return f"""\
  <section class="section" id="report-accuracy">
    <div class="section-head">
      <h2>{_esc(_ui("report_accuracy.title"))}</h2>
      <span class="sub">{_esc(_ui("report_accuracy.subtitle"))}</span>
    </div>
    <div class="kpis kpis-solo">
      <div class="kpi">
        <div class="k">{_esc(_ui("report_accuracy.overall_label"))}</div>
        <div class="v">{_esc(f"{score:.1f}")}</div>
        <div class="delta"><span class="tag {band_cls}">{_esc(_ui(band_key))}</span></div>
      </div>
    </div>
    <div class="tbl-wrap" style="margin-top:14px">
      <table class="holdings-tbl">
        <thead><tr>
          <th>{_esc(_ui("report_accuracy.col_dimension"))}</th>
          <th class="num">{_esc(_ui("report_accuracy.col_score"))}</th>
          <th>{_esc(_ui("report_accuracy.col_detail"))}</th>
        </tr></thead>
        <tbody>
{chr(10).join(rows_html)}
        </tbody>
      </table>
    </div>
    <div class="prose" style="margin-top:14px"><p class="muted">{_esc(_ui("report_accuracy.footer"))}</p></div>
    {fx_note}
  </section>"""


_GAP_GROUP_MAX = 12


def _gap_group_li(label: str, notes: List[str]) -> str:
    """Render a labeled group of audit notes as one parent <li> with a nested
    <ul class="gap-sublist"> so each note gets its own row. Multi-note groups
    must never be concatenated into a single bullet — that overflows the
    section width on long lists (see §10.11 rendering contract).
    """
    head = _GAP_GROUP_MAX
    visible = notes[:head]
    overflow = len(notes) - head
    sub = "".join(f'<li>{_esc(n)}</li>' for n in visible)
    if overflow > 0:
        sub += f'<li class="gap-overflow">+{overflow} more</li>'
    return (
        f'<li><b>{_esc(label)}:</b>'
        f'<ul class="gap-sublist">{sub}</ul>'
        f'</li>'
    )


def _profit_panel_audit_notes(context: Dict[str, Any]) -> List[str]:
    panel = context.get("profit_panel") or {}
    rows = panel.get("rows") or []
    notes: List[str] = []
    for row in rows:
        for line in row.get("audit", []) or []:
            if line and line not in notes:
                notes.append(line)
    for line in panel.get("open_position_audit", []) or []:
        if line and line not in notes:
            notes.append(line)
    for line in panel.get("issues", []) or []:
        if line and line not in notes:
            notes.append(line)
    return notes


def _transaction_analytics(context: Dict[str, Any]) -> Dict[str, Any]:
    payload = context.get("transaction_analytics") or context.get("analytics") or {}
    return payload if isinstance(payload, dict) else {}


def _analytics_pct(value: Optional[float]) -> str:
    if value is None:
        return _ui("common.na")
    sign = "+" if value >= 0 else "−"
    return f"{sign}{abs(value):.2f}%"


def _analytics_plain_pct(value: Optional[float]) -> str:
    if value is None:
        return _ui("common.na")
    return f"{value:.2f}%"


def _analytics_money(value: Optional[float]) -> str:
    return _fmt_money(value)


def _asset_class_label(key: str) -> str:
    translated = _ui(f"analytics.asset_class_{key}")
    return translated if translated != f"analytics.asset_class_{key}" else key


# Stable column order for the per-market period P&L matrix. Markets that appear
# in the data are kept in this order; anything outside the list is appended in
# alphabetical order so unfamiliar markets still render.
_MARKET_COLUMN_ORDER: Tuple[str, ...] = (
    "us", "tw", "two", "jp", "hk", "lse", "crypto", "fx", "cash", "other",
)


def _ordered_market_columns(periods: List[Dict[str, Any]]) -> List[str]:
    seen = set()
    for row in periods:
        for k in (row.get("per_market") or {}).keys():
            seen.add(k)
        detail = row.get("per_market_detail")
        if isinstance(detail, dict):
            for k in detail.keys():
                seen.add(k)
    ordered = [m for m in _MARKET_COLUMN_ORDER if m in seen]
    extras = sorted(m for m in seen if m not in _MARKET_COLUMN_ORDER)
    return ordered + extras


# Show "unallocated P&L" block when portfolio row P&L vs sum(per_market_detail) exceeds this (base ccy).
_MARKET_PNL_RESIDUAL_THRESHOLD = 0.015


def render_performance_attribution(context: Dict[str, Any]) -> str:
    analytics = _transaction_analytics(context)
    perf = analytics.get("performance_attribution") or {}
    if not perf:
        return ""
    periods = perf.get("periods") or []
    contributors = perf.get("top_contributors") or []
    detractors = perf.get("top_detractors") or []

    best = contributors[0] if contributors else {}
    worst = detractors[0] if detractors else {}
    best_label = f'{best.get("ticker", _ui("common.na"))} {_analytics_money(best.get("total_pnl"))}' if best else _ui("common.na")
    worst_label = f'{worst.get("ticker", _ui("common.na"))} {_analytics_money(worst.get("total_pnl"))}' if worst else _ui("common.na")
    mwr = perf.get("money_weighted_return_annualized")

    panel_rows = (context.get("profit_panel") or {}).get("rows") or []
    attr_rows: List[Dict[str, Any]] = panel_rows if panel_rows else periods

    market_tables_html = ""
    market_cols = _ordered_market_columns(attr_rows)
    if attr_rows and market_cols:
        blocks: List[str] = []
        for m in market_cols:
            m_body = _build_profit_panel_table_body_rows(
                attr_rows, flows_null_as_dash=True, market=m,
            )
            blocks.append(
                f"""
    <div class="subsection" style="margin-top:20px">
      <h3 class="eyebrow">{_esc(_asset_class_label(m))}</h3>
      <div class="tbl-wrap" style="margin-top:8px">
        <table class="holdings-tbl">
{_profit_panel_thead_html()}
          <tbody>
{chr(10).join(m_body)}
          </tbody>
        </table>
      </div>
    </div>"""
            )

        residual_lines: List[str] = []
        for key, ui_key in _PROFIT_PANEL_PERIOD_KEYS:
            row = next((r for r in attr_rows if r.get("period") == key), None)
            if row is None:
                continue
            row_pnl = row.get("pnl")
            if row_pnl is None:
                continue
            det = row.get("per_market_detail") or {}
            sum_m = 0.0
            if isinstance(det, dict):
                for _bk, sub in det.items():
                    if isinstance(sub, dict) and sub.get("pnl") is not None:
                        sum_m += float(sub["pnl"])
            residual = float(row_pnl) - sum_m
            if abs(residual) <= _MARKET_PNL_RESIDUAL_THRESHOLD:
                continue
            boundary = row.get("boundary")
            bh = ""
            if boundary:
                bh = (
                    f' <span class="muted">({_esc(_ui("profit_panel.boundary_prefix"))} '
                    f'{_esc(boundary)})</span>'
                )
            r_cls, r_inner = _profit_panel_signed_money(round(residual, 2))
            residual_lines.append(
                f"      <tr><td>{_esc(_ui(ui_key))}{bh}</td>"
                f'<td class="num {r_cls}">{r_inner}</td></tr>'
            )

        if residual_lines:
            blocks.append(
                f"""
    <div class="subsection" style="margin-top:20px">
      <h3 class="eyebrow">{_esc(_ui("analytics.market_residual_title"))}</h3>
      <div class="tbl-wrap" style="margin-top:8px">
        <table class="holdings-tbl">
          <thead>
            <tr>
              <th>{_esc(_ui("profit_panel.col_period"))}</th>
              <th class="num">{_esc(_ui("analytics.market_residual_col_pnl"))}</th>
            </tr>
          </thead>
          <tbody>
{chr(10).join(residual_lines)}
          </tbody>
        </table>
      </div>
    </div>"""
            )

        foot = _esc(_ui("analytics.market_tables_footnote", base=ACTIVE_BASE_CURRENCY))
        market_tables_html = (
            f'{"".join(blocks)}'
            f'<div class="prose" style="margin-top:16px"><p>{foot}</p></div>'
        )

    def _bars(items: List[Dict[str, Any]]) -> str:
        if not items:
            return f'<div class="prose"><p class="muted">{_esc(_ui("common.na"))}</p></div>'
        max_abs = max(abs(float(i.get("total_pnl") or 0)) for i in items) or 1.0
        out = []
        for item in items:
            value = float(item.get("total_pnl") or 0)
            width = abs(value) / max_abs * 100.0
            cls = "pos" if value >= 0 else "neg"
            txt_cls = "pos-txt" if value >= 0 else "neg-txt"
            sign = "+" if value >= 0 else "−"
            out.append(
                f'<div class="bar-row"><div class="bar-label">{_esc(str(item.get("ticker") or ""))}</div>'
                f'<div class="bar-track"><div class="bar {cls}" style="width:{width:.1f}%"></div></div>'
                f'<div class="bar-value {txt_cls}">{sign}{_base_prefix()}{abs(value):,.0f}</div></div>'
            )
        return "".join(out)

    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("analytics.performance_title"))}</h2>
      <span class="sub">{_esc(_ui("analytics.market_breakdown_subtitle", base=ACTIVE_BASE_CURRENCY))}</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="k">{_esc(_ui("analytics.ending_nav"))}</div><div class="v">{_analytics_money(perf.get("ending_nav"))}</div><div class="delta">{_esc(_ui("analytics.ending_nav_note"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("analytics.mwr"))}</div><div class="v">{_analytics_pct(mwr) if mwr is not None else _ui("common.na")}</div><div class="delta">{_esc(_ui("analytics.mwr_note"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("analytics.best_contributor"))}</div><div class="v">{_esc(best_label)}</div><div class="delta">{_esc(_ui("analytics.lifetime_basis"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("analytics.worst_detractor"))}</div><div class="v">{_esc(worst_label)}</div><div class="delta">{_esc(_ui("analytics.lifetime_basis"))}</div></div>
    </div>{market_tables_html}
    <div class="cols-2" style="margin-top:22px">
      <div><div class="eyebrow" style="margin-bottom:10px">{_esc(_ui("analytics.top_contributors"))}</div><div class="bars">{_bars(contributors)}</div></div>
      <div><div class="eyebrow" style="margin-bottom:10px">{_esc(_ui("analytics.top_detractors"))}</div><div class="bars">{_bars(detractors)}</div></div>
    </div>
  </section>"""


def render_trade_quality(context: Dict[str, Any]) -> str:
    analytics = _transaction_analytics(context)
    tq = analytics.get("trade_quality") or {}
    if not tq:
        return ""
    activity = tq.get("recent_activity") or []
    if not activity:
        # Back-compat: synthesize from sell_followups + buy_followups so older
        # snapshots without a `recent_activity` field still render something.
        legacy: List[Dict[str, Any]] = []
        for s in tq.get("sell_followups") or []:
            legacy.append({
                "date": s.get("sell_date"), "action": "SELL", "ticker": s.get("ticker"),
                "qty": s.get("qty"), "price": s.get("sell_price"),
                "realized": s.get("realized"),
                "after_30d_pct": s.get("after_30d_pct"),
                "after_90d_pct": s.get("after_90d_pct"),
            })
        for b in tq.get("buy_followups") or []:
            legacy.append({
                "date": b.get("buy_date"), "action": "BUY", "ticker": b.get("ticker"),
                "qty": b.get("qty"), "price": b.get("buy_price"),
                "after_30d_pct": b.get("after_30d_pct"),
                "after_90d_pct": b.get("after_90d_pct"),
            })
        legacy.sort(key=lambda r: r.get("date") or "", reverse=True)
        activity = legacy

    rows = []
    for item in activity[:10]:
        action = str(item.get("action") or "")
        action_cls = "pos-txt" if action == "SELL" else "neg-txt" if action == "BUY" else ""
        action_label = _ui(f"analytics.action_{action.lower()}") if action else ""
        if action_label.startswith("analytics."):
            action_label = action  # i18n key missing → fall back to literal
        qty_str = ""
        qty = item.get("qty")
        if qty is not None:
            try:
                qty_str = f"{float(qty):,.4g}"
            except (TypeError, ValueError):
                qty_str = str(qty)
        price_str = ""
        price = item.get("price")
        if price is not None:
            try:
                price_str = f"{float(price):,.2f}"
            except (TypeError, ValueError):
                price_str = str(price)
        realized = item.get("realized")
        realized_html = _analytics_money(realized) if realized is not None else f'<span class="muted">{_esc(_ui("common.dash"))}</span>'

        def _drift_cell(pct):
            if pct is None:
                return f'<td class="num"><span class="muted">{_esc(_ui("common.na"))}</span></td>'
            cls = "pos-txt" if pct >= 0 else "neg-txt"
            sign = "+" if pct >= 0 else "−"
            return f'<td class="num {cls}">{sign}{abs(pct):.2f}%</td>'

        rows.append(
            f"""\
      <tr>
        <td>{_esc(str(item.get("date") or ""))}</td>
        <td><span class="adj-action {action.lower()}">{_esc(action_label)}</span></td>
        <td><span class="sym-trigger" tabindex="0" role="button">{_esc(str(item.get("ticker") or ""))}</span></td>
        <td class="num">{_esc(qty_str)}</td>
        <td class="num">{_esc(price_str)}</td>
        <td class="num">{realized_html}</td>
        {_drift_cell(item.get("after_30d_pct"))}
        {_drift_cell(item.get("after_90d_pct"))}
      </tr>"""
        )

    body = (
        chr(10).join(rows)
        if rows else
        f'<tr><td colspan="8" class="na" style="text-align:center;padding:14px">{_esc(_ui("analytics.no_recent_activity"))}</td></tr>'
    )

    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("analytics.trade_quality_title"))}</h2>
      <span class="sub">{_esc(_ui("analytics.recent_activity_subtitle"))}</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="k">{_esc(_ui("analytics.closed_lots"))}</div><div class="v">{_esc(str(tq.get("closed_lot_count", 0)))}</div><div class="delta">{_esc(_ui("analytics.closed_lots_note"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("analytics.win_rate"))}</div><div class="v">{_analytics_plain_pct(tq.get("win_rate_pct")) if tq.get("win_rate_pct") is not None else _ui("common.na")}</div><div class="delta">{_esc(_ui("analytics.sell_lot_basis"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("analytics.profit_factor"))}</div><div class="v">{_esc(str(tq.get("profit_factor") if tq.get("profit_factor") is not None else _ui("common.na")))}</div><div class="delta">{_esc(_ui("analytics.profit_factor_note"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("analytics.avg_hold_days"))}</div><div class="v">{_esc(str(tq.get("avg_hold_days") if tq.get("avg_hold_days") is not None else _ui("common.na")))}</div><div class="delta">{_esc(_ui("analytics.sell_lot_basis"))}</div></div>
    </div>
    <div class="tbl-wrap scroll-y" style="margin-top:18px">
      <table>
        <thead><tr>
          <th>{_esc(_ui("analytics.activity_date"))}</th>
          <th>{_esc(_ui("analytics.activity_action"))}</th>
          <th>{_esc(_ui("adjustments.ticker"))}</th>
          <th class="num">{_esc(_ui("analytics.activity_qty"))}</th>
          <th class="num">{_esc(_ui("analytics.activity_price"))}</th>
          <th class="num">{_esc(_ui("analytics.realized"))}</th>
          <th class="num">{_esc(_ui("analytics.after_30d"))}</th>
          <th class="num">{_esc(_ui("analytics.after_90d"))}</th>
        </tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
  </section>"""


def render_discipline_check(context: Dict[str, Any]) -> str:
    analytics = _transaction_analytics(context)
    dc = analytics.get("discipline_check") or {}
    if not dc:
        return ""
    weights = dc.get("top_position_weights") or []
    recent = dc.get("recent_buy_counts_30d") or []
    stale = dc.get("short_bucket_over_1y") or []
    cost_flags = dc.get("latest_lot_cost_flags") or []
    losses = dc.get("largest_unrealized_losses") or []
    gains = dc.get("largest_unrealized_gains") or []
    gaps = dc.get("data_gaps") or []

    top_weight = weights[0] if weights else {}
    weight_label = (
        f'{top_weight.get("ticker")} {top_weight.get("weight_pct"):.1f}%'
        if top_weight and top_weight.get("weight_pct") is not None else _ui("common.na")
    )

    def _simple_list(items: List[str]) -> str:
        if not items:
            return f'<li>{_esc(_ui("common.na"))}</li>'
        return "".join(f"<li>{_esc(str(i))}</li>" for i in items)

    weight_rows = "".join(
        f'<tr><td>{_esc(str(i.get("ticker") or ""))}</td><td class="num">{i.get("weight_pct"):.2f}%</td></tr>'
        for i in weights if i.get("weight_pct") is not None
    )
    recent_items = [f'{i.get("ticker")} x{i.get("count")}' for i in recent]
    stale_items = [f'{i.get("ticker")} {i.get("acq_date")} ({i.get("hold_days")}d)' for i in stale]
    cost_items = [
        f'{i.get("ticker")} {i.get("newest_date")}: +{i.get("premium_pct")}% vs older avg'
        for i in cost_flags
    ]

    def _lot_rows(items: List[Dict[str, Any]]) -> str:
        if not items:
            return f'<tr><td colspan="4">{_esc(_ui("common.na"))}</td></tr>'
        return "".join(
            f'<tr><td>{_esc(str(i.get("ticker") or ""))}</td><td>{_esc(str(i.get("acq_date") or ""))}</td>'
            f'<td class="num">{_analytics_money(i.get("unrealized"))}</td>'
            f'<td class="num">{_analytics_pct(i.get("unrealized_pct")) if i.get("unrealized_pct") is not None else _ui("common.na")}</td></tr>'
            for i in items[:6]
        )

    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("analytics.discipline_title"))}</h2>
      <span class="sub">{_esc(_ui("analytics.discipline_subtitle"))}</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="k">{_esc(_ui("analytics.deposit_to_buy"))}</div><div class="v">{_esc(str(dc.get("avg_days_deposit_to_buy") if dc.get("avg_days_deposit_to_buy") is not None else _ui("common.na")))}</div><div class="delta">{_esc(_ui("analytics.days"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("analytics.sell_to_buy"))}</div><div class="v">{_esc(str(dc.get("avg_days_sell_to_buy") if dc.get("avg_days_sell_to_buy") is not None else _ui("common.na")))}</div><div class="delta">{_esc(_ui("analytics.days"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("analytics.top_weight"))}</div><div class="v">{_esc(weight_label)}</div><div class="delta">{_esc(_ui("analytics.current_open_book"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("analytics.data_gaps"))}</div><div class="v">{len(gaps)}</div><div class="delta">{_esc(_ui("sources.gaps_heading"))}</div></div>
    </div>
    <div class="cols-2" style="margin-top:18px">
      <div>
        <div class="eyebrow" style="margin-bottom:10px">{_esc(_ui("analytics.top_position_weights"))}</div>
        <div class="tbl-wrap scroll-y"><table><tbody>{weight_rows or f'<tr><td>{_esc(_ui("common.na"))}</td></tr>'}</tbody></table></div>
      </div>
      <div>
        <div class="bucket-note"><b>{_esc(_ui("analytics.recent_churn"))}:</b><ul>{_simple_list(recent_items)}</ul></div>
        <div class="bucket-note"><b>{_esc(_ui("analytics.short_stale"))}:</b><ul>{_simple_list(stale_items)}</ul></div>
        <div class="bucket-note"><b>{_esc(_ui("analytics.high_cost_adds"))}:</b><ul>{_simple_list(cost_items)}</ul></div>
      </div>
    </div>
    <div class="cols-2" style="margin-top:18px">
      <div class="tbl-wrap scroll-y"><table><thead><tr><th>{_esc(_ui("analytics.loss_lots"))}</th><th>{_esc(_ui("price_pop.acquired"))}</th><th class="num">{_esc(_ui("price_pop.pnl"))}</th><th class="num">%</th></tr></thead><tbody>{_lot_rows(losses)}</tbody></table></div>
      <div class="tbl-wrap scroll-y"><table><thead><tr><th>{_esc(_ui("analytics.gain_lots"))}</th><th>{_esc(_ui("price_pop.acquired"))}</th><th class="num">{_esc(_ui("price_pop.pnl"))}</th><th class="num">%</th></tr></thead><tbody>{_lot_rows(gains)}</tbody></table></div>
    </div>
  </section>"""


# --------------------------------------------------------------------------- #
# §10.1.7 Trading-psychology evaluation
#
# Editorial section authored by the agent during report generation. Schema:
#
#   context["trading_psychology"] = {
#     "headline":     str,                       # 1-line summary (≤ 80 chars)
#     "observations": [{"behavior", "evidence", "tone"}],  # 2-4 items
#     "improvements": [{"issue", "suggestion", "priority"}],  # 2-4 items
#     "strengths":    [str | {"behavior", "evidence"}],   # optional 0-2 items
#   }
#
# `tone ∈ {pos, neu, warn, neg}`; `priority ∈ {high, medium, low}`.
# The CLI render path hard-fails when the field is missing; the fallback below
# is defensive for direct function callers only.
# --------------------------------------------------------------------------- #

_PSYCH_TONE_CLASS = {"pos": "pos", "neu": "info", "warn": "warn", "neg": "neg"}
_PSYCH_PRIORITY_CLASS = {"high": "warn", "medium": "info", "low": "neu"}


def _psych_tone_chip(tone: Optional[str]) -> str:
    cls = _PSYCH_TONE_CLASS.get(str(tone or "neu").lower(), "info")
    label_key = f"psychology.tone_{str(tone or 'neu').lower()}"
    label = _ui(label_key)
    if label.startswith("psychology."):
        label = str(tone or "")
    return f'<span class="tag {cls}">{_esc(label)}</span>' if label else ""


def _psych_priority_chip(priority: Optional[str]) -> str:
    cls = _PSYCH_PRIORITY_CLASS.get(str(priority or "medium").lower(), "info")
    label_key = f"psychology.priority_{str(priority or 'medium').lower()}"
    label = _ui(label_key)
    if label.startswith("psychology."):
        label = str(priority or "")
    return f'<span class="tag {cls}">{_esc(label)}</span>' if label else ""


def render_trading_psychology(context: Dict[str, Any]) -> str:
    """Render §10.1.7 — agent's read of recent trading mindset + improvements.

    The section sits between the transaction-history evidence (§10.1.5/6) and
    the holdings table so the user sees: facts → reflection → positions.
    """
    payload = context.get("trading_psychology") or {}
    title = _ui("psychology.title")
    subtitle = _ui("psychology.subtitle")

    if not isinstance(payload, dict) or not payload:
        return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(title)}</h2>
      <span class="sub">{_esc(subtitle)}</span>
    </div>
    <div class="prose"><p class="muted">{_esc(_ui("psychology.placeholder"))}</p></div>
  </section>"""

    headline = str(payload.get("headline") or "").strip()
    observations = payload.get("observations") or []
    improvements = payload.get("improvements") or []
    strengths = payload.get("strengths") or []
    rp_label = _ui("reviewer.note_label")

    headline_html = ""
    if headline:
        headline_html = (
            f'<div class="prose psych-headline">'
            f'<p>{_esc(headline)}</p>'
            f'</div>'
        )

    def _observation_row(item: Any) -> str:
        if isinstance(item, str):
            return f'<li>{_esc(item)}</li>'
        if not isinstance(item, dict):
            return ""
        behavior = str(item.get("behavior") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        tone = item.get("tone")
        chip = _psych_tone_chip(tone)
        evidence_html = (
            f'<div class="psych-evidence">'
            f'<span class="psych-ev-prefix">{_esc(_ui("psychology.evidence_prefix"))}</span>'
            f'{_esc(evidence)}'
            f'</div>'
        ) if evidence else ""
        return (
            f'<li>'
            f'<div class="psych-li-main">{chip}<span style="margin-left:6px">{_esc(behavior)}</span></div>'
            f'{evidence_html}'
            f'</li>'
        )

    def _improvement_row(item: Any) -> str:
        if isinstance(item, str):
            return f'<li>{_esc(item)}</li>'
        if not isinstance(item, dict):
            return ""
        issue = str(item.get("issue") or "").strip()
        suggestion = str(item.get("suggestion") or "").strip()
        priority = item.get("priority")
        chip = _psych_priority_chip(priority)
        suggestion_html = (
            f'<div class="psych-suggestion">'
            f'<span class="psych-suggestion-label">{_esc(_ui("psychology.suggestion_prefix"))}</span>'
            f'{_esc(suggestion)}'
            f'</div>'
        ) if suggestion else ""
        return (
            f'<li>'
            f'<div class="psych-li-main">{chip}<span style="margin-left:6px">{_esc(issue)}</span></div>'
            f'{suggestion_html}'
            f'</li>'
        )

    obs_html = (
        "".join(_observation_row(i) for i in observations)
        or f'<li class="muted">{_esc(_ui("psychology.no_observations"))}</li>'
    )
    imp_html = (
        "".join(_improvement_row(i) for i in improvements)
        or f'<li class="muted">{_esc(_ui("psychology.no_improvements"))}</li>'
    )
    strengths_html = ""
    if strengths:
        strengths_items = "".join(
            f'<li>{_esc(s if isinstance(s, str) else (s.get("behavior") or ""))}</li>'
            for s in strengths
        )
        strengths_html = (
            f'<div class="psych-strengths-wrap">'
            f'<div class="eyebrow" style="margin-bottom:8px">{_esc(_ui("psychology.strengths_label"))}</div>'
            f'<ul class="psych-list">{strengths_items}</ul>'
            f'</div>'
        )

    rp_notes = _reviewer_pass(context)["by_section"].get("trading_psychology") or []
    reviewer_block = _render_reviewer_notes(rp_notes, rp_label)

    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(title)}</h2>
      <span class="sub">{_esc(subtitle)}</span>
    </div>
    {headline_html}
    <div class="cols-2" style="align-items:start">
      <div>
        <div class="eyebrow" style="margin-bottom:10px">{_esc(_ui("psychology.observations_label"))}</div>
        <ul class="psych-list">{obs_html}</ul>
      </div>
      <div>
        <div class="eyebrow" style="margin-bottom:10px">{_esc(_ui("psychology.improvements_label"))}</div>
        <ul class="psych-list">{imp_html}</ul>
      </div>
    </div>
    {strengths_html}
    {reviewer_block}
  </section>"""


_ALLOCATION_PALETTE = [
    "#1f2937",  # ink
    "#15703d",  # pos
    "#8a5a1c",  # accent-warm
    "#1d4690",  # info
    "#b15309",  # warn
    "#b42318",  # neg
    "#8a8f99",  # muted-2
    "#6b7280",  # muted
]

_ALLOCATION_CATEGORIES = (
    # (key, ui_label_key)
    ("us",     "allocation.cat_us"),
    ("crypto", "allocation.cat_crypto"),
    ("cash",   "allocation.cat_cash"),
    ("tw",     "allocation.cat_tw"),
    ("jp",     "allocation.cat_jp"),
    ("hk",     "allocation.cat_hk"),
    ("lse",    "allocation.cat_lse"),
    ("fx",     "allocation.cat_fx"),
    ("other",  "allocation.cat_other"),
)


def _allocation_category_key(agg: TickerAggregate) -> str:
    if agg.is_cash:
        return "cash"
    m = agg.market
    if m == MarketType.US:
        return "us"
    if m == MarketType.CRYPTO:
        return "crypto"
    if m in (MarketType.TW, MarketType.TWO):
        return "tw"
    if m == MarketType.JP:
        return "jp"
    if m == MarketType.HK:
        return "hk"
    if m == MarketType.LSE:
        return "lse"
    if m == MarketType.FX:
        return "fx"
    return "other"


def _format_total_compact(value: float) -> str:
    bp = _base_prefix()
    if value >= 1_000_000:
        return f"{bp}{value/1_000_000:.1f}M"
    if value >= 1_000:
        return f"{bp}{value/1_000:.0f}k"
    return f"{bp}{value:.0f}"


def render_allocation_and_weight(
    aggs: Dict[str, TickerAggregate],
    total_assets: float,
    today: _dt.date,
) -> str:
    """§10.1 — Allocation donut + top-N weight bars (matches sample lines 807-858)."""
    if total_assets <= 0:
        return ""

    # 1) Aggregate market values per category, drop empty buckets, sort by value desc.
    sums: Dict[str, float] = {}
    for agg in aggs.values():
        if agg.market_value is None or agg.market_value <= 0:
            continue
        sums[_allocation_category_key(agg)] = sums.get(
            _allocation_category_key(agg), 0.0
        ) + agg.market_value

    cats: List[Tuple[str, str, float, float]] = []  # (label, color, value, pct)
    for key, ui_key in _ALLOCATION_CATEGORIES:
        v = sums.get(key, 0.0)
        if v <= 0:
            continue
        cats.append((_ui(ui_key), "", v, v / total_assets * 100.0))
    cats.sort(key=lambda c: -c[2])
    cats = [
        (label, _ALLOCATION_PALETTE[i % len(_ALLOCATION_PALETTE)], v, pct)
        for i, (label, _, v, pct) in enumerate(cats)
    ]

    # 2) Donut SVG arcs — circumference at r=42 ≈ 263.89 (matches sample numbers).
    import math
    circumference = 2 * math.pi * 42
    offset = 0.0
    arcs: List[str] = []
    for label, color, _v, pct in cats:
        seg_len = pct / 100.0 * circumference
        arcs.append(
            f'<circle cx="60" cy="60" r="42" stroke="{color}"\n'
            f'                      stroke-dasharray="{seg_len:.2f} {circumference:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}"/>'
        )
        offset += seg_len
    arcs_html = "\n              ".join(arcs)

    legend_rows = "\n            ".join(
        f'<div class="row"><span class="sw" style="background:{color}"></span>'
        f'<span>{_esc(label)}</span><span class="pct">{pct:.1f}%</span></div>'
        for label, color, _v, pct in cats
    )

    total_label = _format_total_compact(total_assets)

    # 3) Top-N bars (max 10) — width relative to the largest weight, like the sample.
    holdings = sorted(
        (a for a in aggs.values() if a.market_value is not None and a.market_value > 0),
        key=lambda a: -(a.market_value or 0),
    )[:10]
    bar_rows: List[str] = []
    if holdings:
        max_pct = max(h.market_value / total_assets * 100.0 for h in holdings) or 1.0
        for h in holdings:
            pct = h.market_value / total_assets * 100.0
            width = pct / max_pct * 100.0
            bar_rows.append(
                f'<div class="bar-row">'
                f'<div class="bar-label">{_esc(h.ticker)}</div>'
                f'<div class="bar-track"><div class="bar" style="width:{width:.1f}%"></div></div>'
                f'<div class="bar-value">{pct:.1f}%</div>'
                f'</div>'
            )
    bars_html = "\n          ".join(bar_rows)

    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("allocation.title"))}</h2>
      <span class="sub">{_esc(_ui("allocation.subtitle", date=today.isoformat(), base=ACTIVE_BASE_CURRENCY))}</span>
    </div>
    <div class="cols-2">
      <div>
        <div class="donut-wrap">
          <svg viewBox="0 0 120 120" aria-label="{_esc(_ui("allocation.donut_label"))}">
            <circle cx="60" cy="60" r="52" fill="#f0ece0"/>
            <g transform="rotate(-90 60 60)" fill="none" stroke-width="20">
              {arcs_html}
            </g>
            <text x="60" y="56" text-anchor="middle"
                  font-size="8" fill="#6b7280" letter-spacing=".15em">{_esc(_ui("allocation.total_label"))}</text>
            <text x="60" y="72" text-anchor="middle"
                  font-size="14" font-weight="650" fill="#15191f">{_esc(total_label)}</text>
          </svg>
          <div class="legend">
            {legend_rows}
          </div>
        </div>
      </div>
      <div>
        <div class="bars">
          {bars_html}
        </div>
      </div>
    </div>
  </section>"""


def _build_holdings_action_map(context: Dict[str, Any]) -> Dict[str, str]:
    """Build ticker → action text map for the holdings-table action column.

    Priority:
      1. `context["holdings_actions"]` — explicit per-ticker override `{ticker: text}`.
      2. `context["adjustments"]` — derive `"<action_label>；<trigger>"` per ticker.

    Both sources may coexist; the explicit map wins on conflict.
    """
    explicit = context.get("holdings_actions") or {}
    out: Dict[str, str] = {}
    for adj in context.get("adjustments") or []:
        ticker = (adj.get("ticker") or "").strip()
        if not ticker:
            continue
        label = (adj.get("action_label") or "").strip()
        trigger = (adj.get("trigger") or "").strip()
        text = "；".join(p for p in (label, trigger) if p)
        if text:
            out[ticker] = text
    if isinstance(explicit, dict):
        for k, v in explicit.items():
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()
    return out


def render_holdings_table(
    aggs: Dict[str, TickerAggregate],
    total_assets: float,
    prices: Dict[str, Any],
    today: _dt.date,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """Render the holdings table — emits one row per ticker, no truncation.

    The wrap intentionally does NOT use `.scroll-y` because cells contain popovers
    that must escape the wrap on desktop. Section height grows naturally with the
    number of holdings; the user accepts this trade-off in exchange for popover
    interactivity.
    """
    rows: List[str] = []
    sorted_aggs = sorted(aggs.values(), key=lambda a: -(a.market_value or 0))
    action_by_ticker = _build_holdings_action_map(context or {})
    for agg in sorted_aggs:
        weight_pct = (agg.market_value / total_assets * 100.0) if (agg.market_value and total_assets) else None
        weight_html = f"{weight_pct:.1f}%" if weight_pct is not None else f'<span class="na">{_ui("common.na")}</span>'
        value_html = _fmt_money(agg.market_value)
        if agg.is_cash:
            pnl_td_class, pnl_html = "", _ui("common.dash")
        else:
            pnl_td_class, pnl_html = _fmt_signed_parts(agg.pnl_amount, agg.pnl_pct)
        pnl_td_class_attr = f" {pnl_td_class}" if pnl_td_class else ""
        price_html, price_sub_html = _price_cell_pieces(agg, prices)
        sym_pop = _symbol_popover(agg, today)
        price_pop = _price_popover(agg, prices)
        action_text = action_by_ticker.get(agg.ticker)
        action = _esc(action_text) if action_text else _ui("common.dash")
        rows.append(f"""\
          <tr>
            <td><div class="sym-trigger" tabindex="0" role="button">{_esc(agg.ticker)}{sym_pop}</div></td>
            <td>{_category_chip(agg)}</td>
            <td class="num price-cell"><div class="price-trigger" tabindex="0" role="button">{price_html}{price_sub_html}{price_pop}</div></td>
            <td class="num">{weight_html}</td>
            <td class="num">{value_html}</td>
            <td class="num{pnl_td_class_attr}">{pnl_html}</td>
            <td class="col-action">{action}</td>
          </tr>""")
    body = "\n".join(rows)
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("holdings.title"))}</h2>
      <span class="sub">{_esc(_ui("holdings.subtitle", count=len(sorted_aggs)))}</span>
    </div>
    <div class="tbl-wrap">
      <table class="holdings-tbl">
        <colgroup>
          <col style="width:7%">
          <col style="width:12%">
          <col style="width:14%">
          <col style="width:7%">
          <col style="width:11%">
          <col style="width:19%">
          <col style="width:30%">
        </colgroup>
        <thead>
          <tr>
            <th>{_esc(_ui("holdings.symbol"))}</th>
            <th>{_esc(_ui("holdings.category"))}</th>
            <th class="num">{_esc(_ui("holdings.latest_price"))}</th>
            <th class="num">{_esc(_ui("holdings.weight"))}</th>
            <th class="num">{_esc(_ui("holdings.value"))}</th>
            <th class="num">{_esc(_ui("holdings.pnl"))}</th>
            <th class="col-action">{_esc(_ui("holdings.action"))}</th>
          </tr>
        </thead>
        <tbody>
{body}
        </tbody>
      </table>
    </div>
  </section>"""


def _price_cell_pieces(agg: TickerAggregate, prices: Dict[str, Any]) -> Tuple[str, str]:
    if agg.is_cash:
        return f'<span class="na">{_ui("common.dash")}</span>', ""
    if agg.latest_price is None:
        return f'<span class="na">{_ui("common.na")}</span>', ""
    # §9.0 — the visible market price keeps the native trade currency prefix; the
    # row's `市值` cell (rendered in render_holdings_table) is the USD aggregate.
    pfx = CURRENCY_PREFIX.get(agg.trade_currency.upper(), f"{agg.trade_currency} ")
    price = f'<span class="price-num">{pfx}{agg.latest_price:,.2f}</span>'
    if agg.move_pct is None:
        return price, ""
    cls = "pos" if agg.move_pct >= 0 else "neg"
    sign = "+" if agg.move_pct >= 0 else "−"
    move_prefix = _ui("price_pop.move_24h") if agg.market == MarketType.CRYPTO else _ui("price_pop.move_vs_prior")
    sub = f'<span class="price-sub {cls}">{_esc(move_prefix)} {sign}{abs(agg.move_pct):.2f}%</span>'
    return price, sub


def _category_chip(agg: TickerAggregate) -> str:
    if agg.is_cash:
        return f'{_esc(_ui("category.cash"))}<span class="tag">{_esc(_ui("category.chip_cash"))}</span>'
    chips = {
        MarketType.US: (_ui("category.us"), ""),
        MarketType.CRYPTO: (_ui("category.crypto"), "warn"),
        MarketType.TW: (_ui("category.tw"), ""),
        MarketType.TWO: (_ui("category.two"), ""),
        MarketType.JP: (_ui("category.jp"), ""),
        MarketType.HK: (_ui("category.hk"), ""),
        MarketType.LSE: (_ui("category.lse"), ""),
    }.get(agg.market, (_ui("category.asset"), ""))
    label, cls = chips
    bucket_chip = {
        "long": f'<span class="tag pos">{_esc(_ui("category.chip_long"))}</span>',
        "mid": f'<span class="tag">{_esc(_ui("category.chip_mid"))}</span>',
        "short": f'<span class="tag warn">{_esc(_ui("category.chip_short"))}</span>',
    }.get(_bucket_key(agg.bucket), "")
    return f"{label}{bucket_chip}"


def _symbol_popover(agg: TickerAggregate, today: _dt.date) -> str:
    hold = hold_period_label(agg.earliest_date, today)
    since = (agg.earliest_date or "").rsplit("-", 1)[0] if agg.earliest_date else _ui("common.na")
    return f"""<div class="pop pop-sym" role="tooltip">
                <h4>{_esc(agg.ticker)} · {_esc(_translate_bucket(agg.bucket))}</h4>
                <div class="pop-sub">{_esc(_translate_market(agg.market.value))}</div>
                <div class="pop-row"><span class="k">{_esc(_ui("symbol_pop.opened"))}</span><span class="v">{_esc(since)} · {hold}</span></div>
                <div class="pop-row"><span class="k">{_esc(_ui("symbol_pop.lots"))}</span><span class="v">{_esc(_ui("symbol_pop.lots_suffix", count=len(agg.lots)))}</span></div>
              </div>"""


CURRENCY_PREFIX: Dict[str, str] = {
    "USD": "$", "TWD": "NT$", "JPY": "¥", "HKD": "HK$", "GBP": "£", "EUR": "€",
    "KRW": "₩", "CNY": "RMB ", "SGD": "S$", "AUD": "A$", "CAD": "C$", "CHF": "CHF ",
}


def _native_money(value: Optional[float], ccy: str, decimals: int = 2) -> str:
    """Format a native-currency value with the right prefix; `n/a` placeholder when missing."""
    if value is None:
        return f'<span class="pop-neg">{_ui("common.na")}</span>'
    pfx = CURRENCY_PREFIX.get(ccy.upper(), f"{ccy} ")
    return f"{pfx}{value:,.{decimals}f}"


def _price_popover(agg: TickerAggregate, prices: Dict[str, Any]) -> str:
    if agg.is_cash:
        return ""
    pr = prices.get(agg.ticker, {}) or {}
    src = _esc(pr.get("price_source", _ui("common.na")))
    as_of = _esc(pr.get("price_as_of") or _ui("common.na"))
    fresh = _esc(_translate_freshness(pr.get("price_freshness", "n/a")))
    state = _esc(_translate_market_state(pr.get("market_state_basis", "n/a")))
    feed_ccy = _esc((pr.get("currency") or agg.trade_currency or _ui("common.na")).upper())
    exchange = _esc(pr.get("exchange") or _ui("common.na"))
    # §9.0 — latest price displays in native trade currency; footer aggregates in base currency.
    ccy = agg.trade_currency
    price_str = _native_money(agg.latest_price, ccy)
    rows: List[str] = []
    for lot in sorted(agg.lots, key=lambda l: l.date or ""):
        date = _esc(lot.date or "?")
        if lot.cost is None:
            cost = f'<span class="pop-neg">{_ui("common.na")}</span>'
            pnl_native = f'<span class="pop-neg">{_ui("common.na")}</span>'
        else:
            cost = _native_money(lot.cost, ccy)
            if agg.latest_price is not None:
                # Native-currency P&L per lot for the popover row (matches the user's
                # original trade currency mental model). Base-currency aggregates live in the footer.
                p_native = (agg.latest_price - lot.cost) * lot.quantity
                p_cls = "pop-pos" if p_native >= 0 else "pop-neg"
                p_sign = "+" if p_native >= 0 else "−"
                pfx = CURRENCY_PREFIX.get(ccy.upper(), f"{ccy} ")
                pnl_native = f'<span class="{p_cls}">{p_sign}{pfx}{abs(p_native):,.0f}</span>'
            else:
                pnl_native = f'<span class="pop-neg">{_ui("common.na")}</span>'
        qty = f"{lot.quantity:g}"
        rows.append(f'<tr><td>{date}</td><td class="num">{cost}</td><td class="num">{qty}</td><td class="num">{pnl_native}</td></tr>')

    # Footer — base-currency aggregates per §9.0. The `weighted_avg_cost_usd`
    # field name predates the configurable-base feature; semantically it now holds
    # the cost basis in the active base currency.
    base_pfx = _base_prefix()
    base_ccy_code = ACTIVE_BASE_CURRENCY
    if agg.weighted_avg_cost_usd is not None:
        foot_avg = f"{base_pfx}{agg.weighted_avg_cost_usd:,.2f} ({base_ccy_code})"
    elif agg.weighted_avg_cost is not None:
        # Couldn't FX-convert; show native and flag.
        foot_avg = _native_money(agg.weighted_avg_cost, ccy) + f' <span class="pop-neg">{_esc(_ui("price_pop.fx_na"))}</span>'
    else:
        foot_avg = _ui("common.na")
    if agg.weighted_avg_cost_usd is not None:
        foot_total_cost = f"{base_pfx}{agg.weighted_avg_cost_usd * agg.total_qty:,.0f}"
    elif agg.total_cost_known:
        foot_total_cost = _native_money(agg.total_cost_known, ccy, decimals=0)
    else:
        foot_total_cost = _ui("common.na")
    foot_pnl = f'<span class="pop-neg">{_ui("common.na")}</span>' if agg.pnl_amount is None else (
        f'<span class="pop-{"pos" if agg.pnl_amount>=0 else "neg"}">'
        f'{"+" if agg.pnl_amount>=0 else "−"}{base_pfx}{abs(agg.pnl_amount):,.0f}</span>'
    )
    return f"""<div class="pop pop-px" role="tooltip">
                <h4>{_esc(agg.ticker)} · {_esc(_ui("price_pop.title_suffix"))}</h4>
                <div class="pop-sub">{_esc(_ui("price_pop.latest_price"))} {price_str} · {_esc(_ui("common.source"))}：{src} · {_esc(_ui("price_pop.freshness"))}：{fresh} · {_esc(_ui("price_pop.market_basis"))}：{state} · {_esc(_ui("price_pop.currency"))}：{feed_ccy} · {_esc(_ui("price_pop.exchange"))}：{exchange} · {as_of}</div>
                <table>
                  <thead><tr><th>{_esc(_ui("price_pop.acquired"))}</th><th class="num">{_esc(_ui("price_pop.cost"))}</th><th class="num">{_esc(_ui("price_pop.quantity"))}</th><th class="num">{_esc(_ui("price_pop.pnl"))}</th></tr></thead>
                  <tbody>{''.join(rows)}</tbody>
                  <tfoot class="summary"><tr><td>{_esc(_ui("price_pop.avg_cost"))} {foot_avg}</td><td class="num">{foot_total_cost}</td><td class="num">{agg.total_qty:g}</td><td class="num">{foot_pnl}</td></tr></tfoot>
                </table>
              </div>"""


def render_pnl_ranking(aggs: Dict[str, TickerAggregate]) -> str:
    items = [a for a in aggs.values() if a.pnl_amount is not None]
    if not items:
        return ""
    items.sort(key=lambda a: -(a.pnl_amount or 0))
    max_abs = max(abs(a.pnl_amount or 0) for a in items) or 1.0
    rows = []
    for a in items:
        width = abs(a.pnl_amount) / max_abs * 100.0
        cls = "pos" if a.pnl_amount >= 0 else "neg"
        sign = "+" if a.pnl_amount >= 0 else "−"
        txt_cls = "pos-txt" if a.pnl_amount >= 0 else "neg-txt"
        rows.append(
            f'<div class="bar-row"><div class="bar-label">{_esc(a.ticker)}</div>'
            f'<div class="bar-track"><div class="bar {cls}" style="width:{width:.1f}%"></div></div>'
            f'<div class="bar-value {txt_cls}">{sign}{_base_prefix()}{abs(a.pnl_amount):,.0f}</div></div>'
        )
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("pnl_ranking.title"))}</h2>
      <span class="sub">{_esc(_ui("pnl_ranking.subtitle", base=ACTIVE_BASE_CURRENCY))}</span>
    </div>
    <div class="bars">{''.join(rows)}</div>
  </section>"""


def render_holding_period(pacing: BookPacing) -> str:
    if pacing.avg_hold_years is None:
        return ""
    oldest = pacing.oldest or (_ui("common.na"), _ui("common.na"), _ui("common.na"))
    newest = pacing.newest or (_ui("common.na"), _ui("common.na"), _ui("common.na"))
    over_1y = _ui("common.na") if pacing.pct_held_over_1y is None else f"{pacing.pct_held_over_1y:.0f}%"
    d = pacing.distribution_pct
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("holding_period.title"))}</h2>
      <span class="sub">{_esc(_ui("holding_period.subtitle"))}</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="k">{_esc(_ui("holding_period.avg_hold"))}</div><div class="v">{_esc(_format_years(pacing.avg_hold_years))}</div><div class="delta">{_esc(_ui("holding_period.avg_hold_note"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("holding_period.oldest_lot"))}</div><div class="v">{_esc(oldest[0])}</div><div class="delta">{_esc(oldest[1])} · {_esc(oldest[2])}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("holding_period.newest_lot"))}</div><div class="v">{_esc(newest[0])}</div><div class="delta">{_esc(newest[1])} · {_esc(newest[2])}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("holding_period.held_over_1y"))}</div><div class="v">{over_1y}</div><div class="delta">{_esc(_ui("holding_period.held_over_1y_note"))}</div></div>
    </div>

    <div style="margin-top:18px">
      <div class="period-strip" aria-label="{_esc(_ui("holding_period.period_strip_label"))}">
        <span style="width:{d['<1m']}%;background:#b15309"  title="{_esc(_ui("holding_period.lt_1m"))}"></span>
        <span style="width:{d['1-6m']}%;background:#8a5a1c" title="{_esc(_ui("holding_period.m1_6"))}"></span>
        <span style="width:{d['6-12m']}%;background:#1d4690" title="{_esc(_ui("holding_period.m6_12"))}"></span>
        <span style="width:{d['1-3y']}%;background:#1f2937" title="{_esc(_ui("holding_period.y1_3"))}"></span>
        <span style="width:{d['3y+']}%;background:#15703d" title="{_esc(_ui("holding_period.y3_plus"))}"></span>
      </div>
      <div class="period-legend">
        <span><i style="background:#b15309"></i>{_esc(_ui("holding_period.lt_1m"))} · {d['<1m']}%</span>
        <span><i style="background:#8a5a1c"></i>{_esc(_ui("holding_period.m1_6"))} · {d['1-6m']}%</span>
        <span><i style="background:#1d4690"></i>{_esc(_ui("holding_period.m6_12"))} · {d['6-12m']}%</span>
        <span><i style="background:#1f2937"></i>{_esc(_ui("holding_period.y1_3"))} · {d['1-3y']}%</span>
        <span><i style="background:#15703d"></i>{_esc(_ui("holding_period.y3_plus"))} · {d['3y+']}%</span>
      </div>
    </div>
  </section>"""


def render_theme_sector(context: Dict[str, Any]) -> str:
    """§10.1 #5 — Theme / sector exposure.

    Theme/sector classification is editorial (spec §4.3 — agent auto-classifies each
    holding by sector / theme each run; buckets are not fixed). The agent must
    pre-render the bar chart and pass it as `context["theme_sector_html"]`.

    The CLI pre-render validator requires this field and theme_sector_audit.
    The placeholder branch is defensive for direct function callers only.
    """
    body = context.get("theme_sector_html") or (
        f'<div class="prose"><p>{_esc(_ui("theme_sector.placeholder"))}</p></div>'
    )
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("theme_sector.title"))}</h2>
      <span class="sub">{_esc(_ui("theme_sector.subtitle", base=ACTIVE_BASE_CURRENCY))}</span>
    </div>
    {body}
  </section>"""


def render_news(context: Dict[str, Any]) -> str:
    items = context.get("news") or []
    if not items:
        body = f'<div class="prose"><p>{_esc(_ui("news.placeholder"))}</p></div>'
    else:
        rows = []
        for n in items:
            impact = n.get("impact", "neu")
            label = {
                "pos": _ui("news.positive"),
                "neg": _ui("news.negative"),
                "neu": _ui("news.neutral"),
            }.get(impact, _ui("news.neutral"))
            raw_url = n.get("url", "#")
            safe_url = raw_url if (
                isinstance(raw_url, str)
                and (raw_url.startswith(("http://", "https://", "mailto:"))
                     or raw_url == "#")
            ) else "#"
            url = _esc(safe_url)
            rows.append(f"""\
      <div class="item">
        <div class="meta"><span class="tk">{_esc(n.get('ticker', _ui("common.dash")))}</span>{_esc(n.get('date', ''))}</div>
        <div class="body">
          <div class="head">{_esc(n.get('headline', ''))}</div>
          <div class="src">{_esc(_ui("news.source_prefix"))}<a href="{url}" target="_blank" rel="noopener noreferrer">{_esc(n.get('source', ''))}</a></div>
        </div>
        <span class="impact {impact}">{label}</span>
      </div>""")
        body = '<div class="news">' + "".join(rows) + "</div>"
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("news.title"))}</h2>
      <span class="sub">{_esc(_ui("news.subtitle"))}</span>
    </div>
    {body}
  </section>"""


_PIN_CLASS_BY_IMPACT = {"warn": "warn", "neg": "neg", "pos": "pos", "info": "info"}


def _events_timeline_html(events: List[Dict[str, Any]], today: _dt.date) -> str:
    """Render the 30-day event-calendar visualization (matches sample lines 1324-1338)."""
    if not events:
        return ""

    window_days = 30
    end = today + _dt.timedelta(days=window_days)

    def parse_date(raw: str) -> Optional[_dt.date]:
        s = (raw or "").strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%m-%d", "%m/%d"):
            try:
                d = _dt.datetime.strptime(s, fmt).date()
                # MM-DD: assume the year that keeps the date inside [today, end].
                if fmt != "%Y-%m-%d":
                    d = d.replace(year=today.year)
                    if d < today:
                        d = d.replace(year=today.year + 1)
                return d
            except ValueError:
                continue
        return None

    # Tick marks at 0/25/50/75/100% — labelled with the corresponding date.
    ticks: List[str] = []
    for pct in (0, 25, 50, 75, 100):
        d = today + _dt.timedelta(days=int(window_days * pct / 100))
        ticks.append(
            f'<span class="tick" style="left:{pct}%"></span>'
            f'<span class="tick-label" style="left:{pct}%">{d.strftime("%m-%d")}</span>'
        )

    pins: List[str] = []
    for e in events:
        d = parse_date(str(e.get("date", "")))
        if d is None:
            continue
        delta = (d - today).days
        if delta < 0 or delta > window_days:
            continue
        pct = delta / window_days * 100.0
        impact_class = _PIN_CLASS_BY_IMPACT.get(str(e.get("impact_class", "")).strip(), "")
        pin_cls = f"pin {impact_class}".rstrip()
        title = f"{d.strftime('%m-%d')} {e.get('topic', '')} {e.get('event', '')}".strip()
        pins.append(f'<span class="{pin_cls}" style="left:{pct:.1f}%" title="{_esc(title)}"></span>')
        if e.get("show_label", True):
            label = f"{e.get('topic', '')} {d.strftime('%m-%d')}".strip()
            pins.append(f'<span class="pin-label" style="left:{pct:.1f}%">{_esc(label)}</span>')

    return f"""    <div class="timeline" aria-label="{_esc(_ui("events.timeline_label"))}">
      <div class="axis"></div>
      {"".join(ticks)}
      {"".join(pins)}
    </div>
"""


def render_events(context: Dict[str, Any]) -> str:
    events = context.get("events") or []
    today = _dt.date.today()
    rows = []
    for e in events:
        rows.append(f"""\
          <tr>
            <td>{_esc(e.get('date', ''))}</td>
            <td>{_esc(e.get('topic', ''))}</td>
            <td>{_esc(e.get('event', ''))}</td>
            <td><span class="tag {_esc(e.get('impact_class', ''))}">{_esc(e.get('impact_label', ''))}</span></td>
            <td>{_esc(e.get('watch', ''))}</td>
          </tr>""")
    body = "\n".join(rows) if rows else (
        f'<tr><td colspan="5" class="na" style="text-align:center;padding:14px">{_esc(_ui("events.empty"))}</td></tr>'
    )
    timeline_html = _events_timeline_html(events, today)
    table_style = ' style="margin-top:14px"' if timeline_html else ""
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("events.title"))}</h2>
      <span class="sub">{_esc(_ui("events.subtitle"))}</span>
    </div>
{timeline_html}    <div class="tbl-wrap scroll-y"{table_style}>
      <table>
        <thead>
          <tr><th>{_esc(_ui("events.date"))}</th><th>{_esc(_ui("events.topic"))}</th><th>{_esc(_ui("events.event"))}</th><th>{_esc(_ui("events.impact"))}</th><th>{_esc(_ui("events.watch"))}</th></tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
    </div>
  </section>"""


def _translate_heat_reason(reason: Dict[str, Any]) -> str:
    """Translate a structured risk-heat reason payload (`{code, threshold?}`).

    The pipeline emits these as locale-stable codes; the renderer formats them
    via `_ui("risk.factor_<code>", threshold=...)` at display time so the
    snapshot doesn't need to know the active locale.
    """
    code = reason.get("code") if isinstance(reason, dict) else None
    if not code:
        return ""
    key = f"risk.factor_{code}"
    threshold = reason.get("threshold") if isinstance(reason, dict) else None
    if threshold is None:
        return _ui(key)
    return _ui(key, threshold=threshold)


def render_high_risk_opp(
    aggs: Dict[str, TickerAggregate],
    prices: Dict[str, Any],
    total_assets: float,
    context: Dict[str, Any],
    config: Dict[str, float],
    risk_heat: Optional[List[RiskHeatItem]] = None,
) -> str:
    """Render the high-risk heatmap + opportunities block.

    `risk_heat` may be supplied pre-computed (e.g. from a snapshot); when
    omitted, fall back to computing it from `aggs` for the legacy in-memory
    path.
    """
    items = risk_heat if risk_heat is not None else build_risk_heat_items(
        aggs, prices, total_assets, config
    )
    risk_cells = []
    for item in items:
        move_str = f"{item.move_pct:+.1f}%" if item.move_pct is not None else _ui("common.na")
        translated = [_translate_heat_reason(r) for r in item.reasons[:3]]
        reason_summary = " · ".join(t for t in translated if t)
        risk_cells.append(
            f'<div class="risk {item.band_class}"><div class="t">{_esc(item.ticker)}</div>'
            f'<div class="s">{_esc(_ui("risk.card_label", score=item.score))} · {_esc(reason_summary)}</div>'
            f'<div class="m">{item.weight_pct:.1f}% · {move_str}</div></div>'
        )

    risk_html = ''.join(risk_cells) or f'<div class="prose"><p>{_esc(_ui("risk.empty_risk"))}</p></div>'
    opps = context.get("high_opps") or []
    opp_rows = []
    for o in opps:
        opp_rows.append(f"""\
          <div class="item">
            <div class="tk">{_esc(o.get('ticker', _ui("common.dash")))}</div>
            <div class="why">{_esc(o.get('why', ''))}</div>
            <div class="trig">{_esc(o.get('trigger', ''))}</div>
          </div>""")
    opp_html = "".join(opp_rows) or f'<div class="prose"><p>{_esc(_ui("risk.empty_opp"))}</p></div>'
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("risk.title"))}</h2>
      <span class="sub">{_esc(_ui("risk.subtitle"))}</span>
    </div>
    <div class="cols-2">
      <div>
        <div class="eyebrow" style="margin-bottom:10px">{_esc(_ui("risk.left_title"))} · {_esc(_ui("risk.standard"))}</div>
        <div class="risk-grid">{risk_html}</div>
      </div>
      <div>
        <div class="eyebrow" style="margin-bottom:10px">{_esc(_ui("risk.right_title"))}</div>
        <div class="opp-list">{opp_html}</div>
      </div>
    </div>
  </section>"""


def _format_rr_string_ui(
    target: Optional[float],
    entry: Optional[float],
    stop: Optional[float],
    horizon_label: Optional[str] = None,
    *,
    binary: bool = False,
    rebalance: bool = False,
    hedged: bool = False,
    structural_reason: Optional[str] = None,
) -> str:
    """Localized report-facing R:R formatter.

    The exported `format_rr_string()` remains an English deterministic helper for
    tests and external callers; the HTML renderer uses this function so labels
    follow SETTINGS language and incomplete inputs do not leak into hold rows.
    """

    if rebalance:
        return _ui("pm.rr_rebalance")
    if binary:
        return _ui("pm.rr_binary")
    if structural_reason:
        return f"R:R = n/a（{structural_reason}）"
    if hedged and target is not None and entry is not None:
        upside_pct = (target - entry) / entry * 100.0
        return (
            f"{_ui('pm.target')} ${target:g} ({upside_pct:+.0f}%) / "
            f"{_ui('pm.stop')} = n/a（{_ui('pm.hedged_stop')}）"
        )

    rr = compute_rr_ratio(target, entry, stop)
    if rr is None or target is None or entry is None or stop is None:
        return ""

    upside_pct = (target - entry) / entry * 100.0
    downside_pct = (stop - entry) / entry * 100.0
    horizon = f" {_ui('pm.over')} {horizon_label}" if horizon_label else ""
    return (
        f"{_ui('pm.target')} ${target:g} ({upside_pct:+.0f}%) / "
        f"{_ui('pm.stop')} ${stop:g} ({downside_pct:+.0f}%) → R:R = {rr:g}:1{horizon}"
    )


def _format_portfolio_fit_line_ui(
    *,
    sized_pp: float,
    correlated_with: Optional[List[str]] = None,
    theme_overlap: Optional[List[str]] = None,
    rails: Optional[RailReport] = None,
) -> str:
    parts: List[str] = [f"{_ui('pm.sized')} {sized_pp:+.1f}{_ui('pm.pp_nav')}"]
    if correlated_with:
        parts.append(f"{_ui('pm.correlated_with')} {', '.join(correlated_with)}")
    if theme_overlap:
        parts.append(f"{_ui('pm.theme_overlap')} {', '.join(theme_overlap)}")
    if rails is not None:
        if rails.any_breach:
            parts.append(f"{_ui('pm.rail_breach')} {', '.join(rails.breached_rails())}")
        else:
            parts.append(_ui("pm.rails_ok"))
        parts.append(
            f"{_ui('pm.single_name')} {rails.single_name_pct_after:.1f}% "
            f"{_ui('pm.vs_warn')} {rails.single_name_warn:.1f}%"
        )
        if rails.cash_pct_after is not None:
            parts.append(
                f"{_ui('pm.cash')} {rails.cash_pct_after:.1f}% "
                f"{_ui('pm.vs_floor')} {rails.cash_floor_warn:.1f}%"
            )
    return f"{_ui('pm.portfolio_fit')} — " + "；".join(parts)


def _enrich_adjustment_why(
    a: Dict[str, Any],
    config: Dict[str, float],
    current_pct: Optional[float] = None,
) -> str:
    """Append PM-grade structured lines to an adjustment's `why` cell.

    Reads optional fields per §15.3 / §15.4 / §15.5 / §15.6 and produces the
    canonical strings via the helpers above. Back-compat: when the agent's
    context omits these fields entirely, the `why` cell renders unchanged.
    """

    base_why = a.get("why", "") or ""
    extras: List[str] = []
    has_pm_fields = any(a.get(k) not in (None, "", []) for k in PM_FIELD_KEYS)
    if not has_pm_fields:
        return _esc(base_why)

    variant_tag = (a.get("variant_tag") or "").strip()
    consensus = a.get("consensus")
    variant = a.get("variant")
    anchor = a.get("anchor")
    if variant_tag:
        line = f"{_ui('pm.tag')}：{variant_tag}"
        if consensus:
            line += f"；{_ui('pm.consensus')}：{consensus}"
        if variant and variant_tag in ("variant", "contrarian"):
            line += f"；{_ui('pm.variant')}：{variant}"
        if anchor and variant_tag in ("variant", "contrarian"):
            line += f"；{_ui('pm.anchor')}：{anchor}"
        extras.append(line)

    # R:R line
    binary = bool(a.get("binary_catalyst"))
    hedged = bool(a.get("hedged_structure"))
    is_rebalance = variant_tag == "rebalance"
    should_print_rr = (
        any(a.get(k) is not None for k in ("target_price", "entry_price", "stop_price"))
        or binary
        or hedged
        or bool(a.get("rr_structural_reason"))
        or (is_rebalance and is_actionable_recommendation(a, current_pct))
    )
    rr_line = _format_rr_string_ui(
        _float_or_none(a.get("target_price")),
        _float_or_none(a.get("entry_price")),
        _float_or_none(a.get("stop_price")),
        a.get("horizon_label"),
        binary=binary,
        rebalance=is_rebalance,
        hedged=hedged,
        structural_reason=a.get("rr_structural_reason"),
    ) if should_print_rr else ""
    if rr_line:
        extras.append(rr_line)

    # Pre-mortem triplet (§15.5)
    if not is_rebalance:
        pm_bits: List[str] = []
        if a.get("failure_mode"):
            pm_bits.append(f"{_ui('pm.failure')}：{a['failure_mode']}")
        if a.get("kill_trigger"):
            pm_bits.append(f"{_ui('pm.kill')}：{a['kill_trigger']}")
        if a.get("kill_action"):
            pm_bits.append(f"{_ui('pm.kill_action')}：{a['kill_action']}")
        # Each pm_bit is its own <br>-separated line in the why cell so a long
        # kill_action / failure_mode never produces a single overflowing string.
        extras.extend(pm_bits)

    # Portfolio fit (§15.6)
    sized_pp = _resolved_sized_pp_delta(a, current_pct)
    if sized_pp is not None:
        rails = check_rails(
            config,
            current_pct=float(current_pct if current_pct is not None else a.get("current_pct", 0.0) or 0.0),
            delta_pp=float(sized_pp),
            theme_pct_after=_float_or_none(a.get("theme_pct_after")),
            high_vol_pct_after=_float_or_none(a.get("high_vol_pct_after")),
            cash_pct_after=_float_or_none(a.get("cash_pct_after")),
        )
        extras.append(_format_portfolio_fit_line_ui(
            sized_pp=float(sized_pp),
            correlated_with=a.get("correlated_with"),
            theme_overlap=a.get("theme_overlap"),
            rails=rails,
        ))

    if not extras:
        return base_why

    enriched_lines = "<br>".join(_esc(line) for line in extras)
    if base_why:
        return f"{_esc(base_why)}<br><span class=\"pm-meta\">{enriched_lines}</span>"
    return f'<span class="pm-meta">{enriched_lines}</span>'


def render_adjustments(
    context: Dict[str, Any],
    config: Optional[Dict[str, float]] = None,
    aggs: Optional[Dict[str, TickerAggregate]] = None,
    total_assets: Optional[float] = None,
) -> str:
    adjs = context.get("adjustments") or []
    cfg = config or DEFAULTS
    if not adjs:
        return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("adjustments.title"))}</h2>
      <span class="sub">{_esc(_ui("adjustments.subtitle"))}</span>
    </div>
    <div class="prose"><p>{_esc(_ui("adjustments.placeholder"))}</p></div>
  </section>"""
    rp_label = _ui("reviewer.note_label")
    rows = []
    for a in adjs:
        ticker = str(a.get("ticker", "")).strip()
        actual_current_pct: Optional[float] = None
        if aggs is not None and total_assets and ticker in aggs:
            mv = aggs[ticker].market_value
            if mv is not None:
                actual_current_pct = mv / total_assets * 100.0
        current_pct = actual_current_pct
        if current_pct is None:
            current_pct = _float_or_none(a.get("current_pct")) or 0.0
        # `why_cell` is already escaped (or contains pre-escaped HTML for the
        # PM-meta span); skip _esc in the template to avoid double-escape.
        why_cell = _enrich_adjustment_why(a, cfg, current_pct)
        # §15.8 inline per-row reviewer notes — appended to the why cell so
        # they sit beside the recommendation they annotate without replacing
        # the user's prose.
        row_notes = a.get("reviewer_notes") or []
        if isinstance(row_notes, str):
            row_notes = [row_notes]
        for n in row_notes:
            if isinstance(n, str) and n.strip():
                why_cell += (
                    f'<div class="reviewer-note-inline">'
                    f'<b>{_esc(rp_label)}:</b> {_esc(n)}</div>'
                )
        rows.append(f"""\
          <tr>
            <td><span class="sym-trigger" tabindex="0" role="button">{_esc(ticker or _ui("common.dash"))}</span></td>
            <td class="num">{current_pct:.1f}%</td>
            <td><span class="adj-action {_esc(a.get('action', 'hold'))}">{_esc(a.get('action_label', ''))}</span></td>
            <td class="why">{why_cell}</td>
            <td class="trig">{_esc(a.get('trigger', ''))}</td>
          </tr>""")
    section_notes = _reviewer_pass(context)["by_section"].get("adjustments") or []
    section_reviewer_block = _render_reviewer_notes(section_notes, rp_label)
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("adjustments.title"))}</h2>
      <span class="sub">{_esc(_ui("adjustments.subtitle"))}</span>
    </div>
    <div class="tbl-wrap">
      <table class="adj-tbl">
        <colgroup>
          <col style="width:12%">
          <col style="width:8%">
          <col style="width:14%">
          <col style="width:38%">
          <col style="width:28%">
        </colgroup>
        <thead><tr><th>{_esc(_ui("adjustments.ticker"))}</th><th class="num">{_esc(_ui("adjustments.current"))}</th><th>{_esc(_ui("adjustments.recommendation"))}</th><th>{_esc(_ui("adjustments.why"))}</th><th>{_esc(_ui("adjustments.trigger"))}</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    {section_reviewer_block}
  </section>"""


def _render_action_item(item: Any) -> str:
    if isinstance(item, str):
        return _esc(item)
    if not isinstance(item, dict):
        return _esc(str(item))

    ticker = str(item.get("ticker") or "").strip()
    label = str(item.get("text") or item.get("action_label") or item.get("action") or "").strip()
    why = str(item.get("why") or "").strip()
    trigger = str(item.get("trigger") or "").strip()
    chunks: List[str] = []
    head = " ".join(x for x in (ticker, label) if x).strip()
    if head:
        chunks.append(head)
    if why:
        chunks.append(why)
    if trigger:
        chunks.append(f"{_ui('adjustments.trigger')}: {trigger}")
    main = " — ".join(chunks) or _ui("common.dash")

    meta: List[str] = []
    for key, label_key in [
        ("variant_tag", "pm.tag"),
        ("consensus", "pm.consensus"),
        ("anchor", "pm.anchor"),
        ("kill_trigger", "pm.kill"),
        ("kill_action", "pm.kill_action"),
    ]:
        value = item.get(key)
        if value not in (None, "", []):
            meta.append(f"{_ui(label_key)}: {value}")
    sized = item.get("sized_pp_delta")
    if sized not in (None, ""):
        meta.append(f"{_ui('pm.sized')} {float(sized):+.1f}{_ui('pm.pp_nav')}")
    if not meta:
        return _esc(main)
    meta_html = "<br>".join(_esc(m) for m in meta)
    return f'{_esc(main)}<br><span class="pm-meta">{meta_html}</span>'


def render_actions(context: Dict[str, Any]) -> str:
    a = context.get("actions") or {}
    rows = []
    for label_class, label_text, key in [
        ("do", _ui("actions.must_do"), "must_do"),
        ("may", _ui("actions.may_do"), "may_do"),
        ("no", _ui("actions.avoid"), "avoid"),
        ("fix", _ui("actions.need_data"), "need_data"),
    ]:
        for item in a.get(key, []) or []:
            rows.append(f'<li><span class="lbl {label_class}">{_esc(label_text)}</span><span>{_render_action_item(item)}</span></li>')
    body = "\n".join(rows) or f'<li><span class="lbl">{_esc(_ui("common.dash"))}</span><span>{_esc(_ui("actions.placeholder"))}</span></li>'
    rp_notes = _reviewer_pass(context)["by_section"].get("actions") or []
    reviewer_block = _render_reviewer_notes(rp_notes, _ui("reviewer.note_label"))
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("actions.title"))}</h2>
      <span class="sub">{_esc(_ui("actions.subtitle"))}</span>
    </div>
    <ul class="actions">
{body}
    </ul>
    {reviewer_block}
  </section>"""


def render_sources(prices: Dict[str, Any], context: Dict[str, Any]) -> str:
    rows = []
    for ticker, pr in sorted(prices.items()):
        if ticker.startswith("_"):
            continue
        if not isinstance(pr, dict):
            continue
        fresh = pr.get("price_freshness", "n/a")
        fresh_cls = {"fresh": "fresh", "delayed": "delayed",
                     "stale_after_exhaustive_search": "stale", "n/a": "stale"}.get(fresh, "stale")
        fresh_label = _translate_freshness(fresh)
        market_state_label = _translate_market_state(pr.get("market_state_basis", "n/a"))
        notes = []
        if pr.get("yfinance_auto_fix_applied"):
            notes.append(f"{_ui('sources.auto_fix')}：{pr.get('yfinance_auto_fix_summary')}")
        if pr.get("yfinance_retry_count"):
            notes.append(_ui("sources.retry", count=pr.get("yfinance_retry_count")))
        if pr.get("yfinance_failure_reason"):
            notes.append(str(pr.get("yfinance_failure_reason"))[:60])
        rows.append(f"""\
          <tr>
            <td>{_esc(ticker)}</td>
            <td>{_esc(pr.get('price_source', _ui("common.na")))}</td>
            <td>{_esc(market_state_label)}</td>
            <td class="num">{_esc(pr.get('price_as_of') or _ui("common.na"))}</td>
            <td><span class="freshness {fresh_cls}">{_esc(fresh_label)}</span></td>
            <td>{('<br>'.join(_esc(n) for n in notes)) or _esc(_ui("common.dash"))}</td>
          </tr>""")
    fx_payload = prices.get("_fx") if isinstance(prices.get("_fx"), dict) else {}
    fx_details = fx_payload.get("details") if isinstance(fx_payload.get("details"), dict) else {}
    for pair, detail in sorted(fx_details.items()):
        if not isinstance(detail, dict):
            continue
        fresh = detail.get("price_freshness", "n/a")
        fresh_cls = {"fresh": "fresh", "delayed": "delayed",
                     "stale_after_exhaustive_search": "stale", "n/a": "stale"}.get(fresh, "stale")
        fresh_label = _translate_freshness(fresh)
        market_state_label = _translate_market_state(detail.get("market_state_basis", "n/a"))
        notes = []
        if detail.get("latest_price") not in (None, ""):
            notes.append(f"rate={detail.get('latest_price')}")
        if detail.get("yfinance_failure_reason"):
            notes.append(str(detail.get("yfinance_failure_reason"))[:60])
        rows.append(f"""\
          <tr>
            <td>FX {_esc(pair)}</td>
            <td>{_esc(detail.get('price_source', _ui("common.na")))}</td>
            <td>{_esc(market_state_label)}</td>
            <td class="num">{_esc(detail.get('price_as_of') or _ui("common.na"))}</td>
            <td><span class="freshness {fresh_cls}">{_esc(fresh_label)}</span></td>
            <td>{('<br>'.join(_esc(n) for n in notes)) or _esc(_ui("common.dash"))}</td>
          </tr>""")
    gaps = context.get("data_gaps") or []
    gap_items: List[str] = []

    # §15.7 Strategy readout — agent supplies the pre-formatted string.
    # The script does not template-format the readout from any structured input
    # because the prose is the user's own framing: the LLM reads the whole
    # `## Investment Style And Strategy` section in SETTINGS.md, internalises
    # it, and writes the readout in first person as the user (in the SETTINGS
    # Language). Renderer just slots it as a labeled prose block at the top of
    # §10.11 — separate from the data-gaps list so the paragraph cadence does
    # not collide with terse `<b>label:</b> detail` gap bullets.
    # Canonical key: `strategy_readout`. Legacy alias `style_readout` is still
    # accepted so older context payloads keep rendering.
    strategy_readout_str = context.get("strategy_readout") or context.get("style_readout")

    rp = _reviewer_pass(context)
    rp_label = _ui("reviewer.note_label")
    readout_review_notes = [
        n for n in (rp["by_section"].get("strategy_readout") or [])
        if isinstance(n, str) and n.strip()
    ]
    if strategy_readout_str:
        review_html = "".join(
            f'<div class="reviewer-note-inline"><b>{_esc(rp_label)}:</b> {_esc(n)}</div>'
            for n in readout_review_notes
        )
        readout_block = (
            f'<div class="strategy-readout-wrap" style="margin-bottom:18px">'
            f'<div class="eyebrow" style="margin-bottom:8px">'
            f'{_esc(_ui("sources.strategy_readout_heading"))}</div>'
            f'<div class="prose"><p>{_esc(strategy_readout_str)}</p></div>'
            f'{review_html}'
            f'</div>'
        )
    else:
        readout_block = ""

    for g in gaps:
        gap_items.append(
            f'<li><b>{_esc(g.get("summary", ""))}:</b> {_esc(g.get("detail", ""))}</li>'
        )

    profit_panel_notes = _profit_panel_audit_notes(context)
    if profit_panel_notes:
        gap_items.append(
            _gap_group_li(_ui("sources.profit_panel_gap"), profit_panel_notes)
        )
    if not _transaction_analytics(context):
        gap_items.append(
            f'<li><b>{_esc(_ui("sources.transaction_analytics_gap"))}:</b> '
            f'{_esc(_ui("sources.transaction_analytics_gap_detail"))}</li>'
        )
    else:
        analytics_gaps = [
            str(g) for g in
            ((_transaction_analytics(context).get("discipline_check") or {}).get("data_gaps") or [])
        ]
        if analytics_gaps:
            gap_items.append(
                _gap_group_li(_ui("sources.transaction_analytics_gap"), analytics_gaps)
            )

    rp_summary_label = _ui("reviewer.summary_label")
    for note in rp["summary"]:
        if isinstance(note, str) and note.strip():
            gap_items.append(
                f'<li class="reviewer-summary"><b>{_esc(rp_summary_label)}:</b> {_esc(note)}</li>'
            )

    gap_html = "".join(gap_items) or f'<li>{_esc(_ui("sources.no_gaps"))}</li>'
    spec_note = context.get("spec_update_note")
    spec_html = (f'<div class="bucket-note" style="margin-top:18px"><b>{_esc(_ui("sources.spec_note"))}</b>{_esc(spec_note)}</div>'
                 if spec_note else "")
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("sources.title"))}</h2>
      <span class="sub">{_esc(_ui("sources.subtitle"))}</span>
    </div>
    {readout_block}
    <div class="eyebrow" style="margin-bottom:10px">{_esc(_ui("sources.audit_heading"))}</div>
    <div class="tbl-wrap scroll-y">
      <table class="src-tbl">
        <thead>
          <tr><th>{_esc(_ui("sources.ticker"))}</th><th>{_esc(_ui("sources.price_source"))}</th><th>{_esc(_ui("sources.market_state"))}</th><th>{_esc(_ui("sources.as_of"))}</th><th>{_esc(_ui("sources.freshness"))}</th><th>{_esc(_ui("sources.notes"))}</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    <div class="eyebrow" style="margin-top:22px;margin-bottom:6px">{_esc(_ui("sources.gaps_heading"))}</div>
    <ul class="gap-list">{gap_html}</ul>
    {spec_html}
  </section>"""


# ----------------------------------------------------------------------------- #
# Master assembly
# ----------------------------------------------------------------------------- #

def render_html(
    snapshot: Snapshot,
    context: Dict[str, Any],
    css: str,
    settings: SettingsProfile,
) -> str:
    """Project a fully-resolved Snapshot onto HTML.

    All numeric / structural data comes from the snapshot — the renderer
    performs no aggregation, FX conversion, pacing, heat scoring, or
    special-check computation here. Editorial content (news, events, alerts,
    adjustments, action list, theme/sector HTML) comes from `context`.
    """
    try:
        today = _dt.date.fromisoformat(snapshot.today)
    except (ValueError, TypeError):
        today = _dt.date.today()

    # Activate the base currency *before* any render_ function runs so all
    # downstream `_fmt_money` / `_fmt_signed*` / popover-footer prefixes use the
    # configured base.
    _set_active_base_currency(snapshot.base_currency)

    aggs = snapshot.aggregates
    prices = snapshot.prices
    config = snapshot.config
    totals = snapshot.totals
    total_assets = totals.get("total_assets") or 0.0
    invested = totals.get("invested") or 0.0
    cash = totals.get("cash") or 0.0
    pnl = totals.get("pnl")

    # Render sections (§10 order)
    sections = [
        render_masthead(context),
        render_alerts(context),
        render_today_summary(context),                                     # §10.1 #1
        render_dashboard(aggs, total_assets, invested, cash, pnl),         # §10.1 #2
        render_profit_panel(context),                                      # §10.1.5 profit panel
        render_report_accuracy(context),                                   # §10.1.5a data quality scores
        render_performance_attribution(context),                           # transaction history attribution
        render_trade_quality(context),                                     # transaction history trade review
        render_discipline_check(context),                                  # transaction history discipline checks
        render_trading_psychology(context),                                # §10.1.7 trading-psychology evaluation
        render_allocation_and_weight(aggs, total_assets, today),           # §10.1 allocation + weight
        render_holdings_table(aggs, total_assets, prices, today, context), # §10.1 #3
        render_pnl_ranking(aggs),                                          # §10.4 chart
        render_holding_period(snapshot.book_pacing),                       # §10.1 #4
        render_theme_sector(context),                                      # §10.1 #5
        render_news(context),                                              # §10.1 #6
        render_events(context),                                            # §10.1 #7
        render_high_risk_opp(aggs, prices, total_assets, context, config,  # §10.1 #8
                              risk_heat=snapshot.risk_heat),
        render_adjustments(context, config, aggs, total_assets),           # §10.1 #9
        render_actions(context),                                           # §10.1 #10
        render_sources(prices, context),                                   # §10.1 #11
    ]

    return f"""<!doctype html>
<html lang="{_esc(settings.locale)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(context.get('title', _ui('masthead.title')))}</title>
<style>{css}{_REVIEWER_CSS}</style>
</head>
<body>
<div class="wrap">
{chr(10).join(s for s in sections if s)}
  <footer class="footer">
    {_esc(_ui("footer.text"))}
  </footer>
</div>
</body>
</html>
"""


# ----------------------------------------------------------------------------- #
# CLI
# ----------------------------------------------------------------------------- #

def _cli(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--snapshot", default=None, type=Path,
                   help="Pre-computed report snapshot from `python scripts/transactions.py "
                        "snapshot`. When supplied, the renderer skips aggregation, "
                        "merge_prices, book_pacing, build_risk_heat_items, special_checks, "
                        "auto-FX, and auto-analytics — all numeric work happens upstream. "
                        "This is the canonical pipeline path; --prices/--db is a fallback.")
    p.add_argument("--db", default=Path("transactions.db"), type=Path,
                   help="Fallback path: transactions.db source for positions when "
                        "--snapshot is not supplied.")
    p.add_argument("--settings", default="SETTINGS.md", type=Path)
    p.add_argument("--prices", required=False, type=Path,
                   help="Fallback path: prices.json from scripts/fetch_prices.py. Ignored "
                        "when --snapshot is supplied.")
    p.add_argument("--ui-dict", default=None, type=Path,
                   help="Optional UI dictionary JSON overlay. For non-built-in languages, "
                        "the executing agent should translate scripts/i18n/report_ui.en.json "
                        "and pass the translated JSON here.")
    p.add_argument("--context", default=None, type=Path,
                   help="Editorial context JSON (today summary, news, actions, ...)")
    p.add_argument("--sample", default=Path(__file__).resolve().parent.parent / "reports" / "_sample_redesign.html",
                   type=Path, help="Canonical visual reference (read-only, supplies CSS)")
    p.add_argument("--output", default=None, type=Path,
                   help="Output HTML path; default: reports/<timestamp>_portfolio_report.html")
    p.add_argument("--self-check", action="store_true",
                   help="Run unit tests for PM-grade indicator helpers and exit. Validates "
                        "the canonical math (R:R, rails, style readout, lever inference) "
                        "without rendering a report. Use this in CI to catch silent drift.")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


# --------------------------------------------------------------------------- #
# Self-check — unit tests for PM-grade helpers (§§15.4–15.7)
# --------------------------------------------------------------------------- #

def _run_self_check() -> int:
    """Validate the canonical math. Returns 0 on success, 1 on failure."""

    failures: List[str] = []

    def check(name: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            failures.append(f"  - {name}: expected {expected!r}, got {actual!r}")

    # --- R:R ratio ---
    check("rr long 4.3:1", compute_rr_ratio(target=260, entry=200, stop=186), 4.29)
    check("rr long 2:1",   compute_rr_ratio(target=120, entry=100, stop=90), 2.0)
    check("rr short",      compute_rr_ratio(target=80,  entry=100, stop=110), 2.0)
    check("rr inverted",   compute_rr_ratio(target=80,  entry=100, stop=90), None)
    check("rr missing",    compute_rr_ratio(target=None, entry=100, stop=90), None)
    check("rr zero stop",  compute_rr_ratio(target=120, entry=100, stop=100), None)

    # --- R:R formatted strings ---
    rr_str = format_rr_string(target=260, entry=200, stop=186, horizon_label="9 months")
    if "R:R = 4.29:1" not in rr_str or "Target $260" not in rr_str:
        failures.append(f"  - rr_str canonical: got {rr_str!r}")
    check("rr binary",
          format_rr_string(target=None, entry=None, stop=None, binary=True),
          "R:R = n/a (binary outcome — see kill criteria)")
    check("rr rebalance",
          format_rr_string(target=None, entry=None, stop=None, rebalance=True),
          "R:R = n/a (rebalance)")
    rr_hedged = format_rr_string(target=200, entry=180, stop=None, hedged=True)
    if "Stop = n/a (hedged structure" not in rr_hedged:
        failures.append(f"  - rr hedged: got {rr_hedged!r}")

    # --- Lever bands ---
    check("stop band high",   suggest_stop_pct_band("high"),   (20.0, 30.0))
    check("stop band medium", suggest_stop_pct_band("medium"), (12.0, 18.0))
    check("stop band low",    suggest_stop_pct_band("low"),    (7.0, 10.0))
    check("size band aggressive", suggest_size_pp_band("aggressive"), (8.0, 15.0))
    check("size band kelly-lite", suggest_size_pp_band("kelly-lite"), (2.0, 8.0))
    check("size band flat",       suggest_size_pp_band("flat"),       (0.0, 5.0))

    # --- Rail check ---
    cfg = {**DEFAULTS}
    rep = check_rails(cfg, current_pct=4.0, delta_pp=2.0,
                      cash_pct_after=15.0, theme_pct_after=20.0, high_vol_pct_after=10.0)
    check("rail no breach",      rep.any_breach, False)
    check("rail single after",   rep.single_name_pct_after, 6.0)

    rep2 = check_rails(cfg, current_pct=14.0, delta_pp=3.0)  # 17 > 15
    check("rail single breach",  rep2.single_name_breach, True)
    check("rail breached list",  rep2.breached_rails(), ["single-name"])

    rep3 = check_rails(cfg, current_pct=4.0, delta_pp=1.0,
                      cash_pct_after=8.0, theme_pct_after=35.0, high_vol_pct_after=40.0)
    check("rail multi breaches", set(rep3.breached_rails()), {"theme", "high-vol bucket", "cash floor"})

    # --- Portfolio fit line ---
    fit = format_portfolio_fit_line(sized_pp=2.0, correlated_with=["DELT"], theme_overlap=["AI"], rails=rep)
    if "sized +2.0pp of NAV" not in fit or "correlated with DELT" not in fit or "rails OK" not in fit:
        failures.append(f"  - portfolio fit OK case: got {fit!r}")
    fit_breach = format_portfolio_fit_line(sized_pp=3.0, rails=rep2)
    if "BREACHES rails: single-name" not in fit_breach:
        failures.append(f"  - portfolio fit breach: got {fit_breach!r}")

    # --- Style lever validation (legacy helper) ---
    # The §15.7 spec no longer mandates structured lever resolution; the agent
    # reads `## Investment Style And Strategy` and acts as the user. The
    # validator is kept so legacy callers that still produce StyleLevers
    # objects continue to round-trip correctly.
    good_levers = StyleLevers(
        drawdown_tolerance="high", conviction_sizing="kelly-lite",
        holding_period_bias="investor", confirmation_threshold="low",
        contrarian_appetite="selective", hype_tolerance="zero",
        sources={"drawdown_tolerance": 'bullet "我能承受極大的短期虧損與波動"',
                 "conviction_sizing": 'bullet "願意在高勝率或高報酬風險比的機會上積極投入"',
                 "holding_period_bias": "default",
                 "confirmation_threshold": "inferred — pin to confirm",
                 "contrarian_appetite": "default",
                 "hype_tolerance": 'bullet "不希望聽到過度誇大的樂觀預測"'},
    )
    check("validate good levers", validate_style_levers(good_levers), [])

    bad_levers = StyleLevers(drawdown_tolerance="extreme")  # invalid
    bad_findings = validate_style_levers(bad_levers)
    if not any("drawdown_tolerance=" in f for f in bad_findings):
        failures.append(f"  - validate_style_levers should flag bad value: {bad_findings}")

    defaults = StyleLevers()  # all neutral defaults
    check("default levers valid", validate_style_levers(defaults), [])

    # Note: the Strategy readout *prose* is composed by the agent in natural
    # language (first person, as the user) and passed via
    # context["strategy_readout"] (legacy alias context["style_readout"] still
    # accepted). The script does not format the readout — that would force
    # template English/Chinese into a block that should match the SETTINGS
    # Language and the user's voice.

    # --- Length budget ---
    lb = length_budget_status("hello world", max_words=5, max_chars=20)
    check("length OK",  lb["over"], False)
    lb2 = length_budget_status("a " * 50, max_words=10)
    check("length over", lb2["over"], True)

    # --- Validation: rebalance item is exempt from variant/R:R ---
    rebalance_adj = {"variant_tag": "rebalance", "sized_pp_delta": -1.0}
    check("rebalance compliant", validate_recommendation_block(rebalance_adj), [])

    # Non-action status guidance should not be forced into fake R:R / kill fields.
    hold_status = {"ticker": "NVDA", "action": "hold", "why": "Wait for earnings."}
    check("hold status has no PM requirements", validate_recommendation_block(hold_status), [])

    # Variant call missing R:R + kill → multiple findings
    bad_adj = {"action": "add", "variant_tag": "variant", "consensus": "EPS 4.20",
               "anchor": "10-Q", "sized_pp_delta": 2.0}
    findings = validate_recommendation_block(bad_adj)
    if not any("R:R inputs missing" in f for f in findings):
        failures.append(f"  - bad_adj should flag R:R missing: {findings}")
    if not any("kill_trigger missing" in f for f in findings):
        failures.append(f"  - bad_adj should flag kill_trigger missing: {findings}")

    # Fully compliant variant call
    good_adj = {"variant_tag": "variant", "consensus": "EPS 4.20", "anchor": "10-Q",
                "entry_price": 200, "target_price": 260, "stop_price": 186,
                "failure_mode": "GM compresses", "kill_trigger": "Q3 GM < 30%",
                "kill_action": "cut full position", "sized_pp_delta": 2.0}
    check("good_adj compliant", validate_recommendation_block(good_adj), [])

    from report_accuracy import compute_report_accuracy  # noqa: WPS433

    ra = compute_report_accuracy(
        profit_panel={"rows": [{"period": "1D", "pnl": 1000.0, "audit": []}]},
        prices={"NVDA": {"latest_price": 1.0, "price_freshness": "fresh"}},
        position_tickers=["NVDA"],
        missing_fx=[],
        errors={},
    )
    if not isinstance(ra.get("overall"), dict) or "score" not in ra["overall"]:
        failures.append(f"  - report_accuracy shape: {ra!r}")
    elif not isinstance(ra.get("dimensions"), list) or len(ra["dimensions"]) < 4:
        failures.append(f"  - report_accuracy dimensions: {ra.get('dimensions')!r}")

    if failures:
        print(f"FAIL — {len(failures)} self-check assertions failed:")
        for f in failures:
            print(f)
        return 1
    print("OK — all self-check assertions passed.")
    return 0


def _load_snapshot_from_disk(path: Path) -> Snapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return deserialize_snapshot(payload)


def _build_snapshot_from_legacy_inputs(args: argparse.Namespace) -> Tuple[Optional[Snapshot], int]:
    """Legacy `--prices --db` path: build the snapshot in-process before render.

    Emits a deprecation warning so the canonical pipeline (`transactions.py
    snapshot` → `--snapshot`) is preferred. Returns (snapshot, exit_code).
    Exit code is 0 on success; non-zero exit codes are propagated to main().
    """
    logging.warning(
        "DEPRECATED: --prices/--db path materializes the snapshot in-process. "
        "Run `python scripts/transactions.py snapshot --prices ... --output "
        "report_snapshot.json` upstream and pass --snapshot for a clean "
        "pipeline / renderer split."
    )
    if args.prices is None:
        print("ERROR: --prices is required when --snapshot is omitted", file=sys.stderr)
        return None, 2
    if not args.prices.exists():
        print(f"ERROR: {args.prices} not found (run fetch_prices.py first)", file=sys.stderr)
        return None, 3
    if not (args.db and args.db.exists()):
        print(f"ERROR: no positions source found at --db {args.db}. "
              f"Run `python scripts/transactions.py db init` and import transactions first.",
              file=sys.stderr)
        return None, 2

    prices = json.loads(args.prices.read_text(encoding="utf-8"))
    todo_hard_failures = find_todo_required_hard_failures(prices)
    if todo_hard_failures:
        print(format_todo_required_hard_failures(todo_hard_failures), file=sys.stderr)
        return None, 5

    settings = parse_settings_profile(args.settings)
    snapshot = compute_snapshot(
        db_path=args.db,
        prices=prices,
        settings=settings,
    )
    if not snapshot.aggregates:
        print(f"ERROR: {args.db} has no open_lots / cash_balances. "
              f"Run `python scripts/transactions.py db init` and import transactions first.",
              file=sys.stderr)
        return None, 4
    return snapshot, 0


def main(argv: Optional[List[str]] = None) -> int:
    args = _cli(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.self_check:
        return _run_self_check()

    # Defense-in-depth: warn if --output lands under demo/ but --settings is
    # the root default. Mirrors the cache + archive demo-isolation guards.
    output_under_demo = (
        args.output is not None
        and "demo" in {p.lower() for p in args.output.resolve().parts}
    )
    if (
        output_under_demo
        and Path(args.settings).resolve().name == "SETTINGS.md"
        and Path(args.settings).resolve().parent.name != "demo"
    ):
        print(
            f"WARNING: --output {args.output} appears to be a demo report but --settings "
            f"is the root default ({args.settings}). Pass --settings demo/SETTINGS.md to "
            "keep the demo run from reading your real strategy / language / API keys.",
            file=sys.stderr,
        )

    # ----------------------------------------------------------------------- #
    # Resolve the snapshot. Canonical path: --snapshot (built upstream by
    # `python scripts/transactions.py snapshot`). Legacy path: --prices + --db
    # builds the snapshot in-process and emits a deprecation warning.
    # ----------------------------------------------------------------------- #
    if args.snapshot is not None:
        if not args.snapshot.exists():
            print(f"ERROR: snapshot file {args.snapshot} not found. "
                  "Run `python scripts/transactions.py snapshot` first.",
                  file=sys.stderr)
            return 3
        try:
            snapshot = _load_snapshot_from_disk(args.snapshot)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: failed to load snapshot {args.snapshot}: {exc}", file=sys.stderr)
            return 6
    else:
        snapshot, exit_code = _build_snapshot_from_legacy_inputs(args)
        if snapshot is None:
            return exit_code

    # ----------------------------------------------------------------------- #
    # Editorial context (agent-authored: news, events, alerts, action list,
    # adjustments, theme/sector HTML, reviewer pass, and research audits).
    # ----------------------------------------------------------------------- #
    context: Dict[str, Any] = {}
    if args.context and args.context.exists():
        context = json.loads(args.context.read_text(encoding="utf-8"))
    elif args.context:
        logging.warning("Context file %s not found; pre-render validation will fail.", args.context)

    # Reconstruct a SettingsProfile shim from the snapshot so UI bundle resolution
    # stays uniform across both paths.
    settings = settings_profile_for_snapshot(snapshot)

    ui_dict_override: Optional[Dict[str, Any]] = None
    if args.ui_dict and args.ui_dict.exists():
        ui_dict_override = _load_json_ui_dict(args.ui_dict)
    elif args.ui_dict:
        logging.warning("UI dictionary file %s not found; ignoring.", args.ui_dict)
    elif isinstance(context.get("ui_dictionary"), dict):
        ui_dict_override = context.get("ui_dictionary")
    elif context.get("ui_dictionary_path"):
        candidate = Path(str(context.get("ui_dictionary_path")))
        if candidate.exists():
            ui_dict_override = _load_json_ui_dict(candidate)
        else:
            logging.warning("Context UI dictionary path %s not found; ignoring.", candidate)

    if settings.locale not in STABLE_UI_TEXT and ui_dict_override is None:
        logging.warning(
            "Locale %s has no built-in UI dictionary. Falling back to English chrome. "
            "The executing agent should translate %s and pass it via --ui-dict "
            "or context['ui_dictionary'].",
            settings.raw_language,
            I18N_DIR / "report_ui.en.json",
        )
    _set_active_ui(resolve_ui_bundle(settings, ui_dict_override))
    if settings.missing:
        logging.warning("SETTINGS.md not found; defaulting report UI language to English.")

    context["language"] = settings.display_name

    if "fx" in context:
        logging.warning(
            "Ignoring context['fx']; FX conversion rates are auto-fetched into "
            "prices.json by scripts/fetch_prices.py and propagated through the snapshot."
        )
    # Snapshot is the single source of truth for FX (already base-scoped).
    context["fx"] = dict(snapshot.fx)
    context["fx_details"] = dict(snapshot.fx_details) if isinstance(snapshot.fx_details, dict) else {}

    # Profit panel / analytics: prefer agent-supplied context, fall back to
    # snapshot pre-computed values. The renderer never recomputes here.
    if not context.get("profit_panel") and snapshot.profit_panel:
        context["profit_panel"] = snapshot.profit_panel
    if not context.get("report_accuracy") and getattr(snapshot, "report_accuracy", None):
        context["report_accuracy"] = snapshot.report_accuracy
    if not context.get("realized_unrealized") and snapshot.realized_unrealized:
        context["realized_unrealized"] = snapshot.realized_unrealized
    if not _transaction_analytics(context) and snapshot.transaction_analytics:
        context["transaction_analytics"] = snapshot.transaction_analytics
    # §10.1.7 trading psychology is a mandatory agent-authored gate. Snapshot
    # fallback exists only for callers that explicitly pre-merge a validated
    # block into the snapshot; otherwise missing context is a render failure.
    if not context.get("trading_psychology") and snapshot.trading_psychology:
        context["trading_psychology"] = snapshot.trading_psychology

    context_errors = validate_report_context(context, serialize_snapshot(snapshot))
    if context_errors:
        print(
            f"ERROR: report_context failed pre-render validation "
            f"({len(context_errors)} problem(s)):",
            file=sys.stderr,
        )
        for err in context_errors:
            print(f"  - {err}", file=sys.stderr)
        print(
            "Run `python scripts/validate_report_context.py --snapshot "
            "report_snapshot.json --context report_context.json` before rendering.",
            file=sys.stderr,
        )
        return 7

    # Surface snapshot-side errors as data gaps.
    snapshot_errors = [
        ("profit_panel", snapshot.profit_panel_error),
        ("realized_unrealized", snapshot.realized_unrealized_error),
        ("transaction_analytics", snapshot.transaction_analytics_error),
    ]
    for key, msg in snapshot_errors:
        if not msg:
            continue
        gaps = context.setdefault("data_gaps", [])
        if isinstance(gaps, list):
            gaps.append({
                "summary": f"{key} pipeline error",
                "detail": msg,
            })

    if snapshot.missing_fx:
        logging.warning(
            "Non-%s currency in book without FX rate: %s. "
            "Affected aggregates will render as `n/a` per spec §9.0. "
            "Re-run scripts/fetch_prices.py so prices.json['_fx'] is populated.",
            snapshot.base_currency, ", ".join(snapshot.missing_fx),
        )

    css = load_canonical_css(args.sample)
    html_doc = render_html(snapshot, context, css, settings)

    if args.output is None:
        ts = _dt.datetime.now().strftime("%Y-%m-%d_%H%M")
        args.output = Path("reports") / f"{ts}_portfolio_report.html"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {args.output} ({len(html_doc):,} bytes)")

    try:
        m = re.search(r"(\d{4}-\d{2}-\d{2}_\d{4})", args.output.name)
        report_id = m.group(1) if m else args.output.stem
        # Demo-isolation guard: if the HTML lands under a `demo/` directory,
        # archive into `demo/transactions.db` so synthetic runs do not pollute
        # the production `report_archive` table. Mirrors the cache-isolation
        # discipline in fetch_history.py.
        archive_db = args.db if args.db else Path("transactions.db")
        out_parts = {p.lower() for p in args.output.resolve().parts}
        if "demo" in out_parts and Path(archive_db).resolve().name == "transactions.db" \
                and Path(archive_db).resolve().parent.name != "demo":
            demo_db = Path("demo/transactions.db")
            if demo_db.exists():
                print(
                    f"WARNING: --output is under demo/ but --db resolves to root "
                    f"{archive_db}; routing report_archive to {demo_db} so demo "
                    f"runs do not pollute production. Pass --db demo/transactions.db "
                    "explicitly to silence this warning.",
                    file=sys.stderr,
                )
                archive_db = demo_db
        _archive_report(
            report_id=report_id,
            snapshot_path=args.snapshot,
            context_path=args.context,
            html_path=args.output,
            db_path=archive_db,
        )
    except Exception as exc:  # noqa: BLE001 — never let archival block delivery
        # Surface to stderr in addition to the log so an agent running this in
        # a terminal sees the failure even if logging is muted.
        print(f"WARN: report_archive failed for {args.output}: {exc}", file=sys.stderr)
        logging.warning("report_archive: failed to persist %s: %s", args.output, exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
