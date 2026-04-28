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
        --holdings HOLDINGS.md \
        --settings SETTINGS.md \
        --prices prices.json \
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
      "fx":            {"USD/TWD": 30.0},   # keyed "<base>/<ccy>" — base is from SETTINGS.md (default USD)
      "next_event":    "01-03 央行決議",
      "today_summary": ["paragraph 1", "paragraph 2"],
      "alerts":        ["bullet 1", "bullet 2"],
      "news":          [{"ticker": "DELT", "date": "2026-04-27", "headline": "...",
                          "url": "...", "source": "Reuters", "impact": "neg"}, ...],
      "events":        [{"date": "01-08", "topic": "DELT", "event": "本季財報",
                          "impact_label": "高", "impact_class": "warn", "watch": "..."},
                         ...],
      "high_opps":     [{"ticker": "ZETA", "why": "...", "trigger": "260 突破加碼"}, ...],
      "adjustments":   [{"ticker": "KAPA", "current_pct": 4.5, "action": "trim",
                          "action_label": "減碼 20%", "why": "...", "trigger": "..."},
                         ...],
      "holdings_actions": {"BTC": "長線續抱；50–55k 分批加碼", ...},
      "actions":       {"must_do": ["..."], "may_do": ["..."],
                         "avoid": ["..."],  "need_data": ["..."]},
      "data_gaps":     [{"summary": "ALPH 成本基礎缺失",
                          "detail": "<HOLDINGS.md → Long Term> 內 ALPH 1 @ ? on ..."}, ...],
      "spec_update_note": "...",

      "theme_sector_html": "<div class=\"bars\">...</div>"
    }

REQUIRED EDITORIAL HTML — `theme_sector_html` (spec §10.4.2)
-------------------------------------------------------------
The agent **must** auto-classify each holding by sector / theme each run and
pre-render the bar chart as a string of HTML. The script does NOT compute this
because the classification depends on current public-data context, not just the
ticker. If `theme_sector_html` is missing, the section renders a placeholder
telling the user the agent skipped this step.

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
USD-based (§9.0). Bucket-note thresholds are configurable via SETTINGS.md.

Every other field is optional; missing fields render as `n/a` per §9.6 with no
guesses.

The "Sources & data gaps" audit table is built mechanically from `prices.json` —
the agent does not need to author it.

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

# Reuse the parser + market routing from the sister script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_prices import (                                    # noqa: E402
    Lot,
    MarketType,
    parse_holdings,
)


# ----------------------------------------------------------------------------- #
# Defaults — mirror SETTINGS.example.md "Position sizing rails" so warnings fire.
# ----------------------------------------------------------------------------- #

DEFAULTS = {
    "single_name_weight_warn_pct": 15.0,    # §11 special check #1
    "theme_concentration_warn_pct": 25.0,   # §11 #2
    "high_vol_bucket_warn_pct": 30.0,       # §11 #3
    "single_day_move_alert_pct": 8.0,       # §10.6 alert #4
    "earnings_within_days": 7,              # §10.6 alert #5
    "earnings_weight_pct": 5.0,             # §10.6 alert #5
    "above_target_pct": 20.0,               # §10.6 alert #7
}


# ----------------------------------------------------------------------------- #
# SETTINGS.md parsing + language resolution
# ----------------------------------------------------------------------------- #

LANGUAGE_ALIASES = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "zh-hant": "zh-Hant",
    "zh-tw": "zh-Hant",
    "traditional chinese": "zh-Hant",
    "traditional chinese (taiwan)": "zh-Hant",
    "繁體中文": "zh-Hant",
    "繁体中文": "zh-Hant",
    "zh-hans": "zh-Hans",
    "zh-cn": "zh-Hans",
    "simplified chinese": "zh-Hans",
    "簡體中文": "zh-Hans",
    "简体中文": "zh-Hans",
    "ja": "ja",
    "jp": "ja",
    "japanese": "ja",
    "日本語": "ja",
    "ko": "ko",
    "korean": "ko",
    "한국어": "ko",
    "vi": "vi",
    "vietnamese": "vi",
    "tiếng việt": "vi",
}

DISPLAY_NAME_BY_LOCALE = {
    "en": "English",
    "zh-Hant": "繁體中文",
    "zh-Hans": "简体中文",
    "ja": "日本語",
    "ko": "한국어",
    "vi": "Tiếng Việt",
}

RAIL_PATTERNS = {
    "single_name_weight_warn_pct": r"Single-name weight cap:\s*([0-9]*\.?[0-9]+)%",
    "theme_concentration_warn_pct": r"Theme concentration cap:\s*([0-9]*\.?[0-9]+)%",
    "high_vol_bucket_warn_pct": r"High-volatility bucket cap:\s*([0-9]*\.?[0-9]+)%",
    "cash_floor_warn_pct": r"Cash floor:\s*([0-9]*\.?[0-9]+)%",
    "single_day_move_alert_pct": r"Single-day move alert:\s*[±+-]?([0-9]*\.?[0-9]+)%",
}

# §9.0 — `Base currency: <CCY>` line in SETTINGS.md picks the canonical currency
# every aggregate is denominated in. Default is USD when missing or unset.
BASE_CURRENCY_PATTERN = r"Base currency:\s*([A-Za-z]{3})"
DEFAULT_BASE_CURRENCY = "USD"


@dataclass
class SettingsProfile:
    raw_language: str
    locale: str
    display_name: str
    config_overrides: Dict[str, float]
    base_currency: str = DEFAULT_BASE_CURRENCY
    missing: bool = False


def _extract_settings_section_bullets(text: str, heading: str) -> List[str]:
    bullets: List[str] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        # Match both `## Language` and `Language:` heading formats.
        if line.startswith("## "):
            current = line[3:].strip().lower()
            in_section = current == heading.lower()
            continue
        stripped = line.strip()
        if stripped.lower() == heading.lower() + ":":
            in_section = True
            continue
        if not in_section:
            continue
        # A new plain heading (no leading `-`) that ends with `:` terminates the section.
        if stripped and not stripped.startswith("-") and stripped.endswith(":"):
            break
        if line.startswith("### "):
            break
        if line.lstrip().startswith("-"):
            bullets.append(line.split("-", 1)[1].strip())
    return bullets


def _normalize_language(raw_language: str) -> str:
    normalized = raw_language.strip().strip(LANGUAGE_QUOTE_CHARS).strip().lower()
    if normalized in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[normalized]
    return normalized or "en"


def parse_settings_profile(path: Path) -> SettingsProfile:
    if not path.exists():
        return SettingsProfile(
            raw_language="english",
            locale="en",
            display_name=DISPLAY_NAME_BY_LOCALE["en"],
            config_overrides={},
            base_currency=DEFAULT_BASE_CURRENCY,
            missing=True,
        )

    text = path.read_text(encoding="utf-8")
    bullets = _extract_settings_section_bullets(text, "Language")
    raw_language = bullets[0] if bullets else "english"
    locale = _normalize_language(raw_language)
    display_name = DISPLAY_NAME_BY_LOCALE.get(locale, raw_language.strip() or locale)

    config_overrides: Dict[str, float] = {}
    for key, pattern in RAIL_PATTERNS.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        try:
            config_overrides[key] = float(m.group(1))
        except ValueError:
            continue

    # Base currency: optional. Falls back to USD per §9.0 default.
    base_match = re.search(BASE_CURRENCY_PATTERN, text, re.IGNORECASE)
    base_currency = base_match.group(1).upper() if base_match else DEFAULT_BASE_CURRENCY

    return SettingsProfile(
        raw_language=raw_language,
        locale=locale,
        display_name=display_name,
        config_overrides=config_overrides,
        base_currency=base_currency,
        missing=False,
    )


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
LANGUAGE_QUOTE_CHARS = "\"'“”‘’「」『』〈〉《》"


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
# Metrics
# ----------------------------------------------------------------------------- #

@dataclass
class TickerAggregate:
    """Per-ticker rollup used by the holdings table and the popovers.

    Per spec §9.0 every aggregate (`market_value`, `pnl_amount`, `weighted_avg_cost_usd`,
    cash totals) is in **USD**. Native trade currency is preserved for popover display
    via the `*_native` fields and `trade_currency`.
    """
    ticker: str
    market: MarketType
    bucket: str                       # representative bucket (highest seniority)
    total_qty: float
    weighted_avg_cost: Optional[float]      # native trade currency (None if all lots have ? cost)
    total_cost_known: float                 # native: Σ(lot_cost × lot_qty) over known-cost lots
    earliest_date: Optional[str]            # for hold period
    lots: List[Lot] = field(default_factory=list)

    # Filled in after price merge — all USD unless suffixed _native
    latest_price: Optional[float] = None             # native trade currency (display in §10.3)
    move_pct: Optional[float] = None
    market_value: Optional[float] = None             # **USD** (post-FX)
    pnl_amount: Optional[float] = None               # **USD**
    pnl_pct: Optional[float] = None                  # ratio, currency-agnostic
    weighted_avg_cost_usd: Optional[float] = None    # USD-converted avg cost (popover footer)
    is_cash: bool = False
    trade_currency: str = "USD"                      # market → currency (US/crypto/FX → USD)
    fx_rate_used: Optional[float] = None             # 1 unit native = N USD; None when USD or n/a


@dataclass
class BookPacing:
    """§9.5 book-wide aggregates for the Holding period & pacing block."""
    avg_hold_years: Optional[float]
    oldest: Optional[Tuple[str, str, str]]    # (ticker, date, duration_label)
    newest: Optional[Tuple[str, str, str]]
    pct_held_over_1y: Optional[float]
    distribution_pct: Dict[str, float]        # buckets: <1m, 1-6m, 6-12m, 1-3y, 3y+


def _bucket_priority(name: str) -> int:
    order = {"long term": 0, "mid term": 1, "short term": 2, "cash holdings": 99}
    for k, v in order.items():
        if name.lower().startswith(k):
            return v
    return 50


def aggregate(lots: List[Lot]) -> Dict[str, TickerAggregate]:
    """One row per distinct ticker, picking the most senior bucket if a ticker spans multiple."""
    buckets: Dict[str, TickerAggregate] = {}
    for lot in lots:
        agg = buckets.get(lot.ticker)
        is_cash = lot.market == MarketType.CASH or _bucket_priority(lot.bucket) == 99
        if agg is None:
            agg = TickerAggregate(
                ticker=lot.ticker,
                market=lot.market,
                bucket=lot.bucket,
                total_qty=0.0,
                weighted_avg_cost=None,
                total_cost_known=0.0,
                earliest_date=None,
                is_cash=is_cash,
            )
            buckets[lot.ticker] = agg
        # Promote bucket if a more senior one shows up
        if _bucket_priority(lot.bucket) < _bucket_priority(agg.bucket):
            agg.bucket = lot.bucket

        agg.lots.append(lot)
        agg.total_qty += lot.quantity
        if lot.cost is not None:
            agg.total_cost_known += lot.cost * lot.quantity
        if lot.date:
            if agg.earliest_date is None or lot.date < agg.earliest_date:
                agg.earliest_date = lot.date

    # Compute weighted average cost over lots with known cost only
    for agg in buckets.values():
        known_qty = sum(l.quantity for l in agg.lots if l.cost is not None)
        if known_qty > 0:
            agg.weighted_avg_cost = agg.total_cost_known / known_qty
    return buckets


# §9.0 — every market type maps to a default trade currency. The agent can override
# per-ticker via the editorial context if a security is dual-listed.
MARKET_DEFAULT_CCY: Dict[MarketType, str] = {
    MarketType.US: "USD",
    MarketType.CRYPTO: "USD",
    MarketType.FX: "USD",
    MarketType.TW: "TWD",
    MarketType.TWO: "TWD",
    MarketType.JP: "JPY",
    MarketType.HK: "HKD",
    MarketType.LSE: "GBP",
    MarketType.UNKNOWN: "USD",
    MarketType.CASH: "USD",  # overridden per-line below
}

# USD stablecoin tickers held as `[cash]` are pegged at $1.00 USD per unit. When the
# report base currency is not USD, the cash-line conversion below applies the
# configured fx rate to translate the peg into base units.
CASH_STABLECOIN_USD: Dict[str, float] = {
    "USDC": 1.0, "USDT": 1.0, "DAI": 1.0, "BUSD": 1.0, "TUSD": 1.0, "USDP": 1.0,
}


def _fx_to_base(
    native_amount: Optional[float],
    currency: str,
    fx: Dict[str, float],
    base: str = DEFAULT_BASE_CURRENCY,
) -> Tuple[Optional[float], Optional[float]]:
    """Convert `native_amount` in `currency` to the configured base currency.

    `fx` is keyed `"<BASE>/<CCY>"` with the rate "1 unit of base = N units of CCY"
    (matches the SETTINGS.example.md format). Returns (base_amount, fx_rate_used).
    `fx_rate_used` is "1 unit of native = X units of base" (i.e. 1 / (base/ccy))
    so the caller can record what was applied.
    """
    if native_amount is None:
        return None, None
    if currency == base:
        return native_amount, 1.0
    rate_key = f"{base}/{currency}"
    pair_rate = fx.get(rate_key)
    if pair_rate in (None, 0):
        return None, None
    fx_native_to_base = 1.0 / pair_rate
    return native_amount * fx_native_to_base, fx_native_to_base


def merge_prices(
    aggs: Dict[str, TickerAggregate],
    prices: Dict[str, Any],
    fx: Optional[Dict[str, float]] = None,
    base: str = DEFAULT_BASE_CURRENCY,
) -> None:
    """Merge prices and apply §9.0 base-currency canonicalization.

    `fx` is the agent-supplied base-quoted rates. If a non-base currency is held
    but no rate is configured, the affected aggregate is marked `n/a` (per §9.6) —
    the agent must walk §9.0 fetch-rate flow before regenerating the report. We
    never assume parity.

    `base` defaults to USD for backwards compatibility; pass a different ISO 4217
    code (e.g. "TWD") to denominate the report in another currency.
    """
    fx = fx or {}
    base = base.upper()
    for ticker, agg in aggs.items():
        if agg.is_cash:
            ccy = ticker.upper()
            agg.trade_currency = ccy
            # USD stablecoins are pegged at $1; convert to base via the fx dict.
            if ccy in CASH_STABLECOIN_USD:
                usd_value = agg.total_qty * CASH_STABLECOIN_USD[ccy]
                base_value, base_rate = _fx_to_base(usd_value, "USD", fx, base)
                agg.market_value = base_value           # None if base != USD and fx missing
                agg.fx_rate_used = base_rate
            elif ccy == base:
                agg.market_value = agg.total_qty
                agg.fx_rate_used = 1.0
            else:
                base_value, rate = _fx_to_base(agg.total_qty, ccy, fx, base)
                agg.market_value = base_value           # None when fx missing
                agg.fx_rate_used = rate
            continue

        pr = prices.get(ticker, {}) or {}
        agg.latest_price = pr.get("latest_price")      # native trade currency, displayed as-is
        agg.move_pct = pr.get("move_pct")
        # Source-currency override from prices.json wins over market-default mapping.
        agg.trade_currency = (pr.get("currency") or MARKET_DEFAULT_CCY.get(agg.market, "USD")).upper()

        if agg.latest_price is not None:
            native_mv = agg.latest_price * agg.total_qty
            base_mv, rate = _fx_to_base(native_mv, agg.trade_currency, fx, base)
            agg.market_value = base_mv                  # base currency; None if fx missing
            agg.fx_rate_used = rate
            if agg.weighted_avg_cost not in (None, 0):
                # weighted_avg_cost is in the lot's acquisition trade currency. We use the
                # *current* fx rate as the simplest spec-compliant approximation; the agent
                # may inject acquisition-date FX via a richer context payload in the future.
                native_cost_basis = agg.weighted_avg_cost * agg.total_qty
                base_cost_basis, _ = _fx_to_base(native_cost_basis, agg.trade_currency, fx, base)
                if base_cost_basis is not None and base_mv is not None:
                    agg.pnl_amount = base_mv - base_cost_basis
                    agg.pnl_pct = (agg.pnl_amount / base_cost_basis * 100.0) if base_cost_basis else None
                    agg.weighted_avg_cost_usd = (
                        base_cost_basis / agg.total_qty if agg.total_qty else None
                    )


def hold_period_label(earliest_date: Optional[str], today: _dt.date) -> str:
    if not earliest_date:
        return "n/a"
    try:
        d0 = _dt.date.fromisoformat(earliest_date)
    except ValueError:
        return "n/a"
    days = (today - d0).days
    if days < 0:
        return "n/a"
    if days < 30:
        return f"{days}d"
    months = days // 30
    if months < 12:
        return f"{months}m"
    years = months // 12
    rem = months % 12
    return f"{years}y {rem}m" if rem else f"{years}y"


def book_pacing(aggs: Dict[str, TickerAggregate], today: _dt.date) -> BookPacing:
    """§9.5 — risk-asset only, cost-weighted in USD basis (per §9.0).

    The cost-weighted average hold MUST use USD-converted cost, not native cost.
    Mixing native costs (e.g. NT$345,000 with $4,500) means a single TW lot
    appears 32× heavier than an equivalently-sized US lot just because of the
    currency unit, dragging the weighted average toward whatever lot happens to
    have the largest native-currency notional.
    """
    buckets = {"<1m": 0.0, "1-6m": 0.0, "6-12m": 0.0, "1-3y": 0.0, "3y+": 0.0}
    risk_value = 0.0
    over_1y_value = 0.0
    weighted_days = 0.0
    cost_total = 0.0
    oldest: Optional[Tuple[str, str, int]] = None
    newest: Optional[Tuple[str, str, int]] = None

    for agg in aggs.values():
        if agg.is_cash or agg.market_value in (None, 0):
            continue
        risk_value += agg.market_value
        # `fx_rate_used` is "1 unit native = X USD"; None when fx is missing for a
        # non-USD position. In that case we cannot compare costs across the book,
        # so the lot is excluded from the cost-weighted aggregate (oldest/newest/
        # bucket distribution still use USD market value, which the merge step has
        # already filtered to USD-resolvable holdings via market_value).
        fx_rate = agg.fx_rate_used
        for lot in agg.lots:
            if not lot.date or lot.cost is None:
                continue
            try:
                d0 = _dt.date.fromisoformat(lot.date)
            except ValueError:
                continue
            days = (today - d0).days
            if fx_rate is not None:
                cost_usd = lot.cost * lot.quantity * fx_rate
                cost_total += cost_usd
                weighted_days += cost_usd * days
            if days >= 365:
                over_1y_value += (agg.market_value or 0) * (lot.quantity / agg.total_qty)
            if oldest is None or days > oldest[2]:
                oldest = (agg.ticker, lot.date, days)
            if newest is None or days < newest[2]:
                newest = (agg.ticker, lot.date, days)

            # Distribution by hold period (value-weighted using lot share of agg market value)
            value_share = (agg.market_value or 0) * (lot.quantity / agg.total_qty)
            if days < 30:
                buckets["<1m"] += value_share
            elif days < 180:
                buckets["1-6m"] += value_share
            elif days < 365:
                buckets["6-12m"] += value_share
            elif days < 365 * 3:
                buckets["1-3y"] += value_share
            else:
                buckets["3y+"] += value_share

    if risk_value > 0:
        dist_pct = {k: round(v / risk_value * 100.0, 1) for k, v in buckets.items()}
    else:
        dist_pct = {k: 0.0 for k in buckets}

    avg_years = (weighted_days / cost_total / 365.0) if cost_total > 0 else None
    pct_over_1y = round(over_1y_value / risk_value * 100.0, 1) if risk_value > 0 else None

    def _wrap(node: Optional[Tuple[str, str, int]]) -> Optional[Tuple[str, str, str]]:
        if node is None:
            return None
        ticker, date, days = node
        return (ticker, date, _days_label(days))

    return BookPacing(
        avg_hold_years=round(avg_years, 1) if avg_years is not None else None,
        oldest=_wrap(oldest),
        newest=_wrap(newest),
        pct_held_over_1y=pct_over_1y,
        distribution_pct=dist_pct,
    )


def _days_label(days: int) -> str:
    if days < 30:
        return f"{days}d"
    months = days // 30
    if months < 12:
        return f"{months}m"
    years = months // 12
    rem = months % 12
    return f"{years}y {rem}m" if rem else f"{years}y"

def _bucket_key(bucket: str) -> str:
    bucket_lc = bucket.lower()
    if bucket_lc.startswith("long term"):
        return "long"
    if bucket_lc.startswith("mid term"):
        return "mid"
    if bucket_lc.startswith("short term"):
        return "short"
    if bucket_lc.startswith("cash holdings"):
        return "cash"
    return bucket_lc


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
# §11 special checks — runs against the merged data
# ----------------------------------------------------------------------------- #

@dataclass
class CheckResult:
    label: str
    triggered: bool
    detail: str


def special_checks(
    aggs: Dict[str, TickerAggregate],
    total_assets: float,
    config: Dict[str, float],
) -> List[CheckResult]:
    """Returns one CheckResult per §11 item — both passes and triggers."""
    if total_assets <= 0:
        return []
    results: List[CheckResult] = []
    # 1. Single asset > 15%
    for agg in aggs.values():
        if agg.is_cash or agg.market_value is None:
            continue
        weight = agg.market_value / total_assets * 100.0
        if weight > config["single_name_weight_warn_pct"]:
            results.append(CheckResult(
                "Concentration: single asset",
                True,
                f"{agg.ticker} 權重 {weight:.1f}% > {config['single_name_weight_warn_pct']:.0f}%",
            ))
            break
    else:
        results.append(CheckResult("Concentration: single asset", False, "通過 — 無單一標的超過上限"))

    # 6. Recent buying spree — 3+ adds in last 30 days per ticker
    today = _dt.date.today()
    spree: List[str] = []
    for agg in aggs.values():
        recent = [l for l in agg.lots if l.date and (today - _dt.date.fromisoformat(l.date)).days <= 30]
        if len(recent) >= 3:
            spree.append(agg.ticker)
    results.append(CheckResult(
        "Recent buying spree (3+ adds in 30 days)",
        bool(spree),
        ", ".join(spree) if spree else "通過 — 無近期密集加碼",
    ))

    # 8. Bucket misclassification — Short Term lot held > 12 months
    misclassified: List[Tuple[str, str]] = []
    for agg in aggs.values():
        for lot in agg.lots:
            if "short" in lot.bucket.lower() and lot.date:
                try:
                    days = (today - _dt.date.fromisoformat(lot.date)).days
                except ValueError:
                    continue
                if days > 365:
                    misclassified.append((agg.ticker, lot.date))
    results.append(CheckResult(
        "Bucket misclassification (Short Term > 12m)",
        bool(misclassified),
        ", ".join(f"{t} ({d})" for t, d in misclassified) if misclassified else "通過 — 短線桶內無持有 > 12 月之批次",
    ))

    # 9. Averaging up — most recent lot > 1.1× older weighted avg
    averaging_up: List[str] = []
    for agg in aggs.values():
        if len(agg.lots) < 2 or agg.weighted_avg_cost is None:
            continue
        sorted_lots = sorted([l for l in agg.lots if l.date and l.cost is not None], key=lambda l: l.date or "")
        if len(sorted_lots) < 2:
            continue
        older = sorted_lots[:-1]
        latest = sorted_lots[-1]
        older_qty = sum(l.quantity for l in older)
        if older_qty == 0:
            continue
        older_avg = sum(l.cost * l.quantity for l in older) / older_qty
        if latest.cost > older_avg * 1.1:
            averaging_up.append(f"{agg.ticker} (latest {latest.cost:.2f} vs older avg {older_avg:.2f})")
    results.append(CheckResult(
        "Averaging up (latest lot > 1.1× older avg)",
        bool(averaging_up),
        "; ".join(averaging_up) if averaging_up else "通過 — 無加碼追高情形",
    ))

    # 10. Open cost-basis or date gaps
    gaps = [agg.ticker for agg in aggs.values()
            if any(l.cost is None or l.date is None for l in agg.lots)]
    results.append(CheckResult(
        "Open cost-basis / date gaps",
        bool(gaps),
        ", ".join(sorted(set(gaps))) if gaps else "通過 — 所有批次皆有完整成本與日期",
    ))
    return results


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

def render_masthead(context: Dict[str, Any]) -> str:
    lang = _esc(context.get("language", _ui("meta.language_name")))
    title = _esc(context.get("title", _ui("masthead.title")))
    subtitle = _esc(context.get("subtitle", ""))
    fx_str = " · ".join(f"{k} {v}" for k, v in (context.get("fx") or {}).items()) or _ui("common.na")
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


def render_alerts(context: Dict[str, Any]) -> str:
    alerts = context.get("alerts") or []
    if not alerts:
        return ""
    items = "\n      ".join(f"<li>{_esc(a)}</li>" for a in alerts)
    return f"""\
  <section class="callout">
    <div class="ctitle"><span class="badge">{_esc(_ui("alerts.badge"))}</span>{_esc(_ui("alerts.title"))}</div>
    <ul>
      {items}
    </ul>
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
    pnl_html = (f'<div class="delta {"pos" if pnl >= 0 else "neg"}">{"+" if pnl >= 0 else "−"}${abs(pnl):,.0f}</div>'
                if pnl is not None else f'<div class="delta">{_ui("common.na")}</div>')
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("dashboard.title"))}</h2>
      <span class="sub">{_esc(_ui("dashboard.subtitle", base=ACTIVE_BASE_CURRENCY))}</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="k">{_esc(_ui("dashboard.total_assets"))}</div><div class="v">${total_assets:,.0f}</div><div class="delta">{_esc(_ui("dashboard.total_assets_note"))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("dashboard.invested"))}</div><div class="v">${invested:,.0f}</div><div class="delta">{_esc(_ui("dashboard.invested_note", pct=invested_pct))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("dashboard.cash"))}</div><div class="v">${cash:,.0f}</div><div class="delta">{_esc(_ui("dashboard.cash_note", pct=cash_pct))}</div></div>
      <div class="kpi"><div class="k">{_esc(_ui("dashboard.known_pnl"))}</div><div class="v">{_fmt_money(pnl)}</div><div class="delta">{_esc(_ui("dashboard.pnl_note"))}</div>{pnl_html}</div>
    </div>

    <div style="margin-top:22px">
      <div class="cash-bar" aria-label="{_esc(_ui("dashboard.cash_bar_label"))}">
        <span class="seg risk" style="width:{invested_pct:.1f}%"></span>
        <span class="seg cash" style="width:{cash_pct:.1f}%"></span>
      </div>
      <div class="cash-legend">
        <span><i style="background:var(--ink)"></i>{_esc(_ui("dashboard.risk_legend", pct=invested_pct, value=invested))}</span>
        <span><i style="background:var(--accent-warm)"></i>{_esc(_ui("dashboard.cash_legend", pct=cash_pct, value=cash))}</span>
      </div>
    </div>
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
    if value >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value/1_000:.0f}k"
    return f"${value:.0f}"


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
        MarketType.US: (_ui("category.stock_etf"), ""),
        MarketType.CRYPTO: (_ui("category.crypto"), "warn"),
        MarketType.TW: (_ui("category.tw"), ""),
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
    # §9.0 — latest price displays in native trade currency; footer aggregates in USD.
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
                # original trade currency mental model). USD aggregates live in the footer.
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
            f'<div class="bar-value {txt_cls}">{sign}${abs(a.pnl_amount):,.0f}</div></div>'
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

    See the CONTEXT FILE SHAPE section at the top of this module for the markup
    contract. If the field is missing, the section renders a placeholder so the
    omission is visible — never a guess.
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
            url = _esc(n.get("url", "#"))
            rows.append(f"""\
      <div class="item">
        <div class="meta"><span class="tk">{_esc(n.get('ticker', _ui("common.dash")))}</span>{_esc(n.get('date', ''))}</div>
        <div class="body">
          <div class="head">{_esc(n.get('headline', ''))}</div>
          <div class="src">{_esc(_ui("news.source_prefix"))}<a href="{url}">{_esc(n.get('source', ''))}</a></div>
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


@dataclass
class RiskHeatItem:
    ticker: str
    score: int
    band_class: str
    weight_pct: float
    move_pct: Optional[float]
    reasons: List[str]


def build_risk_heat_items(
    aggs: Dict[str, TickerAggregate],
    prices: Dict[str, Any],
    total_assets: float,
    config: Dict[str, float],
) -> List[RiskHeatItem]:
    items: List[RiskHeatItem] = []
    single_name_cap = config.get("single_name_weight_warn_pct", DEFAULTS["single_name_weight_warn_pct"])
    move_alert = config.get("single_day_move_alert_pct", DEFAULTS["single_day_move_alert_pct"])

    for agg in aggs.values():
        if agg.is_cash or agg.market_value in (None, 0):
            continue
        weight_pct = (agg.market_value / total_assets * 100.0) if total_assets else 0.0
        pr = prices.get(agg.ticker, {}) or {}
        reasons: List[str] = []
        score = 0

        if agg.market == MarketType.CRYPTO:
            score += 3
            reasons.append(_ui("risk.factor_crypto"))

        bucket_key = _bucket_key(agg.bucket)
        if bucket_key == "short":
            score += 2
            reasons.append(_ui("risk.factor_short_bucket"))
        elif bucket_key == "mid":
            score += 1
            reasons.append(_ui("risk.factor_mid_bucket"))

        if weight_pct >= single_name_cap * 1.5:
            score += 3
            reasons.append(_ui("risk.factor_concentration_breach", threshold=single_name_cap))
        elif weight_pct >= single_name_cap:
            score += 2
            reasons.append(_ui("risk.factor_concentration_warn", threshold=single_name_cap))
        elif weight_pct >= single_name_cap * 0.5:
            score += 1
            reasons.append(_ui("risk.factor_concentration_watch", threshold=single_name_cap * 0.5))

        if agg.move_pct is not None:
            abs_move = abs(agg.move_pct)
            if abs_move >= move_alert * 1.5:
                score += 2
                reasons.append(_ui("risk.factor_move_breach", threshold=move_alert))
            elif abs_move >= move_alert:
                score += 1
                reasons.append(_ui("risk.factor_move_warn", threshold=move_alert))

        if agg.latest_price is None or pr.get("price_source") == "n/a":
            score += 2
            reasons.append(_ui("risk.factor_missing"))
        else:
            freshness = pr.get("price_freshness", "n/a")
            if freshness == "delayed":
                score += 1
                reasons.append(_ui("risk.factor_delayed"))
            elif freshness in {"stale_after_exhaustive_search", "n/a"}:
                score += 2
                reasons.append(_ui("risk.factor_stale"))

        score = min(score, 10)
        if not reasons:
            reasons.append(_ui("risk.factor_core"))
        band_class = "r-high" if score >= 6 else "r-mid" if score >= 3 else "r-low"
        items.append(
            RiskHeatItem(
                ticker=agg.ticker,
                score=score,
                band_class=band_class,
                weight_pct=weight_pct,
                move_pct=agg.move_pct,
                reasons=reasons,
            )
        )

    items.sort(key=lambda item: (-item.score, -item.weight_pct, item.ticker))
    return items[:10]


def render_high_risk_opp(
    aggs: Dict[str, TickerAggregate],
    prices: Dict[str, Any],
    total_assets: float,
    context: Dict[str, Any],
    config: Dict[str, float],
) -> str:
    risk_cells = []
    for item in build_risk_heat_items(aggs, prices, total_assets, config):
        move_str = f"{item.move_pct:+.1f}%" if item.move_pct is not None else _ui("common.na")
        reason_summary = " · ".join(item.reasons[:3])
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


def render_adjustments(context: Dict[str, Any]) -> str:
    adjs = context.get("adjustments") or []
    if not adjs:
        return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("adjustments.title"))}</h2>
      <span class="sub">{_esc(_ui("adjustments.subtitle"))}</span>
    </div>
    <div class="prose"><p>{_esc(_ui("adjustments.placeholder"))}</p></div>
  </section>"""
    rows = []
    for a in adjs:
        rows.append(f"""\
          <tr>
            <td><span class="sym-trigger" tabindex="0" role="button">{_esc(a.get('ticker', _ui("common.dash")))}</span></td>
            <td class="num">{a.get('current_pct', 0):.1f}%</td>
            <td><span class="adj-action {_esc(a.get('action', 'hold'))}">{_esc(a.get('action_label', ''))}</span></td>
            <td class="why">{_esc(a.get('why', ''))}</td>
            <td class="trig">{_esc(a.get('trigger', ''))}</td>
          </tr>""")
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
  </section>"""


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
            rows.append(f'<li><span class="lbl {label_class}">{_esc(label_text)}</span><span>{_esc(item)}</span></li>')
    body = "\n".join(rows) or f'<li><span class="lbl">{_esc(_ui("common.dash"))}</span><span>{_esc(_ui("actions.placeholder"))}</span></li>'
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("actions.title"))}</h2>
      <span class="sub">{_esc(_ui("actions.subtitle"))}</span>
    </div>
    <ul class="actions">
{body}
    </ul>
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
            notes.append(_esc(pr.get("yfinance_failure_reason"))[:60])
        rows.append(f"""\
          <tr>
            <td>{_esc(ticker)}</td>
            <td>{_esc(pr.get('price_source', _ui("common.na")))}</td>
            <td>{_esc(market_state_label)}</td>
            <td class="num">{_esc(pr.get('price_as_of') or _ui("common.na"))}</td>
            <td><span class="freshness {fresh_cls}">{_esc(fresh_label)}</span></td>
            <td>{_esc('; '.join(notes)) or _esc(_ui("common.dash"))}</td>
          </tr>""")
    gaps = context.get("data_gaps") or []
    gap_html = "".join(f'<li><b>{_esc(g.get("summary", ""))}:</b> {_esc(g.get("detail", ""))}</li>' for g in gaps) \
        or f'<li>{_esc(_ui("sources.no_gaps"))}</li>'
    spec_note = context.get("spec_update_note")
    spec_html = (f'<div class="bucket-note" style="margin-top:18px"><b>{_esc(_ui("sources.spec_note"))}</b>{_esc(spec_note)}</div>'
                 if spec_note else "")
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>{_esc(_ui("sources.title"))}</h2>
      <span class="sub">{_esc(_ui("sources.subtitle"))}</span>
    </div>
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
    aggs: Dict[str, TickerAggregate],
    prices: Dict[str, Any],
    context: Dict[str, Any],
    css: str,
    config: Dict[str, float],
    settings: SettingsProfile,
) -> str:
    today = _dt.date.today()

    # Activate the base currency *before* any render_ function runs so all
    # downstream `_fmt_money` / `_fmt_signed*` / popover-footer prefixes use the
    # configured base (default USD).
    _set_active_base_currency(settings.base_currency)

    # Totals (base-currency basis — merge_prices has already FX-converted)
    total_assets = sum(a.market_value or 0 for a in aggs.values())
    invested = sum(a.market_value or 0 for a in aggs.values() if not a.is_cash)
    cash = sum(a.market_value or 0 for a in aggs.values() if a.is_cash)
    pnl = sum(a.pnl_amount for a in aggs.values() if a.pnl_amount is not None) or None

    pacing = book_pacing(aggs, today)
    _ = special_checks(aggs, total_assets, config)  # results currently surfaced via context["alerts"]

    # Render sections (§10 order)
    sections = [
        render_masthead(context),
        render_alerts(context),
        render_today_summary(context),                                     # §10.1 #1
        render_dashboard(aggs, total_assets, invested, cash, pnl),         # §10.1 #2
        render_allocation_and_weight(aggs, total_assets, today),           # §10.1 allocation + weight
        render_holdings_table(aggs, total_assets, prices, today, context), # §10.1 #3
        render_pnl_ranking(aggs),                                          # §10.4 chart
        render_holding_period(pacing),                                     # §10.1 #4
        render_theme_sector(context),                                      # §10.1 #5
        render_news(context),                                              # §10.1 #6
        render_events(context),                                            # §10.1 #7
        render_high_risk_opp(aggs, prices, total_assets, context, config), # §10.1 #8
        render_adjustments(context),                                       # §10.1 #9
        render_actions(context),                                           # §10.1 #10
        render_sources(prices, context),                                   # §10.1 #11
    ]

    return f"""<!doctype html>
<html lang="{_esc(settings.locale)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(context.get('title', _ui('masthead.title')))}</title>
<style>{css}</style>
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
    p.add_argument("--holdings", default="HOLDINGS.md", type=Path)
    p.add_argument("--settings", default="SETTINGS.md", type=Path)
    p.add_argument("--prices", required=True, type=Path,
                   help="JSON output from scripts/fetch_prices.py")
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
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _cli(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if not args.holdings.exists():
        print(f"ERROR: {args.holdings} not found", file=sys.stderr); return 2
    if not args.prices.exists():
        print(f"ERROR: {args.prices} not found (run fetch_prices.py first)", file=sys.stderr); return 3

    lots = parse_holdings(args.holdings)
    aggs = aggregate(lots)
    prices = json.loads(args.prices.read_text(encoding="utf-8"))

    # §9.0 — load editorial context BEFORE merging prices so we can apply the supplied
    # USD FX rates to non-USD positions during the merge.
    context: Dict[str, Any] = {}
    if args.context and args.context.exists():
        context = json.loads(args.context.read_text(encoding="utf-8"))
    elif args.context:
        logging.warning("Context file %s not found; rendering with placeholders.", args.context)

    settings = parse_settings_profile(args.settings)
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

    fx = context.get("fx") or {}
    base_ccy = settings.base_currency
    merge_prices(aggs, prices, fx=fx, base=base_ccy)

    # §9.0 audit — warn loudly for any non-base currency in the book that lacks
    # an FX rate. Stablecoins pegged 1:1 to USD still need fx[base/USD] when
    # base != USD; the audit catches that case too.
    needed_ccys = sorted({a.trade_currency for a in aggs.values() if a.trade_currency != base_ccy})
    missing_fx: List[str] = []
    for c in needed_ccys:
        if f"{base_ccy}/{c}" in fx:
            continue
        # USD stablecoins are usable as long as we can convert USD → base (or base IS USD).
        if c in CASH_STABLECOIN_USD and (base_ccy == "USD" or f"{base_ccy}/USD" in fx):
            continue
        missing_fx.append(c)
    if missing_fx:
        logging.warning(
            "Non-%s currency in book without FX rate: %s. "
            "Affected aggregates will render as `n/a` per spec §9.0. "
            "Add `\"fx\": {\"%s/%s\": <rate>, ...}` to the context JSON.",
            base_ccy, ", ".join(missing_fx), base_ccy, missing_fx[0],
        )

    css = load_canonical_css(args.sample)
    config = {**DEFAULTS, **settings.config_overrides}
    html_doc = render_html(aggs, prices, context, css, config, settings)

    if args.output is None:
        ts = _dt.datetime.now().strftime("%Y-%m-%d_%H%M")
        args.output = Path("reports") / f"{ts}_portfolio_report.html"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {args.output} ({len(html_doc):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
