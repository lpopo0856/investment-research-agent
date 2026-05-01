#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_accuracy.py — deterministic data-quality scores for the portfolio report.

Computes a small set of 0–100 sub-scores from the snapshot inputs the profit
panel already uses (prices payload, profit_panel audits, pipeline errors) and
one headline ``overall`` score. The renderer displays these under §10.1.5;
they are not investment advice.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_RECON_GAP_RE = re.compile(
    r"P&L differs from realized \+ unrealized_delta by (-?\d+(?:\.\d+)?)",
)
_NO_HIST = re.compile(r"no historical close at", re.I)
_NO_HIST_NO_PX = re.compile(
    r"no historical close at .+ and no latest price",
    re.I,
)
_UNREAL_EX = re.compile(r"unrealized excluded", re.I)
_MISS_PX = re.compile(r"missing price for", re.I)
_NO_FX_HIST = re.compile(r"no _fx_history", re.I)
_USING_CUR = re.compile(r"using current latest", re.I)


def _flatten_audits(panel: Optional[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    if not isinstance(panel, dict):
        return lines
    for row in panel.get("rows") or []:
        if not isinstance(row, dict):
            continue
        for a in row.get("audit") or []:
            if isinstance(a, str) and a.strip():
                lines.append(a.strip())
    for key in ("open_position_audit", "issues"):
        for a in panel.get(key) or []:
            if isinstance(a, str) and a.strip():
                lines.append(a.strip())
    return lines


def _reconciliation_gaps(panel: Optional[Dict[str, Any]]) -> Tuple[float, float]:
    """Return (max_abs_gap, max_relative_gap) using row pnl as denominator."""
    max_abs = 0.0
    max_rel = 0.0
    if not isinstance(panel, dict):
        return max_abs, max_rel
    for row in panel.get("rows") or []:
        if not isinstance(row, dict):
            continue
        pnl = row.get("pnl")
        try:
            pnl_f = float(pnl) if pnl is not None else 0.0
        except (TypeError, ValueError):
            pnl_f = 0.0
        for a in row.get("audit") or []:
            if not isinstance(a, str):
                continue
            m = _RECON_GAP_RE.search(a)
            if not m:
                continue
            gap = float(m.group(1))
            abs_gap = abs(gap)
            max_abs = max(max_abs, abs_gap)
            denom = max(abs(pnl_f), 1.0)
            max_rel = max(max_rel, abs_gap / denom)
    return max_abs, max_rel


def _boundary_counts(audits: List[str]) -> Dict[str, int]:
    no_close_no_px = sum(1 for a in audits if _NO_HIST_NO_PX.search(a))
    # Avoid double-count: "no close ... and no latest" also matches the looser no-hist pattern.
    hist_only = sum(
        1 for a in audits if _NO_HIST.search(a) and not _NO_HIST_NO_PX.search(a)
    )
    return {
        "no_historical_close": hist_only,
        "no_close_and_no_latest": no_close_no_px,
        "unrealized_excluded": sum(1 for a in audits if _UNREAL_EX.search(a)),
        "missing_price": sum(1 for a in audits if _MISS_PX.search(a)),
        "no_fx_history": sum(1 for a in audits if _NO_FX_HIST.search(a)),
        "using_current_latest": sum(1 for a in audits if _USING_CUR.search(a)),
    }


def _score_boundary(counts: Dict[str, int]) -> float:
    penalty = (
        counts["no_close_and_no_latest"] * 14.0
        + counts["missing_price"] * 7.0
        + counts["unrealized_excluded"] * 5.0
        + counts["no_historical_close"] * 1.5
        + counts["using_current_latest"] * 2.5
        + counts["no_fx_history"] * 4.0
    )
    return max(0.0, min(100.0, 100.0 - penalty))


def _score_reconciliation(max_abs: float, max_rel: float) -> float:
    if max_abs < 1.0:
        return 100.0
    # Relative stress: cap contribution
    rel_penalty = min(70.0, max_rel * 120.0)
    abs_penalty = min(40.0, max_abs / 5000.0 * 40.0)
    return max(0.0, min(100.0, 100.0 - 0.5 * rel_penalty - 0.5 * abs_penalty))


def _quote_scores(
    prices: Dict[str, Any],
    tickers: List[str],
) -> Tuple[float, float, Dict[str, int]]:
    """Return (coverage_0_100, freshness_0_100, counts)."""
    n = len(tickers)
    if n == 0:
        return 100.0, 100.0, {"tickers": 0, "with_price": 0, "fresh": 0, "delayed": 0, "stale": 0}
    with_price = 0
    fresh = 0
    delayed = 0
    stale = 0
    for t in tickers:
        p = prices.get(t)
        if not isinstance(p, dict):
            continue
        if p.get("latest_price") is None:
            continue
        with_price += 1
        fr = str(p.get("price_freshness") or "").lower()
        if fr == "fresh":
            fresh += 1
        elif fr == "delayed":
            delayed += 1
        else:
            stale += 1
    coverage = 100.0 * with_price / n if n else 100.0
    if with_price == 0:
        freshness = 0.0
    else:
        # Delayed still counts as usable for a daily note; stale/n/a hurt more.
        freshness = 100.0 * (fresh + 0.75 * delayed + 0.35 * stale) / with_price
        freshness = max(0.0, min(100.0, freshness))
    counts = {
        "tickers": n,
        "with_price": with_price,
        "fresh": fresh,
        "delayed": delayed,
        "stale": stale,
    }
    return round(coverage, 2), round(freshness, 2), counts


def _pipeline_score(errors: Optional[Dict[str, Optional[str]]]) -> Tuple[float, int]:
    if not errors:
        return 100.0, 0
    bad = sum(1 for v in errors.values() if v)
    if bad == 0:
        return 100.0, 0
    # One failing subsystem is severe for numeric sections.
    return max(0.0, 100.0 - 40.0 * bad), bad


def _overall_band(score: float) -> str:
    if score >= 80.0:
        return "high"
    if score >= 55.0:
        return "medium"
    return "low"


def compute_report_accuracy(
    *,
    profit_panel: Optional[Dict[str, Any]],
    prices: Dict[str, Any],
    position_tickers: List[str],
    missing_fx: Optional[List[str]] = None,
    errors: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, Any]:
    """Build the ``report_accuracy`` object stored on the snapshot JSON.

    ``position_tickers`` should be non-cash tickers currently in open lots
    (same universe as ``fetch_prices``); used only for quote coverage/freshness.
    """
    missing_fx = missing_fx or []
    errors = errors or {}

    cov, fresh, q_counts = _quote_scores(prices, position_tickers)
    fx_penalty = min(30.0, 10.0 * len(missing_fx))
    cov_adj = max(0.0, cov - fx_penalty)

    audits = _flatten_audits(profit_panel)
    b_counts = _boundary_counts(audits)
    boundary_score = _score_boundary(b_counts)
    max_abs, max_rel = _reconciliation_gaps(profit_panel)
    recon_score = _score_reconciliation(max_abs, max_rel)

    pipe_score, pipe_errors = _pipeline_score(errors)

    if profit_panel is None and errors.get("profit_panel"):
        boundary_score = min(boundary_score, 20.0)
        recon_score = min(recon_score, 20.0)

    weights = (0.28, 0.18, 0.32, 0.17, 0.05)
    overall = (
        weights[0] * cov_adj
        + weights[1] * fresh
        + weights[2] * boundary_score
        + weights[3] * recon_score
        + weights[4] * pipe_score
    )
    overall = round(max(0.0, min(100.0, overall)), 1)

    return {
        "schema": "report_accuracy/1",
        "overall": {
            "score": overall,
            "band": _overall_band(overall),
        },
        "dimensions": [
            {
                "id": "quote_coverage",
                "score": round(cov_adj, 1),
                "detail": q_counts,
            },
            {
                "id": "quote_freshness",
                "score": round(fresh, 1),
                "detail": q_counts,
            },
            {
                "id": "profit_boundary",
                "score": round(boundary_score, 1),
                "detail": b_counts,
            },
            {
                "id": "profit_reconciliation",
                "score": round(recon_score, 1),
                "detail": {"max_abs_gap": round(max_abs, 2), "max_rel_gap": round(max_rel, 6)},
            },
            {
                "id": "pipeline",
                "score": round(pipe_score, 1),
                "detail": {"hard_errors": pipe_errors},
            },
        ],
        "meta": {
            "missing_fx_currencies": list(missing_fx),
            "audit_lines": len(audits),
        },
    }


__all__ = ["compute_report_accuracy"]
