from __future__ import annotations

import copy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from validate_report_context import validate_report_context  # noqa: E402


def _snapshot(ticker: str = "TACT", *, bucket: str = "Short Term", lots=None, market_value=5000):
    if lots is None:
        lots = [{"ticker": ticker, "bucket": bucket, "quantity": 10}]
    return {
        "aggregates": [
            {
                "ticker": ticker,
                "bucket": bucket,
                "market": "USA",
                "market_value": market_value,
                "lots": lots,
            }
        ],
        "totals": {"total_assets": 100000},
    }


def _theme_sector(ticker: str):
    return {
        "theme_sector_html": (
            '<div class="cols-2"><div class="bars">'
            '<div class="bar-row"><div class="bar-label">AI</div>'
            '<div class="bar-track"><div class="bar pos" style="width:50%"></div></div>'
            '<div class="bar-value">50%</div></div>'
            "</div></div>"
        ),
        "theme_sector_audit": {
            "tickers": {
                ticker: {
                    "sector": "Technology",
                    "themes": ["AI"],
                    "sources": ["synthetic fixture"],
                }
            }
        },
    }


def _quality_entry(
    ticker: str,
    *,
    horizon: str = "short_term",
    depth: str = "tactical",
    status: str | None = "wait",
    evidence=None,
    source_quality=None,
    relevance: str = "Earnings catalyst plus price trend changes wait/add decision.",
    audit: str | None = None,
    exception_reason=None,
    news_audit: bool = True,
    event_audit: bool = True,
):
    if evidence is None:
        evidence = ["catalyst", "technical"]
    if source_quality is None:
        source_quality = ["issuer", "market_data"]
    entry = {
        "news": {
            "count": 0,
            "audit": f"news_search:{ticker}:no_material_within_14d" if news_audit else "",
        },
        "events": {
            "count": 0,
            "audit": f"event_search:{ticker}:earnings_calendar_checked" if event_audit else "",
        },
        "horizon": horizon,
        "research_depth": depth,
        "decision_relevance": relevance,
        "evidence_classes": evidence,
        "source_quality": source_quality,
        "exception_reason": exception_reason,
    }
    if status is not None:
        entry["decision_or_thesis_status"] = status
    if audit is not None:
        entry["quality_audit"] = audit
    return entry


def _context(ticker: str = "TACT", entry: dict | None = None, *, quality_schema: str | None = "horizon_v1"):
    if entry is None:
        entry = _quality_entry(ticker)
    coverage = {"tickers": {ticker: entry}}
    if quality_schema is not None:
        coverage["quality_schema"] = quality_schema
    ctx = {
        "today_summary": ["Portfolio context fixture is valid."],
        "strategy_readout": "I keep evidence tied to decisions and size only when the setup is clear.",
        "data_gaps": [],
        **_theme_sector(ticker),
        "news": [],
        "events": [],
        "research_coverage": coverage,
        "adjustments": [
            {
                "ticker": ticker,
                "action": "hold",
                "action_label": "Hold",
                "why": "Fixture keeps recommendation table non-empty.",
                "trigger": "Review on next catalyst.",
            }
        ],
        "high_opps": [],
        "actions": {"must_do": [], "may_do": [], "avoid": [], "need_data": []},
        "reviewer_pass": {
            "completed": True,
            "reviewed_sections": [
                "alerts",
                "watchlist",
                "adjustments",
                "actions",
                "strategy_readout",
                "trading_psychology",
                "theme_sector",
                "news_events",
            ],
            "summary": [],
            "by_section": {},
        },
        "trading_psychology": {
            "headline": "Discipline is stable",
            "observations": [
                {
                    "behavior": "Position review is catalyst based.",
                    "evidence": "snapshot.aggregates[0].lots drives horizon classification",
                    "tone": "neu",
                }
            ],
            "improvements": [
                {
                    "issue": "Keep news tied to action.",
                    "suggestion": "Require decision relevance before render.",
                    "priority": "medium",
                }
            ],
        },
    }
    return ctx


def _errors(context, snapshot):
    return validate_report_context(context, snapshot)


def test_research_coverage_legacy_without_quality_schema_passes_old_rules():
    ticker = "LEG"
    entry = {
        "news": {"count": 0, "audit": "news_search:LEG:no_material_within_14d"},
        "events": {"count": 0, "audit": "event_search:LEG:calendar_checked"},
    }
    errors = _errors(_context(ticker, entry, quality_schema=None), _snapshot(ticker))
    assert errors == []


def test_horizon_v1_short_term_tactical_valid_passes():
    errors = _errors(_context(), _snapshot())
    assert errors == []


def test_horizon_v1_short_term_missing_decision_fails():
    entry = _quality_entry("TACT", status=None, evidence=["catalyst"])
    errors = _errors(_context("TACT", entry), _snapshot("TACT"))
    assert any("decision_or_thesis_status" in err for err in errors)
    assert any("at least two tactical evidence" in err for err in errors)


def test_horizon_v1_low_materiality_short_term_tactical_light_still_needs_status():
    snapshot = _snapshot("LOW", market_value=500)
    entry = _quality_entry(
        "LOW",
        status="wait",
        evidence=["catalyst"],
        audit="Low materiality short-term lot; catalyst search completed.",
        exception_reason="not_material_to_position",
    )
    assert _errors(_context("LOW", entry), snapshot) == []

    invalid = copy.deepcopy(entry)
    invalid.pop("decision_or_thesis_status")
    errors = _errors(_context("LOW", invalid), snapshot)
    assert any("decision_or_thesis_status" in err for err in errors)


def test_horizon_v1_mid_long_thesis_status_valid_passes():
    mid_entry = _quality_entry(
        "MID",
        horizon="mid_term",
        depth="thesis",
        status="intact",
        evidence=["primary_source", "valuation"],
        source_quality=["filing", "analyst_or_consensus"],
        relevance="Filing and valuation evidence keep the mid-term thesis intact.",
    )
    assert _errors(_context("MID", mid_entry), _snapshot("MID", bucket="Mid Term")) == []

    long_entry = _quality_entry(
        "CORE",
        horizon="long_term_core",
        depth="strategic",
        status="strategic_role_intact",
        evidence=["allocation_role", "industry_peer"],
        source_quality=["filing", "reputable_media"],
        relevance="Industry peer and allocation role evidence confirm the core role.",
    )
    assert _errors(_context("CORE", long_entry), _snapshot("CORE", bucket="Long Term")) == []


def test_horizon_v1_mixed_bucket_lots_first_requires_audit():
    lots = [
        {"ticker": "MIX", "bucket": "Short Term", "quantity": 1},
        {"ticker": "MIX", "bucket": "Long Term", "quantity": 2},
    ]
    snapshot = _snapshot("MIX", bucket="Long Term", lots=lots)
    entry = _quality_entry(
        "MIX",
        horizon="long_term_core",
        depth="strategic",
        status="strategic_role_intact",
        evidence=["allocation_role", "primary_source"],
        source_quality=["filing", "market_data"],
        relevance="Mixed lots are handled as a core thesis with separate tactical review.",
    )
    errors = _errors(_context("MIX", entry), snapshot)
    assert any("mixed bucket" in err for err in errors)

    entry["quality_audit"] = "Snapshot lots are mixed; short-term lot is immaterial and monitored separately."
    assert _errors(_context("MIX", entry), snapshot) == []


def test_horizon_v1_horizon_override_without_audit_fails():
    entry = _quality_entry(
        "OVR",
        horizon="mid_term",
        depth="thesis",
        status="intact",
        evidence=["primary_source", "valuation"],
        source_quality=["filing", "analyst_or_consensus"],
        relevance="Override to mid-term thesis based on source work.",
    )
    errors = _errors(_context("OVR", entry), _snapshot("OVR", bucket="Short Term"))
    assert any("conflicts with snapshot-derived" in err for err in errors)


def test_horizon_v1_placeholder_decision_relevance_fails():
    entry = _quality_entry("TACT", relevance="TODO")
    errors = _errors(_context("TACT", entry), _snapshot("TACT"))
    assert any("decision_relevance contains placeholder/generic text" in err for err in errors)


def test_horizon_v1_invalid_enums_fail():
    entry = _quality_entry(
        "ENUM",
        horizon="swing",
        depth="fast",
        status="maybe",
        evidence=["rumor"],
        source_quality=["blog"],
        exception_reason="because",
    )
    errors = _errors(_context("ENUM", entry), _snapshot("ENUM"))
    assert any(".horizon must be one of" in err for err in errors)
    assert any(".research_depth must be one of" in err for err in errors)
    assert any(".decision_or_thesis_status must be one of" in err for err in errors)
    assert any(".evidence_classes[0] must be one of" in err for err in errors)
    assert any(".source_quality[0] must be one of" in err for err in errors)
    assert any(".exception_reason must be one of" in err for err in errors)


def test_horizon_v1_covered_by_snapshot_with_news_event_audit_passes():
    entry = _quality_entry(
        "SNAP",
        audit="Technical computation is covered by snapshot; live news/event searches are audited.",
        exception_reason="covered_by_snapshot",
    )
    assert _errors(_context("SNAP", entry), _snapshot("SNAP")) == []


def test_horizon_v1_covered_by_snapshot_without_news_event_audit_fails():
    entry = _quality_entry(
        "SNAP",
        audit="Technical computation is covered by snapshot.",
        exception_reason="covered_by_snapshot",
        news_audit=False,
        event_audit=False,
    )
    errors = _errors(_context("SNAP", entry), _snapshot("SNAP"))
    assert any("needs a news item" in err for err in errors)
    assert any("needs a dated event" in err for err in errors)


def test_horizon_v1_public_flow_unavailable_with_other_evidence_passes():
    entry = _quality_entry(
        "FLOW",
        evidence=["catalyst", "expectation_delta"],
        source_quality=["issuer", "analyst_or_consensus", "unavailable_audited"],
        audit="Public flow data unavailable after audited search; catalyst and consensus evidence remain decision-grade.",
        exception_reason="public_data_unavailable",
    )
    assert _errors(_context("FLOW", entry), _snapshot("FLOW")) == []


def test_horizon_v1_unknown_bucket_need_data_valid_only_with_audit():
    snapshot = _snapshot("UNK", bucket="Experimental", lots=[{"ticker": "UNK", "bucket": "Experimental"}])
    entry = _quality_entry(
        "UNK",
        horizon="unknown",
        depth="need_data",
        status="need_data",
        evidence=["audited_absence"],
        source_quality=["unavailable_audited"],
        relevance="Unknown bucket blocks horizon-specific research depth until the lot is classified.",
        audit="Snapshot lot bucket is unknown; classify holding period before final judgment.",
        exception_reason="unknown_bucket_need_data",
    )
    assert _errors(_context("UNK", entry), snapshot) == []

    invalid = copy.deepcopy(entry)
    invalid.pop("quality_audit")
    errors = _errors(_context("UNK", invalid), snapshot)
    assert any("quality_audit required because snapshot horizon is unknown" in err for err in errors)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("OK")
