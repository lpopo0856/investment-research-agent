#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
portfolio_snapshot.py — pure-compute pipeline stage for the portfolio report.

This module owns every deterministic numeric / structural computation that
turns `transactions.db` + `prices.json` + `SETTINGS.md` into the report-ready
data the HTML renderer consumes:

  - Per-ticker aggregation (`aggregate`, `merge_prices`, `_fx_to_base`)
  - Hold period & pacing (`book_pacing`, `hold_period_label`)
  - High-risk heatmap rubric (`build_risk_heat_items`)
  - §11 special checks (`special_checks`)
  - SETTINGS.md parsing (`parse_settings_profile`)
  - Snapshot serializer (`compute_snapshot`, `serialize_snapshot`,
    `deserialize_snapshot`)

`generate_report.py` imports these names so existing call sites continue to
work, but the rendering script no longer owns the math — pipeline scripts can
materialize the snapshot once (via `python scripts/transactions.py snapshot`)
and the renderer simply projects it onto HTML.

Spec references: `/docs/portfolio_report_agent_guidelines/04-computations-to-static-snapshot.md`
§9 (Computations & missing-value glyphs), §10.4.1 (high-risk heatmap rubric),
§10.5 (book-wide pacing aggregates), §11 (per-run special checks).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Re-use the lot shape + market routing from the price-fetch module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_prices import Lot, MarketType                 # noqa: E402


# ----------------------------------------------------------------------------- #
# Constants — mirror SETTINGS.example.md sizing rails so warnings fire by
# default. Overridden per-run by SETTINGS.md (see `parse_settings_profile`).
# ----------------------------------------------------------------------------- #

DEFAULTS: Dict[str, float] = {
    "single_name_weight_warn_pct": 15.0,    # §11 special check #1
    "theme_concentration_warn_pct": 25.0,   # §11 #2
    "high_vol_bucket_warn_pct": 30.0,       # §11 #3
    "cash_floor_warn_pct": 10.0,            # §15.6 cash floor
    "single_day_move_alert_pct": 8.0,       # §10.6 alert #4
    "earnings_within_days": 7,              # §10.6 alert #5
    "earnings_weight_pct": 5.0,             # §10.6 alert #5
    "above_target_pct": 20.0,               # §10.6 alert #7
}


# §9.0 — `Base currency: <CCY>` line in SETTINGS.md picks the canonical
# currency every aggregate is denominated in. Default is USD when missing.
DEFAULT_BASE_CURRENCY = "USD"
BASE_CURRENCY_PATTERN = r"Base currency:\s*([A-Za-z]{3})"
ACCOUNT_DESCRIPTION_PATTERN = (
    r"^\s*-\s*(?:Account\s+description|Description)\s*:\s*(.+?)\s*$"
)

LANGUAGE_QUOTE_CHARS = "\"'“”‘’「」『』〈〉《》"

LANGUAGE_ALIASES: Dict[str, str] = {
    # English
    "en": "en", "eng": "en", "english": "en",

    # Chinese
    "zh": "zh", "chinese": "zh", "中文": "zh",
    "zh-hant": "zh-Hant", "zh-tw": "zh-Hant", "zh-hk": "zh-Hant",
    "traditional chinese": "zh-Hant",
    "traditional chinese (taiwan)": "zh-Hant",
    "繁體中文": "zh-Hant", "繁体中文": "zh-Hant",
    "zh-hans": "zh-Hans", "zh-cn": "zh-Hans", "zh-sg": "zh-Hans",
    "simplified chinese": "zh-Hans",
    "簡體中文": "zh-Hans", "简体中文": "zh-Hans",

    # Japanese
    "ja": "ja", "jp": "ja", "japanese": "ja", "日本語": "ja", "nihongo": "ja",

    # Korean
    "ko": "ko", "kr": "ko", "korean": "ko", "한국어": "ko", "hangul": "ko",

    # Vietnamese
    "vi": "vi", "vietnamese": "vi", "tiếng việt": "vi", "tieng viet": "vi",

    # French
    "fr": "fr", "french": "fr", "français": "fr", "francais": "fr",
    "fr-ca": "fr-CA", "canadian french": "fr-CA",
    "fr-fr": "fr-FR",

    # German
    "de": "de", "german": "de", "deutsch": "de",
    "de-at": "de-AT", "de-ch": "de-CH",

    # Spanish
    "es": "es", "spanish": "es", "español": "es", "espanol": "es",
    "castellano": "es",
    "es-mx": "es-MX", "mexican spanish": "es-MX",
    "es-419": "es-419", "latin american spanish": "es-419",

    # Portuguese
    "pt": "pt", "portuguese": "pt", "português": "pt", "portugues": "pt",
    "pt-br": "pt-BR", "brazilian portuguese": "pt-BR",
    "português brasileiro": "pt-BR", "portugues brasileiro": "pt-BR",
    "pt-pt": "pt-PT", "european portuguese": "pt-PT",

    # Italian
    "it": "it", "italian": "it", "italiano": "it",

    # Dutch
    "nl": "nl", "dutch": "nl", "nederlands": "nl",

    # Russian
    "ru": "ru", "russian": "ru", "русский": "ru",

    # Arabic
    "ar": "ar", "arabic": "ar", "العربية": "ar",

    # Hebrew
    "he": "he", "iw": "he", "hebrew": "he", "עברית": "he",

    # Persian / Farsi
    "fa": "fa", "persian": "fa", "farsi": "fa", "فارسی": "fa",

    # Urdu
    "ur": "ur", "urdu": "ur", "اردو": "ur",

    # Hindi
    "hi": "hi", "hindi": "hi", "हिन्दी": "hi",

    # Bengali
    "bn": "bn", "bengali": "bn", "bangla": "bn",

    # Thai
    "th": "th", "thai": "th", "ไทย": "th",

    # Indonesian / Malay
    "id": "id", "indonesian": "id", "bahasa indonesia": "id",
    "ms": "ms", "malay": "ms", "bahasa melayu": "ms",

    # Filipino / Tagalog
    "tl": "tl", "tagalog": "tl",
    "fil": "fil", "filipino": "fil",

    # Turkish
    "tr": "tr", "turkish": "tr", "türkçe": "tr", "turkce": "tr",

    # Polish, Czech, Hungarian, Romanian, Ukrainian, Greek, Bulgarian
    "pl": "pl", "polish": "pl", "polski": "pl",
    "cs": "cs", "czech": "cs", "čeština": "cs", "cestina": "cs",
    "sk": "sk", "slovak": "sk", "slovenčina": "sk",
    "hu": "hu", "hungarian": "hu", "magyar": "hu",
    "ro": "ro", "romanian": "ro", "română": "ro", "romana": "ro",
    "uk": "uk", "ukrainian": "uk", "українська": "uk",
    "el": "el", "greek": "el", "ελληνικά": "el",
    "bg": "bg", "bulgarian": "bg", "български": "bg",
    "hr": "hr", "croatian": "hr", "hrvatski": "hr",
    "sr": "sr", "serbian": "sr", "српски": "sr",

    # Nordic
    "sv": "sv", "swedish": "sv", "svenska": "sv",
    "no": "no", "norwegian": "no", "norsk": "no",
    "nb": "nb", "nn": "nn",
    "da": "da", "danish": "da", "dansk": "da",
    "fi": "fi", "finnish": "fi", "suomi": "fi",
    "is": "is", "icelandic": "is", "íslenska": "is",
}

DISPLAY_NAME_BY_LOCALE: Dict[str, str] = {
    "en": "English",
    "zh-Hant": "繁體中文",
    "zh-Hans": "简体中文",
    "ja": "日本語",
    "ko": "한국어",
    "vi": "Tiếng Việt",
}

# Locales whose chrome dictionaries (`scripts/i18n/report_ui.<locale>.json`)
# ship with the repo. For any other locale the executing agent must translate
# `report_ui.en.json` into `$REPORT_RUN_DIR/report_ui.<locale>.json` and pass
# it to `generate_report.py --ui-dict` (or merge into `context["ui_dictionary"]`)
# — the renderer hard-fails otherwise. See
# `docs/portfolio_report_agent_guidelines/02-inputs-to-self-containment.md` §5.1.
BUILTIN_UI_LOCALES: Tuple[str, ...] = ("en", "zh-Hant", "zh-Hans")

RAIL_PATTERNS: Dict[str, str] = {
    "single_name_weight_warn_pct": r"Single-name weight cap:\s*([0-9]*\.?[0-9]+)%",
    "theme_concentration_warn_pct": r"Theme concentration cap:\s*([0-9]*\.?[0-9]+)%",
    "high_vol_bucket_warn_pct": r"High-volatility bucket cap:\s*([0-9]*\.?[0-9]+)%",
    "cash_floor_warn_pct": r"Cash floor:\s*([0-9]*\.?[0-9]+)%",
    "single_day_move_alert_pct": r"Single-day move alert:\s*[±+-]?([0-9]*\.?[0-9]+)%",
}


# §9.0 — every market type maps to a default trade currency. The agent can
# override per-ticker via the editorial context if a security is dual-listed.
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
    MarketType.CASH: "USD",  # overridden per-line in merge_prices
}

# USD stablecoin tickers held as `[cash]` are pegged at $1.00 USD per unit.
# When the report base currency is not USD, the cash-line conversion below
# applies the auto-fetched fx rate to translate the peg into base units.
CASH_STABLECOIN_USD: Dict[str, float] = {
    "USDC": 1.0, "USDT": 1.0, "DAI": 1.0, "BUSD": 1.0, "TUSD": 1.0, "USDP": 1.0,
}


# ----------------------------------------------------------------------------- #
# SETTINGS.md parsing
# ----------------------------------------------------------------------------- #

@dataclass
class SettingsProfile:
    raw_language: str
    locale: str
    display_name: str
    config_overrides: Dict[str, float]
    base_currency: str = DEFAULT_BASE_CURRENCY
    missing: bool = False
    account_description: str = ""


def _extract_settings_section_bullets(text: str, heading: str) -> List[str]:
    bullets: List[str] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
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
        if stripped and not stripped.startswith("-") and stripped.endswith(":"):
            break
        if line.startswith("### "):
            break
        if line.lstrip().startswith("-"):
            bullets.append(line.split("-", 1)[1].strip())
    return bullets


def _extract_account_description(text: str) -> str:
    in_description_section = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            current = stripped[3:].strip().lower()
            in_description_section = current.startswith("account description")
            continue
        if not in_description_section:
            continue
        match = re.match(ACCOUNT_DESCRIPTION_PATTERN, raw_line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


_BCP47_RE = re.compile(
    r"^([A-Za-z]{2,3})"            # primary language subtag (ISO 639-1/2/3)
    r"(?:-([A-Za-z]{4}))?"         # optional script subtag (ISO 15924)
    r"(?:-([A-Za-z]{2}|\d{3}))?$"  # optional region subtag (ISO 3166-1 alpha-2 or UN M.49)
)


def _normalize_bcp47(tag: str) -> Optional[str]:
    """Recognize and case-normalize a basic BCP-47 language tag.

    Accepts shapes like `fr`, `pt-BR`, `zh-Hant`, `zh-Hant-TW`, `es-419`.
    Returns the canonical-cased tag (lang lowercase, script TitleCase,
    region UPPERCASE) or None if the input doesn't match.
    """
    m = _BCP47_RE.match(tag)
    if not m:
        return None
    lang, script, region = m.groups()
    parts = [lang.lower()]
    if script:
        parts.append(script.title())
    if region:
        parts.append(region.upper())
    return "-".join(parts)


def _normalize_language(raw_language: str) -> str:
    """Resolve a SETTINGS `Language:` value to a BCP-47 locale tag.

    Resolution order:
      1. Curated alias table (natural-language names like `français`,
         `german`, `ไทย`, plus common code variants like `zh-tw`).
      2. BCP-47 syntax passthrough — any well-formed `lang[-Script][-REGION]`
         tag is accepted and case-normalized, so unlisted locales like
         `mk`, `ka`, `sw`, `et`, `lv`, `lt`, `pt-AO`, `en-IN` work as-is.
      3. Fallback to `en` for empty / unrecognized input — emitting an
         invalid `<html lang>` is worse than a sane default.
    """
    cleaned = raw_language.strip().strip(LANGUAGE_QUOTE_CHARS).strip()
    if not cleaned:
        return "en"
    if cleaned.lower() in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[cleaned.lower()]
    passthrough = _normalize_bcp47(cleaned)
    if passthrough is not None:
        return passthrough
    return "en"


def parse_settings_profile(path: Path) -> SettingsProfile:
    if not path.exists():
        return SettingsProfile(
            raw_language="english",
            locale="en",
            display_name=DISPLAY_NAME_BY_LOCALE["en"],
            config_overrides={},
            base_currency=DEFAULT_BASE_CURRENCY,
            missing=True,
            account_description="",
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

    base_match = re.search(BASE_CURRENCY_PATTERN, text, re.IGNORECASE)
    base_currency = base_match.group(1).upper() if base_match else DEFAULT_BASE_CURRENCY
    account_description = _extract_account_description(text)

    return SettingsProfile(
        raw_language=raw_language,
        locale=locale,
        display_name=display_name,
        config_overrides=config_overrides,
        base_currency=base_currency,
        missing=False,
        account_description=account_description,
    )


# ----------------------------------------------------------------------------- #
# Per-ticker aggregation
# ----------------------------------------------------------------------------- #

@dataclass
class TickerAggregate:
    """Per-ticker rollup used by the holdings table and the popovers.

    Per spec §9.0 every aggregate (`market_value`, `pnl_amount`,
    `weighted_avg_cost_usd`, cash totals) is in the configured base currency.
    Native trade currency is preserved for popover display via the `*_native`
    fields and `trade_currency`.
    """
    ticker: str
    market: MarketType
    bucket: str                       # representative bucket (highest seniority)
    total_qty: float
    weighted_avg_cost: Optional[float]      # native trade currency
    total_cost_known: float                 # native: Σ(lot_cost × lot_qty) over known-cost lots
    earliest_date: Optional[str]            # for hold period
    lots: List[Lot] = field(default_factory=list)

    # Filled in after price merge.
    latest_price: Optional[float] = None             # native trade currency
    move_pct: Optional[float] = None
    market_value: Optional[float] = None             # base currency (post-FX)
    pnl_amount: Optional[float] = None               # base currency
    pnl_pct: Optional[float] = None                  # ratio, currency-agnostic
    weighted_avg_cost_usd: Optional[float] = None    # base-converted avg cost
    is_cash: bool = False
    trade_currency: str = "USD"
    fx_rate_used: Optional[float] = None             # 1 unit native = N base


@dataclass
class BookPacing:
    """§9.5 book-wide aggregates for the Holding period & pacing block."""
    avg_hold_years: Optional[float]
    oldest: Optional[Tuple[str, str, str]]    # (ticker, date, duration_label)
    newest: Optional[Tuple[str, str, str]]
    pct_held_over_1y: Optional[float]
    distribution_pct: Dict[str, float]        # buckets: <1m, 1-6m, 6-12m, 1-3y, 3y+


@dataclass
class RiskHeatItem:
    ticker: str
    score: int
    band_class: str
    weight_pct: float
    move_pct: Optional[float]
    # Each reason is a structured payload `{"code": "<key>", "threshold": <pct>?}`.
    # Codes are stable across locales (see RISK_REASONS_EN for the EN labels);
    # the renderer translates them at display time using the threshold value
    # for any code that takes one (concentration_*, move_*).
    reasons: List[Dict[str, Any]]


@dataclass
class CheckResult:
    label: str
    triggered: bool
    detail: str


def _bucket_priority(name: str) -> int:
    order = {"long term": 0, "mid term": 1, "short term": 2, "cash holdings": 99}
    for k, v in order.items():
        if name.lower().startswith(k):
            return v
    return 50


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
        elif agg.market != lot.market:
            # Ticker-market collision (CB-4): same ticker code reported with
            # two different MarketType values would silently merge into the
            # first-seen market bucket, double-counting qty/cost.  Surface it
            # loudly instead.  Defense-in-depth in single-account mode (e.g.,
            # a typo like `0700.HK` vs `700.HK` recorded as different markets);
            # essential in --all-accounts mode where two accounts may record
            # the same ticker with conflicting market tags.
            raise ValueError(
                f"ticker market collision: {lot.ticker!r} has market "
                f"{agg.market.value!r} from one source and "
                f"{lot.market.value!r} from another"
            )
        if _bucket_priority(lot.bucket) < _bucket_priority(agg.bucket):
            agg.bucket = lot.bucket

        agg.lots.append(lot)
        agg.total_qty += lot.quantity
        if lot.cost is not None:
            agg.total_cost_known += lot.cost * lot.quantity
        if lot.date:
            if agg.earliest_date is None or lot.date < agg.earliest_date:
                agg.earliest_date = lot.date

    for agg in buckets.values():
        known_qty = sum(l.quantity for l in agg.lots if l.cost is not None)
        if known_qty > 0:
            agg.weighted_avg_cost = agg.total_cost_known / known_qty
    return buckets


# ----------------------------------------------------------------------------- #
# FX + price merge
# ----------------------------------------------------------------------------- #

def _fx_to_base(
    native_amount: Optional[float],
    currency: str,
    fx: Dict[str, float],
    base: str = DEFAULT_BASE_CURRENCY,
) -> Tuple[Optional[float], Optional[float]]:
    """Convert `native_amount` in `currency` to the configured base currency.

    `fx` is keyed `"<BASE>/<CCY>"` with the rate "1 unit of base = N units of CCY".
    Returns (base_amount, fx_rate_used) where `fx_rate_used` is "1 unit of native
    = X units of base" so the caller can record what was applied.
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
    """Merge prices and apply §9.0 base-currency canonicalization."""
    fx = fx or {}
    base = base.upper()
    for ticker, agg in aggs.items():
        if agg.is_cash:
            ccy = ticker.upper()
            agg.trade_currency = ccy
            if ccy in CASH_STABLECOIN_USD:
                usd_value = agg.total_qty * CASH_STABLECOIN_USD[ccy]
                base_value, base_rate = _fx_to_base(usd_value, "USD", fx, base)
                agg.market_value = base_value
                agg.fx_rate_used = base_rate
            elif ccy == base:
                agg.market_value = agg.total_qty
                agg.fx_rate_used = 1.0
            else:
                base_value, rate = _fx_to_base(agg.total_qty, ccy, fx, base)
                agg.market_value = base_value
                agg.fx_rate_used = rate
            continue

        pr = prices.get(ticker, {}) or {}
        agg.latest_price = pr.get("latest_price")
        agg.move_pct = pr.get("move_pct")
        agg.trade_currency = (pr.get("currency") or MARKET_DEFAULT_CCY.get(agg.market, "USD")).upper()

        if agg.latest_price is not None:
            native_mv = agg.latest_price * agg.total_qty
            base_mv, rate = _fx_to_base(native_mv, agg.trade_currency, fx, base)
            agg.market_value = base_mv
            agg.fx_rate_used = rate
            if agg.weighted_avg_cost not in (None, 0):
                native_cost_basis = agg.weighted_avg_cost * agg.total_qty
                base_cost_basis, _ = _fx_to_base(native_cost_basis, agg.trade_currency, fx, base)
                if base_cost_basis is not None and base_mv is not None:
                    agg.pnl_amount = base_mv - base_cost_basis
                    agg.pnl_pct = (agg.pnl_amount / base_cost_basis * 100.0) if base_cost_basis else None
                    agg.weighted_avg_cost_usd = (
                        base_cost_basis / agg.total_qty if agg.total_qty else None
                    )


def auto_fx_from_prices(
    prices: Dict[str, Any],
    base_currency: str,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Return auto-fetched FX rates from prices.json["_fx"], scoped to the base."""
    fx_payload = prices.get("_fx")
    if not isinstance(fx_payload, dict):
        logging.warning(
            "prices.json has no `_fx` payload. Re-run scripts/fetch_prices.py so "
            "FX conversion rates are auto-fetched."
        )
        return {}, {}

    payload_base = str(fx_payload.get("base") or "").upper()
    base = base_currency.upper()
    if payload_base and payload_base != base:
        logging.warning(
            "prices.json `_fx` base %s does not match SETTINGS.md base %s; "
            "ignoring stale FX payload. Re-run scripts/fetch_prices.py.",
            payload_base, base,
        )
        return {}, {}

    raw_rates = fx_payload.get("rates") if isinstance(fx_payload.get("rates"), dict) else {}
    rates: Dict[str, float] = {}
    for pair, raw_rate in raw_rates.items():
        pair_str = str(pair).upper()
        if not pair_str.startswith(f"{base}/"):
            continue
        try:
            rate = float(raw_rate)
        except (TypeError, ValueError):
            continue
        if rate > 0:
            rates[pair_str] = rate

    raw_details = fx_payload.get("details")
    details = raw_details if isinstance(raw_details, dict) else {}
    return rates, details


# ----------------------------------------------------------------------------- #
# Hold-period helpers + book pacing (§9.2 / §9.5)
# ----------------------------------------------------------------------------- #

def _days_label(days: int) -> str:
    if days < 30:
        return f"{days}d"
    months = days // 30
    if months < 12:
        return f"{months}m"
    years = months // 12
    rem = months % 12
    return f"{years}y {rem}m" if rem else f"{years}y"


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
    return _days_label(days)


def book_pacing(aggs: Dict[str, TickerAggregate], today: _dt.date) -> BookPacing:
    """§9.5 — risk-asset only, cost-weighted in base-currency basis (per §9.0)."""
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


# ----------------------------------------------------------------------------- #
# §10.4.1 high-risk heatmap rubric
# ----------------------------------------------------------------------------- #

# UI strings used in the reasons list — kept as plain strings here so the
# pipeline output is locale-stable. The renderer can map these to translated
# strings when it builds the heatmap section.
RISK_REASONS_EN: Dict[str, str] = {
    "crypto": "Crypto asset class",
    "short_bucket": "Short Term bucket",
    "mid_bucket": "Mid Term bucket",
    "concentration_breach": "Weight ≥ 1.5× single-name cap",
    "concentration_warn": "Weight ≥ single-name cap",
    "concentration_watch": "Weight ≥ 0.5× single-name cap",
    "move_breach": "Move ≥ 1.5× alert threshold",
    "move_warn": "Move ≥ alert threshold",
    "missing": "Missing latest price",
    "delayed": "Quote freshness: delayed",
    "stale": "Quote freshness: stale / unresolved",
    "core": "Baseline risk asset",
}


def build_risk_heat_items(
    aggs: Dict[str, TickerAggregate],
    prices: Dict[str, Any],
    total_assets: float,
    config: Dict[str, float],
) -> List[RiskHeatItem]:
    """§10.4.1 — score each non-cash holding and band into r-low / r-mid / r-high."""
    items: List[RiskHeatItem] = []
    single_name_cap = config.get("single_name_weight_warn_pct", DEFAULTS["single_name_weight_warn_pct"])
    move_alert = config.get("single_day_move_alert_pct", DEFAULTS["single_day_move_alert_pct"])

    for agg in aggs.values():
        if agg.is_cash or agg.market_value in (None, 0):
            continue
        weight_pct = (agg.market_value / total_assets * 100.0) if total_assets else 0.0
        pr = prices.get(agg.ticker, {}) or {}
        reasons: List[Dict[str, Any]] = []
        score = 0

        if agg.market == MarketType.CRYPTO:
            score += 3
            reasons.append({"code": "crypto"})

        bucket_key = _bucket_key(agg.bucket)
        if bucket_key == "short":
            score += 2
            reasons.append({"code": "short_bucket"})
        elif bucket_key == "mid":
            score += 1
            reasons.append({"code": "mid_bucket"})

        if weight_pct >= single_name_cap * 1.5:
            score += 3
            reasons.append({"code": "concentration_breach", "threshold": single_name_cap})
        elif weight_pct >= single_name_cap:
            score += 2
            reasons.append({"code": "concentration_warn", "threshold": single_name_cap})
        elif weight_pct >= single_name_cap * 0.5:
            score += 1
            reasons.append({"code": "concentration_watch", "threshold": single_name_cap * 0.5})

        if agg.move_pct is not None:
            abs_move = abs(agg.move_pct)
            if abs_move >= move_alert * 1.5:
                score += 2
                reasons.append({"code": "move_breach", "threshold": move_alert})
            elif abs_move >= move_alert:
                score += 1
                reasons.append({"code": "move_warn", "threshold": move_alert})

        if agg.latest_price is None or pr.get("price_source") == "n/a":
            score += 2
            reasons.append({"code": "missing"})
        else:
            freshness = pr.get("price_freshness", "n/a")
            if freshness == "delayed":
                score += 1
                reasons.append({"code": "delayed"})
            elif freshness in {"stale_after_exhaustive_search", "n/a"}:
                score += 2
                reasons.append({"code": "stale"})

        score = min(score, 10)
        if not reasons:
            reasons.append({"code": "core"})
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


# ----------------------------------------------------------------------------- #
# §11 special checks
# ----------------------------------------------------------------------------- #

def special_checks(
    aggs: Dict[str, TickerAggregate],
    total_assets: float,
    config: Dict[str, float],
    *,
    today: Optional[_dt.date] = None,
) -> List[CheckResult]:
    """Return one CheckResult per §11 item — both passes and triggers."""
    if total_assets <= 0:
        return []
    today = today or _dt.date.today()
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
        results.append(CheckResult(
            "Concentration: single asset", False, "通過 — 無單一標的超過上限"))

    # 6. Recent buying spree — 3+ adds in last 30 days per ticker
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
        sorted_lots = sorted(
            [l for l in agg.lots if l.date and l.cost is not None],
            key=lambda l: l.date or "",
        )
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

    # 10. Open cost-basis or date gaps. Cash lots intentionally carry no
    # cost/date (the position is the cash itself), so excluding them keeps the
    # check focused on the risk-asset side per §11.
    gaps = [agg.ticker for agg in aggs.values()
            if not agg.is_cash
            and any(l.cost is None or l.date is None for l in agg.lots)]
    results.append(CheckResult(
        "Open cost-basis / date gaps",
        bool(gaps),
        ", ".join(sorted(set(gaps))) if gaps else "通過 — 所有批次皆有完整成本與日期",
    ))
    return results


# ----------------------------------------------------------------------------- #
# §10.1.7 trading-psychology evaluation
#
# The renderer reads `context["trading_psychology"]` with the shape
# `{headline, observations[], improvements[], strengths[]}`. The actual
# evaluation is **not** computed here — pure rules can't match the user's
# strategy-specific judgment. The agent must author the block after reading
# this snapshot's transaction_analytics evidence + SETTINGS strategy, validate
# it with scripts/validate_report_context.py, and only then invoke the renderer.
# ----------------------------------------------------------------------------- #


# ----------------------------------------------------------------------------- #
# Snapshot orchestration + JSON serialization
# ----------------------------------------------------------------------------- #

SCHEMA_VERSION = 1


def compute_totals(aggs: Dict[str, TickerAggregate]) -> Dict[str, Optional[float]]:
    """Aggregate-side KPI totals (base-currency basis)."""
    total_assets = sum(a.market_value or 0 for a in aggs.values())
    invested = sum(a.market_value or 0 for a in aggs.values() if not a.is_cash)
    cash = sum(a.market_value or 0 for a in aggs.values() if a.is_cash)
    pnl = sum(a.pnl_amount for a in aggs.values() if a.pnl_amount is not None) or None
    return {
        "total_assets": total_assets,
        "invested": invested,
        "cash": cash,
        "pnl": pnl,
    }


def find_missing_fx(
    aggs: Dict[str, TickerAggregate],
    fx: Dict[str, float],
    base_currency: str,
) -> List[str]:
    """§9.0 audit — currencies in the book that lack an FX rate."""
    needed_ccys = sorted({a.trade_currency for a in aggs.values() if a.trade_currency != base_currency})
    missing: List[str] = []
    for c in needed_ccys:
        if f"{base_currency}/{c}" in fx:
            continue
        if c in CASH_STABLECOIN_USD and (base_currency == "USD" or f"{base_currency}/USD" in fx):
            continue
        missing.append(c)
    return missing


def _lot_to_dict(lot: Lot) -> Dict[str, Any]:
    return {
        "ticker": lot.ticker,
        "quantity": lot.quantity,
        "cost": lot.cost,
        "date": lot.date,
        "bucket": lot.bucket,
        "market": lot.market.value if isinstance(lot.market, MarketType) else str(lot.market),
        "is_share": lot.is_share,
    }


def _lot_from_dict(d: Dict[str, Any]) -> Lot:
    market_raw = d.get("market", "US")
    try:
        market = MarketType(market_raw)
    except ValueError:
        market = MarketType.UNKNOWN
    return Lot(
        raw_line="",
        bucket=d.get("bucket", "Mid Term"),
        ticker=d["ticker"],
        quantity=float(d["quantity"]),
        cost=d.get("cost"),
        date=d.get("date"),
        market=market,
        is_share=bool(d.get("is_share", True)),
    )


def _agg_to_dict(agg: TickerAggregate) -> Dict[str, Any]:
    return {
        "ticker": agg.ticker,
        "market": agg.market.value if isinstance(agg.market, MarketType) else str(agg.market),
        "bucket": agg.bucket,
        "is_cash": agg.is_cash,
        "trade_currency": agg.trade_currency,
        "total_qty": agg.total_qty,
        "weighted_avg_cost": agg.weighted_avg_cost,
        "weighted_avg_cost_base": agg.weighted_avg_cost_usd,
        "total_cost_known": agg.total_cost_known,
        "earliest_date": agg.earliest_date,
        "latest_price": agg.latest_price,
        "move_pct": agg.move_pct,
        "market_value": agg.market_value,
        "pnl_amount": agg.pnl_amount,
        "pnl_pct": agg.pnl_pct,
        "fx_rate_used": agg.fx_rate_used,
        "lots": [_lot_to_dict(l) for l in agg.lots],
    }


def _agg_from_dict(d: Dict[str, Any]) -> TickerAggregate:
    market_raw = d.get("market", "US")
    try:
        market = MarketType(market_raw)
    except ValueError:
        market = MarketType.UNKNOWN
    agg = TickerAggregate(
        ticker=d["ticker"],
        market=market,
        bucket=d.get("bucket", "Mid Term"),
        total_qty=float(d.get("total_qty", 0.0)),
        weighted_avg_cost=d.get("weighted_avg_cost"),
        total_cost_known=float(d.get("total_cost_known", 0.0)),
        earliest_date=d.get("earliest_date"),
        is_cash=bool(d.get("is_cash", False)),
    )
    agg.trade_currency = d.get("trade_currency", "USD")
    agg.latest_price = d.get("latest_price")
    agg.move_pct = d.get("move_pct")
    agg.market_value = d.get("market_value")
    agg.pnl_amount = d.get("pnl_amount")
    agg.pnl_pct = d.get("pnl_pct")
    agg.weighted_avg_cost_usd = d.get("weighted_avg_cost_base")
    agg.fx_rate_used = d.get("fx_rate_used")
    agg.lots = [_lot_from_dict(l) for l in d.get("lots") or []]
    return agg


def _pacing_to_dict(p: BookPacing) -> Dict[str, Any]:
    return {
        "avg_hold_years": p.avg_hold_years,
        "oldest": list(p.oldest) if p.oldest else None,
        "newest": list(p.newest) if p.newest else None,
        "pct_held_over_1y": p.pct_held_over_1y,
        "distribution_pct": dict(p.distribution_pct),
    }


def _pacing_from_dict(d: Dict[str, Any]) -> BookPacing:
    oldest = tuple(d["oldest"]) if d.get("oldest") else None
    newest = tuple(d["newest"]) if d.get("newest") else None
    return BookPacing(
        avg_hold_years=d.get("avg_hold_years"),
        oldest=oldest,  # type: ignore[arg-type]
        newest=newest,  # type: ignore[arg-type]
        pct_held_over_1y=d.get("pct_held_over_1y"),
        distribution_pct=dict(d.get("distribution_pct") or {}),
    )


def _heat_to_dict(item: RiskHeatItem) -> Dict[str, Any]:
    return asdict(item)


def _heat_from_dict(d: Dict[str, Any]) -> RiskHeatItem:
    raw_reasons = list(d.get("reasons") or [])
    reasons: List[Dict[str, Any]] = []
    for r in raw_reasons:
        if isinstance(r, dict):
            reasons.append(r)
        elif isinstance(r, str):
            # Tolerate legacy snapshots that stored reasons as bare strings.
            reasons.append({"code": r})
    return RiskHeatItem(
        ticker=d["ticker"],
        score=int(d["score"]),
        band_class=d["band_class"],
        weight_pct=float(d["weight_pct"]),
        move_pct=d.get("move_pct"),
        reasons=reasons,
    )


def _check_to_dict(c: CheckResult) -> Dict[str, Any]:
    return asdict(c)


def _check_from_dict(d: Dict[str, Any]) -> CheckResult:
    return CheckResult(
        label=d["label"],
        triggered=bool(d["triggered"]),
        detail=d.get("detail", ""),
    )


@dataclass
class Snapshot:
    """Fully-resolved data the renderer needs.

    Round-trips through JSON via `serialize_snapshot` / `deserialize_snapshot`.

    The raw `prices` dict from `prices.json` is embedded so the renderer reads
    source metadata (popover provenance, freshness badges, audit table) from
    one input file. The pipeline performs every numeric computation upstream;
    the renderer just projects.
    """
    schema_version: int
    generated_at: str
    today: str
    base_currency: str
    settings_locale: str
    settings_display_name: str
    settings_raw_language: str
    settings_missing: bool
    settings_account_description: str
    config: Dict[str, float]
    aggregates: Dict[str, TickerAggregate]
    totals: Dict[str, Optional[float]]
    fx: Dict[str, float]
    fx_details: Dict[str, Any]
    missing_fx: List[str]
    book_pacing: BookPacing
    risk_heat: List[RiskHeatItem]
    special_checks: List[CheckResult]
    prices: Dict[str, Any] = field(default_factory=dict)
    profit_panel: Optional[Dict[str, Any]] = None
    realized_unrealized: Optional[Dict[str, Any]] = None
    transaction_analytics: Optional[Dict[str, Any]] = None
    trading_psychology: Optional[Dict[str, Any]] = None
    profit_panel_error: Optional[str] = None
    realized_unrealized_error: Optional[str] = None
    transaction_analytics_error: Optional[str] = None
    report_accuracy: Optional[Dict[str, Any]] = None


def _compute_snapshot_core(
    *,
    lots: List[Lot],
    txns: List[Any],
    prices: Dict[str, Any],
    settings: SettingsProfile,
    today: Optional[_dt.date] = None,
    total_mode: bool = False,
    txn_load_error: Optional[str] = None,
) -> Snapshot:
    """Math kernel.  Identical inputs -> identical outputs by construction.

    Shared between single-account ``compute_snapshot`` (the disk-loading
    wrapper) and the ``--all-accounts`` total-mode entry point in
    ``transactions.py snapshot``.

    ``total_mode=True`` is presently informational only; the math is
    identical.  ``txn_load_error`` (WRAPPER-OUTER-TRY iteration 5): when set
    by the wrapper, the kernel skips the three analytics computations and
    stamps the message into all three ``*_error`` fields, mirroring the
    pre-refactor outer-try graceful-degradation behavior on a corrupted txn
    log.

    Lazy imports ``transactions`` / ``report_accuracy`` so this module can
    be used in environments where they may not be on ``sys.path`` yet.
    """
    today = today or _dt.date.today()

    # Lazy imports to avoid import-time circularity.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report_accuracy import compute_report_accuracy       # noqa: WPS433
    from transactions import (                               # noqa: WPS433
        compute_profit_panel,
        compute_realized_unrealized,
        compute_transaction_analytics,
    )

    base = settings.base_currency
    config: Dict[str, float] = {**DEFAULTS, **settings.config_overrides}
    aggs = aggregate(lots)
    fx, fx_details = auto_fx_from_prices(prices, base)
    merge_prices(aggs, prices, fx=fx, base=base)

    totals = compute_totals(aggs)
    pacing = book_pacing(aggs, today)
    heat = build_risk_heat_items(aggs, prices, totals["total_assets"] or 0.0, config)
    checks = special_checks(aggs, totals["total_assets"] or 0.0, config, today=today)
    missing = find_missing_fx(aggs, fx, base)

    profit_panel: Optional[Dict[str, Any]] = None
    profit_panel_error: Optional[str] = None
    realized_unrealized_data: Optional[Dict[str, Any]] = None
    realized_unrealized_error: Optional[str] = None
    analytics: Optional[Dict[str, Any]] = None
    analytics_error: Optional[str] = None
    if txn_load_error is not None:
        # WRAPPER-OUTER-TRY: txn-log load failed at the wrapper; mirror the
        # pre-refactor behavior — all three analytics fields stay None, all
        # three *_error fields carry the same wrapper-supplied message.
        profit_panel_error = realized_unrealized_error = analytics_error = txn_load_error
    else:
        try:
            profit_panel = compute_profit_panel(txns, prices, base=base, today=today)
        except Exception as e:                                # noqa: BLE001
            profit_panel_error = str(e)
        try:
            realized_unrealized_data = compute_realized_unrealized(txns, prices, base=base)
        except Exception as e:                                # noqa: BLE001
            realized_unrealized_error = str(e)
        try:
            analytics = compute_transaction_analytics(txns, prices, base=base, today=today)
        except Exception as e:                                # noqa: BLE001
            analytics_error = str(e)

    position_tickers = [a.ticker for a in aggs.values() if not a.is_cash]
    report_accuracy = compute_report_accuracy(
        profit_panel=profit_panel,
        prices=prices,
        position_tickers=position_tickers,
        missing_fx=missing,
        errors={
            "profit_panel": profit_panel_error,
            "realized_unrealized": realized_unrealized_error,
            "transaction_analytics": analytics_error,
        },
    )

    # §10.1.7 trading psychology is NOT auto-generated from rules. It is a
    # mandatory agent-authored report_context block after snapshot generation.
    psychology: Optional[Dict[str, Any]] = None

    return Snapshot(
        schema_version=SCHEMA_VERSION,
        generated_at=_dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        today=today.isoformat(),
        base_currency=base,
        settings_locale=settings.locale,
        settings_display_name=settings.display_name,
        settings_raw_language=settings.raw_language,
        settings_missing=settings.missing,
        settings_account_description=settings.account_description,
        config=config,
        aggregates=aggs,
        totals=totals,
        fx=fx,
        fx_details=fx_details,
        missing_fx=missing,
        book_pacing=pacing,
        risk_heat=heat,
        special_checks=checks,
        prices=prices,
        profit_panel=profit_panel,
        realized_unrealized=realized_unrealized_data,
        transaction_analytics=analytics,
        trading_psychology=psychology,
        profit_panel_error=profit_panel_error,
        realized_unrealized_error=realized_unrealized_error,
        transaction_analytics_error=analytics_error,
        report_accuracy=report_accuracy,
    )


def compute_snapshot(
    *,
    db_path: Path,
    prices: Dict[str, Any],
    settings: SettingsProfile,
    today: Optional[_dt.date] = None,
) -> Snapshot:
    """Single-account entry point.  Loads lots + txns from disk, then
    delegates to ``_compute_snapshot_core``.

    WRAPPER-OUTER-TRY: preserves the exact graceful-degradation semantics of
    the pre-refactor body.  If ``load_transactions_db`` raises, the wrapper
    still calls the kernel with ``txns=[]`` and a ``txn_load_error`` so the
    snapshot's positions/cash/totals math still renders, but the three
    analytics fields carry the load error.  ``load_holdings_lots`` is NOT
    wrapped (a Lot-load failure propagates exactly as in the pre-refactor
    code).

    Lazy imports ``transactions`` so this module can be used in environments
    where ``transactions.py`` may not be on ``sys.path`` yet.
    """
    # Lazy imports to avoid import-time circularity.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from transactions import (                               # noqa: WPS433
        load_holdings_lots,
        load_transactions_db,
    )

    lots = load_holdings_lots(db_path)
    try:
        txns = load_transactions_db(db_path)
        txn_load_error: Optional[str] = None
    except Exception as e:                                    # noqa: BLE001
        txns = []
        txn_load_error = f"could not load transactions from {db_path}: {e}"

    return _compute_snapshot_core(
        lots=lots,
        txns=txns,
        prices=prices,
        settings=settings,
        today=today,
        total_mode=False,
        txn_load_error=txn_load_error,
    )


def serialize_snapshot(snap: Snapshot) -> Dict[str, Any]:
    """Convert a Snapshot to a JSON-safe dict."""
    return {
        "schema_version": snap.schema_version,
        "generated_at": snap.generated_at,
        "today": snap.today,
        "base_currency": snap.base_currency,
        "settings": {
            "locale": snap.settings_locale,
            "display_name": snap.settings_display_name,
            "raw_language": snap.settings_raw_language,
            "missing": snap.settings_missing,
            "account_description": snap.settings_account_description,
        },
        "config": dict(snap.config),
        "aggregates": [_agg_to_dict(a) for a in snap.aggregates.values()],
        "totals": dict(snap.totals),
        "fx": dict(snap.fx),
        "fx_details": dict(snap.fx_details) if isinstance(snap.fx_details, dict) else {},
        "missing_fx": list(snap.missing_fx),
        "book_pacing": _pacing_to_dict(snap.book_pacing),
        "risk_heat": [_heat_to_dict(h) for h in snap.risk_heat],
        "special_checks": [_check_to_dict(c) for c in snap.special_checks],
        "prices": dict(snap.prices) if isinstance(snap.prices, dict) else {},
        "profit_panel": snap.profit_panel,
        "realized_unrealized": snap.realized_unrealized,
        "transaction_analytics": snap.transaction_analytics,
        "trading_psychology": snap.trading_psychology,
        "errors": {
            "profit_panel": snap.profit_panel_error,
            "realized_unrealized": snap.realized_unrealized_error,
            "transaction_analytics": snap.transaction_analytics_error,
        },
        "report_accuracy": snap.report_accuracy,
    }


def deserialize_snapshot(payload: Dict[str, Any]) -> Snapshot:
    """Inverse of `serialize_snapshot`. Raises on schema mismatch."""
    schema = int(payload.get("schema_version") or 0)
    if schema != SCHEMA_VERSION:
        raise ValueError(
            f"snapshot schema_version {schema} not supported (expected {SCHEMA_VERSION}); "
            "regenerate via `python scripts/transactions.py snapshot`."
        )
    aggs_dict: Dict[str, TickerAggregate] = {}
    for entry in payload.get("aggregates") or []:
        agg = _agg_from_dict(entry)
        aggs_dict[agg.ticker] = agg

    settings = payload.get("settings") or {}
    errors = payload.get("errors") or {}
    return Snapshot(
        schema_version=schema,
        generated_at=str(payload.get("generated_at") or ""),
        today=str(payload.get("today") or ""),
        base_currency=str(payload.get("base_currency") or DEFAULT_BASE_CURRENCY),
        settings_locale=str(settings.get("locale") or "en"),
        settings_display_name=str(settings.get("display_name") or "English"),
        settings_raw_language=str(settings.get("raw_language") or "english"),
        settings_missing=bool(settings.get("missing", False)),
        settings_account_description=str(settings.get("account_description") or ""),
        config={k: float(v) for k, v in (payload.get("config") or {}).items()},
        aggregates=aggs_dict,
        totals=dict(payload.get("totals") or {}),
        fx={str(k): float(v) for k, v in (payload.get("fx") or {}).items()},
        fx_details=dict(payload.get("fx_details") or {}),
        missing_fx=list(payload.get("missing_fx") or []),
        book_pacing=_pacing_from_dict(payload.get("book_pacing") or {}),
        risk_heat=[_heat_from_dict(h) for h in (payload.get("risk_heat") or [])],
        special_checks=[_check_from_dict(c) for c in (payload.get("special_checks") or [])],
        prices=dict(payload.get("prices") or {}),
        profit_panel=payload.get("profit_panel"),
        realized_unrealized=payload.get("realized_unrealized"),
        transaction_analytics=payload.get("transaction_analytics"),
        trading_psychology=payload.get("trading_psychology"),
        profit_panel_error=errors.get("profit_panel"),
        realized_unrealized_error=errors.get("realized_unrealized"),
        transaction_analytics_error=errors.get("transaction_analytics"),
        report_accuracy=payload.get("report_accuracy"),
    )


def write_snapshot(snap: Snapshot, output_path: Path) -> int:
    """Write serialized snapshot to disk; return bytes written."""
    payload = serialize_snapshot(snap)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized, encoding="utf-8")
    return len(serialized)


def settings_profile_for_snapshot(settings: Snapshot) -> SettingsProfile:
    """Reconstruct a SettingsProfile shim from a deserialized snapshot.

    Used by the renderer when loading via `--snapshot` so the rest of the
    rendering chain can reuse `SettingsProfile`-shaped APIs without re-reading
    SETTINGS.md.
    """
    return SettingsProfile(
        raw_language=settings.settings_raw_language,
        locale=settings.settings_locale,
        display_name=settings.settings_display_name,
        config_overrides={},  # already merged into config; empty here
        base_currency=settings.base_currency,
        missing=settings.settings_missing,
        account_description=settings.settings_account_description,
    )


__all__ = [
    "DEFAULTS",
    "DEFAULT_BASE_CURRENCY",
    "BASE_CURRENCY_PATTERN",
    "ACCOUNT_DESCRIPTION_PATTERN",
    "LANGUAGE_QUOTE_CHARS",
    "LANGUAGE_ALIASES",
    "DISPLAY_NAME_BY_LOCALE",
    "BUILTIN_UI_LOCALES",
    "RAIL_PATTERNS",
    "MARKET_DEFAULT_CCY",
    "CASH_STABLECOIN_USD",
    "RISK_REASONS_EN",
    "SCHEMA_VERSION",
    "SettingsProfile",
    "TickerAggregate",
    "BookPacing",
    "RiskHeatItem",
    "CheckResult",
    "Snapshot",
    "parse_settings_profile",
    "aggregate",
    "_fx_to_base",
    "merge_prices",
    "auto_fx_from_prices",
    "hold_period_label",
    "book_pacing",
    "_days_label",
    "_bucket_priority",
    "_bucket_key",
    "build_risk_heat_items",
    "special_checks",
    "compute_totals",
    "find_missing_fx",
    "compute_snapshot",
    "serialize_snapshot",
    "deserialize_snapshot",
    "write_snapshot",
    "settings_profile_for_snapshot",
]
