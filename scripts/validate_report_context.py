#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_report_context.py — pre-render gate for agent-authored report context.

This validates the editorial layer that cannot be computed by the snapshot:
research coverage, theme/sector classification, PM-grade recommendations,
strategy readout, mandatory trading_psychology, and reviewer pass metadata.

Recommended adjustments (`adjustments`) must be a non-empty list with at least one
agent-authored §10.9 row (`ticker`, `action`, `action_label`, `why`, `trigger`);
an empty array fails validation — express passivity with explicit hold / wait rows.

`trading_psychology` strings must be plain text (no HTML tags). Visual typography
for §10.1.7 is renderer-owned: `generate_report.render_trading_psychology` plus
appended `.psych-*` CSS uses the same scale/tokens as `.prose` / §14.9.

It is a validator, not a generator. Agents must author the content from
report_snapshot.json, SETTINGS.md, and current public research before render.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


ACTION_BUCKETS = ("must_do", "may_do", "avoid", "need_data")
ACTIONABLE_ACTIONS = {
    "add", "buy", "sell", "trim", "cut", "reduce", "increase", "hedge",
    "rebalance", "rotate", "switch",
}
NON_ACTION_STATUSES = {
    "hold", "watch", "wait", "avoid", "pass", "do not add", "no action",
    "need data", "monitor",
}
REQUIRED_REVIEW_SECTIONS = {
    "alerts",
    "watchlist",
    "adjustments",
    "actions",
    "strategy_readout",
    "trading_psychology",
    "theme_sector",
    "news_events",
}
VALID_PSYCHOLOGY_TONES = {"pos", "neu", "warn", "neg"}
VALID_PSYCHOLOGY_PRIORITIES = {"high", "medium", "low"}
PLACEHOLDER_RE = re.compile(
    r"(todo|tbd|placeholder|pending|pending agent|pending collection|pending input|"
    r"demo run audit|待補|占位|示範|流程示範|請補|請接|待 agent|agent 補入|"
    r"假新聞|假催化)",
    re.IGNORECASE,
)

# Disallow raw HTML in psychology prose — the renderer escapes text; tags indicate copy-paste errors.
# Require `<` to be immediately followed by an optional `/` and a tag name (not `x < y` comparisons).
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9:-]*")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_placeholder(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(PLACEHOLDER_RE.search(value))
    return bool(PLACEHOLDER_RE.search(json.dumps(value, ensure_ascii=False, default=str)))


def _cover_tickers(snapshot: Dict[str, Any]) -> List[str]:
    tickers: List[str] = []
    for agg in snapshot.get("aggregates") or []:
        if not isinstance(agg, dict):
            continue
        ticker = str(agg.get("ticker") or "").strip()
        if not ticker:
            continue
        market = str(agg.get("market") or "").lower()
        if agg.get("is_cash") or market == "cash":
            continue
        tickers.append(ticker.upper())
    return sorted(set(tickers))


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _contains_ticker_audit(data_gaps: Any, prefix: str, ticker: str) -> bool:
    needle = f"{prefix}:{ticker}".lower()
    haystack = json.dumps(data_gaps or [], ensure_ascii=False, default=str).lower()
    return needle in haystack


def _check_str_field(
    name: str,
    value: Any,
    *,
    max_len: Optional[int] = None,
    allow_empty: bool = False,
) -> List[str]:
    if not isinstance(value, str):
        return [f"{name} must be a string, got {type(value).__name__}"]
    if not value.strip() and not allow_empty:
        return [f"{name} must not be empty"]
    if max_len is not None and len(value) > max_len:
        return [f"{name} length {len(value)} exceeds max {max_len}"]
    return []


def _event_matches_ticker(event: Any, ticker: str) -> bool:
    if not isinstance(event, dict):
        return False
    topic = str(event.get("topic") or "").upper()
    event_text = str(event.get("event") or "").upper()
    return topic == ticker or ticker in topic.split() or ticker in event_text


def _news_matches_ticker(item: Any, ticker: str) -> bool:
    return isinstance(item, dict) and str(item.get("ticker") or "").upper() == ticker


def _intish(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_strategy_readout(context: Dict[str, Any], errors: List[str]) -> None:
    value = context.get("strategy_readout") or context.get("style_readout")
    if not _is_nonempty_str(value):
        errors.append("strategy_readout must be present and non-empty")
        return
    text = str(value).strip()
    if _has_placeholder(text):
        errors.append("strategy_readout contains placeholder text")
    if len(text) > 700:
        errors.append(f"strategy_readout length {len(text)} exceeds max 700 chars")
    words = [w for w in re.split(r"\s+", text) if w]
    if len(words) > 90 and len(words) != len(text):
        errors.append(f"strategy_readout has {len(words)} words; max is 90")
    if not any(token in text for token in ("我", "I ", "I'm", "I’m", "我的")):
        errors.append("strategy_readout must be first-person")


def _validate_today_summary(context: Dict[str, Any], errors: List[str]) -> None:
    summary = context.get("today_summary")
    if not isinstance(summary, list) or not any(_is_nonempty_str(x) for x in summary):
        errors.append("today_summary must be a non-empty list of strings")
        return
    if _has_placeholder(summary):
        errors.append("today_summary contains placeholder text")


def _validate_theme_sector(
    context: Dict[str, Any],
    cover_tickers: Sequence[str],
    errors: List[str],
) -> None:
    if not cover_tickers:
        return
    html = context.get("theme_sector_html")
    if not _is_nonempty_str(html):
        errors.append("theme_sector_html is required for non-cash holdings")
    else:
        html_text = str(html)
        for token in ('class="cols-2"', 'class="bars"', 'bar-row', 'bar-label', 'bar-track', 'bar-value'):
            if token not in html_text:
                errors.append(f"theme_sector_html missing required markup token {token!r}")
        if _has_placeholder(html_text):
            errors.append("theme_sector_html contains placeholder text")

    audit = context.get("theme_sector_audit")
    if not isinstance(audit, dict):
        errors.append("theme_sector_audit must be present as an object")
        return
    tickers = audit.get("tickers")
    if not isinstance(tickers, dict):
        errors.append("theme_sector_audit.tickers must be an object keyed by ticker")
        return
    audit_keys = {str(k).upper(): v for k, v in tickers.items()}
    for ticker in cover_tickers:
        item = audit_keys.get(ticker)
        if not isinstance(item, dict):
            errors.append(f"theme_sector_audit.tickers.{ticker} missing")
            continue
        if not _is_nonempty_str(item.get("sector")):
            errors.append(f"theme_sector_audit.tickers.{ticker}.sector must be non-empty")
        themes = item.get("themes")
        if isinstance(themes, dict):
            has_theme = any(str(k).strip() and v not in (None, "", 0, 0.0) for k, v in themes.items())
        elif isinstance(themes, list):
            has_theme = any(_is_nonempty_str(x) or isinstance(x, dict) for x in themes)
        else:
            has_theme = False
        if not has_theme:
            errors.append(f"theme_sector_audit.tickers.{ticker}.themes must be non-empty")
        sources = item.get("sources") or item.get("source")
        if isinstance(sources, list):
            has_source = any(_is_nonempty_str(x) for x in sources)
        else:
            has_source = _is_nonempty_str(sources)
        if not has_source:
            errors.append(f"theme_sector_audit.tickers.{ticker}.sources must cite at least one source")


def _coverage_entry_counts(entry: Dict[str, Any], kind: str) -> Tuple[Optional[int], str]:
    direct = _intish(entry.get(f"{kind}_count"))
    if direct is not None:
        return direct, str(entry.get(f"{kind}_audit") or entry.get(f"{kind}_search") or "")
    node = entry.get(kind)
    if isinstance(node, dict):
        count = _intish(node.get("count"))
        if count is None and isinstance(node.get("items"), list):
            count = len(node.get("items") or [])
        audit = str(node.get("audit") or node.get("search") or "")
        return count, audit
    if isinstance(node, list):
        return len(node), ""
    return None, str(entry.get(f"{kind}_audit") or entry.get(f"{kind}_search") or "")


def _validate_research_coverage(
    context: Dict[str, Any],
    cover_tickers: Sequence[str],
    errors: List[str],
) -> None:
    if not cover_tickers:
        return
    coverage = context.get("research_coverage")
    if not isinstance(coverage, dict):
        errors.append("research_coverage must be present as an object")
        return
    tickers_node = coverage.get("tickers")
    if not isinstance(tickers_node, dict):
        errors.append("research_coverage.tickers must be an object keyed by ticker")
        return
    coverage_by_ticker = {str(k).upper(): v for k, v in tickers_node.items()}
    news = _as_list(context.get("news"))
    events = _as_list(context.get("events"))
    data_gaps = context.get("data_gaps")
    for ticker in cover_tickers:
        entry = coverage_by_ticker.get(ticker)
        if not isinstance(entry, dict):
            errors.append(f"research_coverage.tickers.{ticker} missing")
            continue
        if _has_placeholder(entry):
            errors.append(f"research_coverage.tickers.{ticker} contains placeholder/demo audit text")
        news_count, news_audit = _coverage_entry_counts(entry, "news")
        event_count, event_audit = _coverage_entry_counts(entry, "events")
        has_news_item = any(_news_matches_ticker(item, ticker) for item in news)
        has_event_item = any(_event_matches_ticker(item, ticker) for item in events)
        # Per §10.5/§10.6 of docs/portfolio_report_agent_guidelines, when a
        # ticker has no news / events the audit trail must demonstrate the
        # live search actually happened. We accept either:
        #   1. a `data_gaps` entry tagged `news_search:<ticker>` /
        #      `event_search:<ticker>`, or
        #   2. an audit string on the coverage entry that starts with the
        #      structured tag (e.g. `news_search:NVDA:no_material_within_14d`).
        # A freeform string like `news_audit:"no news"` no longer counts —
        # that bypassed the live-research workflow contract.
        news_tag_prefix = f"news_search:{ticker}"
        event_tag_prefix = f"event_search:{ticker}"
        has_news_audit = (
            _contains_ticker_audit(data_gaps, "news_search", ticker)
            or news_audit.strip().lower().startswith(news_tag_prefix.lower())
        )
        has_event_audit = (
            _contains_ticker_audit(data_gaps, "event_search", ticker)
            or event_audit.strip().lower().startswith(event_tag_prefix.lower())
        )
        if not has_news_item and not (news_count == 0 and has_news_audit):
            errors.append(
                f"{ticker} needs a news item, an audit string starting "
                f"`news_search:{ticker}:...`, or a data_gaps entry tagged "
                f"`news_search:{ticker}`"
            )
        if not has_event_item and not (event_count == 0 and has_event_audit):
            errors.append(
                f"{ticker} needs a dated event, an audit string starting "
                f"`event_search:{ticker}:...`, or a data_gaps entry tagged "
                f"`event_search:{ticker}`"
            )


def _validate_reviewer_pass(context: Dict[str, Any], errors: List[str]) -> None:
    reviewer = context.get("reviewer_pass")
    if not isinstance(reviewer, dict):
        errors.append("reviewer_pass must be present as an object")
        return
    if reviewer.get("completed") is not True:
        errors.append("reviewer_pass.completed must be true")
    reviewed = reviewer.get("reviewed_sections")
    if not isinstance(reviewed, list):
        errors.append("reviewer_pass.reviewed_sections must be a list")
        reviewed_set: Set[str] = set()
    else:
        reviewed_set = {str(x) for x in reviewed}
    missing = sorted(REQUIRED_REVIEW_SECTIONS - reviewed_set)
    if missing:
        errors.append("reviewer_pass.reviewed_sections missing: " + ", ".join(missing))
    if not isinstance(reviewer.get("summary"), list):
        errors.append("reviewer_pass.summary must be a list (use [] when clean)")
    if not isinstance(reviewer.get("by_section"), dict):
        errors.append("reviewer_pass.by_section must be an object (use {} when clean)")
    if _has_placeholder(reviewer):
        errors.append("reviewer_pass contains placeholder/demo text")


def _validate_trading_psychology_observation(idx: int, item: Any, errors: List[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"trading_psychology.observations[{idx}] must be an object")
        return
    errors.extend(
        f"trading_psychology.{err}"
        for err in _check_str_field(f"observations[{idx}].behavior", item.get("behavior"), max_len=200)
    )
    errors.extend(
        f"trading_psychology.{err}"
        for err in _check_str_field(f"observations[{idx}].evidence", item.get("evidence"), max_len=240)
    )
    tone = item.get("tone")
    if tone not in VALID_PSYCHOLOGY_TONES:
        errors.append(
            f"trading_psychology.observations[{idx}].tone must be one of "
            f"{sorted(VALID_PSYCHOLOGY_TONES)}, got {tone!r}"
        )
    evidence = (item.get("evidence") or "").strip().lower()
    if evidence in {"", "todo", "tbd", "n/a", "na", "?", "(see snapshot)", "snapshot"}:
        errors.append(
            f"trading_psychology.observations[{idx}].evidence is a placeholder "
            f"({evidence!r}); anchor it to a specific snapshot data path"
        )


def _validate_trading_psychology_improvement(idx: int, item: Any, errors: List[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"trading_psychology.improvements[{idx}] must be an object")
        return
    errors.extend(
        f"trading_psychology.{err}"
        for err in _check_str_field(f"improvements[{idx}].issue", item.get("issue"), max_len=200)
    )
    errors.extend(
        f"trading_psychology.{err}"
        for err in _check_str_field(f"improvements[{idx}].suggestion", item.get("suggestion"), max_len=320)
    )
    priority = item.get("priority")
    if priority not in VALID_PSYCHOLOGY_PRIORITIES:
        errors.append(
            f"trading_psychology.improvements[{idx}].priority must be one of "
            f"{sorted(VALID_PSYCHOLOGY_PRIORITIES)}, got {priority!r}"
        )


def _validate_trading_psychology_strength(idx: int, item: Any, errors: List[str]) -> None:
    if isinstance(item, str):
        if not item.strip():
            errors.append(f"trading_psychology.strengths[{idx}] string must not be empty")
        return
    if not isinstance(item, dict):
        errors.append(f"trading_psychology.strengths[{idx}] must be a string or object")
        return
    errors.extend(
        f"trading_psychology.{err}"
        for err in _check_str_field(f"strengths[{idx}].behavior", item.get("behavior"), max_len=200)
    )
    if "evidence" in item:
        errors.extend(
            f"trading_psychology.{err}"
            for err in _check_str_field(
                f"strengths[{idx}].evidence",
                item.get("evidence"),
                max_len=240,
                allow_empty=True,
            )
        )


def _psych_field_must_be_plain_text(field_path: str, value: Any, errors: List[str]) -> None:
    if not isinstance(value, str):
        return
    if _HTML_TAG_RE.search(value):
        errors.append(f"{field_path} must be plain text without HTML tags")


def _validate_trading_psychology_plain_text(payload: Dict[str, Any], errors: List[str]) -> None:
    _psych_field_must_be_plain_text("trading_psychology.headline", payload.get("headline"), errors)
    for idx, item in enumerate(payload.get("observations") or []):
        if isinstance(item, dict):
            _psych_field_must_be_plain_text(
                f"trading_psychology.observations[{idx}].behavior", item.get("behavior"), errors
            )
            _psych_field_must_be_plain_text(
                f"trading_psychology.observations[{idx}].evidence", item.get("evidence"), errors
            )
    for idx, item in enumerate(payload.get("improvements") or []):
        if isinstance(item, dict):
            _psych_field_must_be_plain_text(
                f"trading_psychology.improvements[{idx}].issue", item.get("issue"), errors
            )
            _psych_field_must_be_plain_text(
                f"trading_psychology.improvements[{idx}].suggestion", item.get("suggestion"), errors
            )
    for idx, item in enumerate(payload.get("strengths") or []):
        if isinstance(item, str):
            _psych_field_must_be_plain_text(f"trading_psychology.strengths[{idx}]", item, errors)
        elif isinstance(item, dict):
            _psych_field_must_be_plain_text(
                f"trading_psychology.strengths[{idx}].behavior", item.get("behavior"), errors
            )
            if "evidence" in item:
                _psych_field_must_be_plain_text(
                    f"trading_psychology.strengths[{idx}].evidence", item.get("evidence"), errors
                )


def _validate_trading_psychology(context: Dict[str, Any], errors: List[str]) -> None:
    if "trading_psychology" not in context:
        errors.append("trading_psychology is mandatory")
        return
    payload = context.get("trading_psychology")
    if payload is None:
        errors.append("trading_psychology must not be null")
        return
    if not isinstance(payload, dict):
        errors.append(f"trading_psychology must be an object, got {type(payload).__name__}")
        return

    errors.extend(
        f"trading_psychology.{err}"
        for err in _check_str_field("headline", payload.get("headline"), max_len=120)
    )

    observations = payload.get("observations")
    if not isinstance(observations, list) or len(observations) < 1:
        errors.append("trading_psychology.observations must be a non-empty array")
    else:
        if len(observations) > 6:
            errors.append(f"trading_psychology.observations length {len(observations)} exceeds max 6")
        for idx, item in enumerate(observations):
            _validate_trading_psychology_observation(idx, item, errors)

    improvements = payload.get("improvements")
    if not isinstance(improvements, list) or len(improvements) < 1:
        errors.append("trading_psychology.improvements must be a non-empty array")
    else:
        if len(improvements) > 6:
            errors.append(f"trading_psychology.improvements length {len(improvements)} exceeds max 6")
        for idx, item in enumerate(improvements):
            _validate_trading_psychology_improvement(idx, item, errors)

    strengths = payload.get("strengths")
    if strengths is not None:
        if not isinstance(strengths, list):
            errors.append("trading_psychology.strengths must be an array (omit the key entirely if none)")
        else:
            if len(strengths) > 4:
                errors.append(f"trading_psychology.strengths length {len(strengths)} exceeds max 4")
            for idx, item in enumerate(strengths):
                _validate_trading_psychology_strength(idx, item, errors)

    _validate_trading_psychology_plain_text(payload, errors)


def _is_actionable(item: Dict[str, Any]) -> bool:
    status = str(item.get("status") or item.get("action") or "").strip().lower()
    if status in NON_ACTION_STATUSES:
        return False
    if item.get("actionable") is False:
        return False
    if item.get("variant_tag") == "rebalance":
        return True
    if item.get("sized_pp_delta") not in (None, "", 0, 0.0):
        return True
    if item.get("target_pct") not in (None, ""):
        return True
    return status in ACTIONABLE_ACTIONS or item.get("actionable") is True


def _has_rr_inputs(item: Dict[str, Any]) -> bool:
    if item.get("variant_tag") == "rebalance":
        return True
    if item.get("binary_catalyst") or item.get("hedged_structure") or item.get("rr_structural_reason"):
        return True
    return all(item.get(k) not in (None, "") for k in ("entry_price", "target_price", "stop_price"))


def _validate_pm_block(item: Dict[str, Any], where: str, errors: List[str]) -> None:
    for key in ("ticker", "action", "why", "trigger"):
        if not _is_nonempty_str(item.get(key)):
            errors.append(f"{where}.{key} must be non-empty")
    if item.get("sized_pp_delta") in (None, "") and item.get("target_pct") in (None, ""):
        errors.append(f"{where} needs sized_pp_delta or target_pct")
    if item.get("variant_tag") == "rebalance":
        if not _is_nonempty_str(item.get("kill_action")):
            errors.append(f"{where}.kill_action required for rebalance housekeeping")
        return
    for key in ("variant_tag", "consensus", "anchor", "failure_mode", "kill_trigger", "kill_action"):
        if not _is_nonempty_str(item.get(key)):
            errors.append(f"{where}.{key} must be non-empty for actionable item")
    if item.get("variant_tag") in {"variant", "contrarian"} and not _is_nonempty_str(item.get("variant")):
        errors.append(f"{where}.variant must be non-empty for variant/contrarian item")
    if not _has_rr_inputs(item):
        errors.append(f"{where} needs R:R inputs (entry_price, target_price, stop_price) or an allowed structural exception")


def _validate_adjustments(context: Dict[str, Any], errors: List[str]) -> None:
    adjs = context.get("adjustments")
    if adjs is None:
        errors.append("adjustments must be present as a non-empty list (agent §10.9)")
        return
    if not isinstance(adjs, list):
        errors.append("adjustments must be a list")
        return
    if len(adjs) < 1:
        errors.append(
            "adjustments must contain at least one recommendation row; "
            "use explicit hold / wait rows with triggers instead of []"
        )
        return
    for idx, item in enumerate(adjs):
        if not isinstance(item, dict):
            errors.append(f"adjustments[{idx}] must be an object")
            continue
        if _has_placeholder(item):
            errors.append(f"adjustments[{idx}] contains placeholder text")
        base_keys = ("ticker", "action", "why", "trigger", "action_label")
        for key in base_keys:
            if not _is_nonempty_str(item.get(key)):
                errors.append(f"adjustments[{idx}].{key} must be non-empty")
        if _is_actionable(item):
            _validate_pm_block(item, f"adjustments[{idx}]", errors)


def _validate_high_opps(context: Dict[str, Any], errors: List[str]) -> None:
    opps = context.get("high_opps")
    if opps is None:
        errors.append("high_opps must be present as a list (use [] when none)")
        return
    if not isinstance(opps, list):
        errors.append("high_opps must be a list")
        return
    for idx, item in enumerate(opps):
        if not isinstance(item, dict):
            errors.append(f"high_opps[{idx}] must be an object")
            continue
        if "actionable" not in item:
            errors.append(f"high_opps[{idx}].actionable must be explicit true/false")
        if item.get("actionable") is True:
            _validate_pm_block(item, f"high_opps[{idx}]", errors)
        else:
            if not _is_nonempty_str(item.get("ticker")):
                errors.append(f"high_opps[{idx}].ticker must be non-empty")
            if not _is_nonempty_str(item.get("why")):
                errors.append(f"high_opps[{idx}].why must be non-empty")
            if not (_is_nonempty_str(item.get("trigger")) or _is_nonempty_str(item.get("watch"))):
                errors.append(f"high_opps[{idx}] needs trigger or watch when not actionable")


def _validate_actions(context: Dict[str, Any], errors: List[str]) -> None:
    actions = context.get("actions")
    if not isinstance(actions, dict):
        errors.append("actions must be present as an object with four buckets")
        return
    for bucket in ACTION_BUCKETS:
        if bucket not in actions:
            errors.append(f"actions.{bucket} bucket missing")
            continue
        if not isinstance(actions[bucket], list):
            errors.append(f"actions.{bucket} must be a list")
            continue
        for idx, item in enumerate(actions[bucket]):
            where = f"actions.{bucket}[{idx}]"
            if bucket in {"avoid", "need_data"}:
                if not (_is_nonempty_str(item) or isinstance(item, dict)):
                    errors.append(f"{where} must be a string or object")
                continue
            if not isinstance(item, dict):
                errors.append(f"{where} must be a structured object; use need_data for unstructured notes")
                continue
            if _has_placeholder(item):
                errors.append(f"{where} contains placeholder text")
            if _is_actionable(item):
                _validate_pm_block(item, where, errors)
            elif not (_is_nonempty_str(item.get("text")) or _is_nonempty_str(item.get("why"))):
                errors.append(f"{where} non-action object needs text or why")


def _validate_data_gaps(context: Dict[str, Any], errors: List[str]) -> None:
    gaps = context.get("data_gaps")
    if gaps is None:
        errors.append("data_gaps must be present as a list (use [] when clean)")
    elif not isinstance(gaps, list):
        errors.append("data_gaps must be a list")
    elif _has_placeholder(gaps):
        errors.append("data_gaps contains placeholder/demo audit text")


def validate_report_context(context: Dict[str, Any], snapshot: Dict[str, Any]) -> List[str]:
    """Return validation errors for the agent-authored report context."""
    if not isinstance(context, dict):
        return ["context must be a JSON object"]
    if not isinstance(snapshot, dict):
        return ["snapshot must be a JSON object"]

    errors: List[str] = []
    cover_tickers = _cover_tickers(snapshot)

    _validate_today_summary(context, errors)
    _validate_strategy_readout(context, errors)
    _validate_data_gaps(context, errors)
    _validate_theme_sector(context, cover_tickers, errors)
    _validate_research_coverage(context, cover_tickers, errors)
    _validate_adjustments(context, errors)
    _validate_high_opps(context, errors)
    _validate_actions(context, errors)
    _validate_reviewer_pass(context, errors)
    _validate_trading_psychology(context, errors)

    return errors


def _cli(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", required=True, type=Path)
    p.add_argument("--context", required=True, type=Path)
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _cli(argv)
    if not args.snapshot.exists():
        print(f"ERROR: snapshot not found: {args.snapshot}", file=sys.stderr)
        return 2
    if not args.context.exists():
        print(f"ERROR: context not found: {args.context}", file=sys.stderr)
        return 2
    try:
        snapshot = _load_json(args.snapshot)
        context = _load_json(args.context)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        return 2

    errors = validate_report_context(context, snapshot)
    if not errors:
        print("OK: report_context is valid.")
        return 0
    print(f"FAIL: {len(errors)} report_context problem(s):", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
