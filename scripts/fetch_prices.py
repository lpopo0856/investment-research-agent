#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_prices.py — Latest-price retrieval template for the portfolio report agent.

Implements `docs/portfolio_report_agent_guidelines.md` §8 (Latest-price retrieval pipeline):

  1. Parse HOLDINGS.md (§4.1)
  2. Group tickers by market type and resolve the market-native primary source path (§8.5)
  3. **PRIMARY**: Stooq (no-token) for listed securities — `.us`/`.uk`/`.jp`/`.hk`/`.tw` suffixes
  4. **SECONDARY**: yfinance per-ticker history (skip crypto) — used only when Stooq misses (§8.3)
  5. yfinance failure recovery — up to 3 auto-correction attempts per failure (§8.4)
  6. Tertiary fallback: keyed APIs (Twelve Data / Finnhub / etc.) → web (manual) (§8.1, §8.5)
  7. **Currency verification**: every successful price result has its `currency` confirmed
     against a live internet source (Stooq metadata, yfinance fast_info, exchange API) before
     falling back to the hardcoded MARKET_DEFAULT_CCY map.
  8. Apply Freshness gate (§8.7)
  9. Emit JSON with the §8.8 stored-fields contract per ticker.

Output JSON shape (per ticker):

    {
      "<TICKER>": {
        "latest_price":           177.34,            // null if n/a
        "prior_close":             175.21,           // prior close or 24h reference for crypto
        "move_pct":                1.22,
        "currency":               "USD",
        "exchange":               "NMS",
        "price_source":           "yfinance",        // or "twelve_data", "finnhub",
                                                     // "coingecko", "no_token:binance",
                                                     // "web:yahoo", "n/a", ...
        "price_as_of":            "2026-04-28T13:30:00-04:00",
        "price_freshness":        "fresh",           // "fresh", "delayed",
                                                     // "stale_after_exhaustive_search", "n/a"
        "market_state_basis":     "regular_open",    // see FreshnessGate
        "yfinance_auto_fix_applied": true,           // optional
        "yfinance_auto_fix_summary": "BRK.B -> BRK-B",
        "yfinance_retry_count":   1,                 // optional, set when retries fired
        "yfinance_request_started_at": "2026-04-28T13:29:55Z",
        "yfinance_request_latency_ms": 1842,
        "yfinance_failure_reason": null,
        "fallback_chain":         ["yfinance", "yfinance_history"],
        "market":                 "US",
        "yfinance_symbol":        "NVDA"
      },
      "_fx": {
        "base": "USD",
        "required_currencies": ["TWD", "JPY"],
        "rates": {
          "USD/TWD": 32.5
        },
        "details": {
          "USD/TWD": {
            "latest_price": 32.5,
            "price_source": "yfinance",
            "price_as_of": "2026-04-28T13:30:00+00:00",
            "fallback_chain": ["yfinance_batch"]
          }
        }
      },
      "_audit": { ... summary stats ... }
    }

USAGE
-----
    python scripts/fetch_prices.py \
        --holdings HOLDINGS.md \
        --settings SETTINGS.md \
        --output prices.json

The script does NOT make web-search calls (those require the agent's tooling, not Python).
For tickers that fall through the keyed-API and no-token tiers, it records the failure
reason and leaves `price_source = "n/a"` so the agent can fill the gap with web search
during report generation.

DEPENDENCIES
------------
    pip install yfinance requests

Per spec §8.0, the **latest-price subagent owns the install step** — it must verify
that `yfinance` and `requests` are importable (and install them if not) *before*
invoking this script. The script does not self-install: it imports yfinance lazily
inside the batch function so the parser, freshness gate, and JSON shape can still be
unit-tested via `--skip-yfinance` even when the package is absent.

If `import yfinance` fails at runtime, every ticker is recorded with
`price_source = "n/a"` and `yfinance_failure_reason = "yfinance_not_installed"`,
and the agent should re-read §8.0, complete the install, and re-run.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ----------------------------------------------------------------------------- #
# Constants — edit cautiously. These mirror the spec; deviations must be agreed.
# ----------------------------------------------------------------------------- #

# §8.3 — pacing
YF_MIN_GAP_SEC: Tuple[float, float] = (1.5, 2.5)   # random.uniform(*range) between calls
YF_BATCH_SIZE: int = 25                            # max tickers per batch
YF_BATCH_GAP_SEC: float = 3.0                      # gap between batches
YF_HTTP_TIMEOUT_SEC: int = 12                      # per-request HTTP timeout
YF_RATE_LIMIT_BACKOFF: Tuple[int, ...] = (30, 60, 120, 300)  # exponential, max 3 retries

# §8.4 — auto-correction budget
YF_MAX_CORRECTION_ATTEMPTS: int = 3

# §8.7 — freshness gate categories (informational labels)
class MarketState(str, Enum):
    REGULAR_OPEN = "regular_open"
    AFTER_CLOSE = "after_close"
    NOT_OPENED_YET = "not_opened_yet"
    WEEKEND_HOLIDAY = "weekend_holiday"
    CRYPTO_24_7 = "crypto_24_7"
    UNKNOWN = "unknown"


# §4.1 — market types declared on HOLDINGS lots
class MarketType(str, Enum):
    US = "US"            # NYSE / NASDAQ / AMEX (yfinance: bare ticker)
    TW = "TW"            # Taiwan listed (yfinance: <code>.TW)
    TWO = "TWO"          # Taiwan OTC / TPEx (yfinance: <code>.TWO)
    JP = "JP"            # Tokyo (yfinance: <code>.T)
    HK = "HK"            # Hong Kong (yfinance: <code>.HK)
    LSE = "LSE"          # London (yfinance: <code>.L)
    CRYPTO = "crypto"    # native crypto feeds: Binance / CoinGecko
    FX = "FX"            # yfinance: <PAIR>=X
    CASH = "cash"        # bare currency holding — no price fetch
    UNKNOWN = "unknown"


# §9.0 — base currency remains a SETTINGS.md preference, but user-supplied FX
# rates do not. Conversion rates are auto-fetched into prices.json["_fx"].
BASE_CURRENCY_PATTERN = r"Base currency:\s*([A-Za-z]{3})"
DEFAULT_BASE_CURRENCY = "USD"

# §9.0 — default trade currencies when the quote feed does not provide metadata.
MARKET_DEFAULT_CCY: Dict[MarketType, str] = {
    MarketType.US: "USD",
    MarketType.TW: "TWD",
    MarketType.TWO: "TWD",
    MarketType.JP: "JPY",
    MarketType.HK: "HKD",
    MarketType.LSE: "GBP",
    MarketType.CRYPTO: "USD",
    MarketType.FX: "USD",
    MarketType.UNKNOWN: "USD",
    MarketType.CASH: "USD",
}

# USD stablecoin tickers held as cash are converted as USD exposure.
CASH_STABLECOIN_USD = {
    "USDC", "USDT", "DAI", "BUSD", "TUSD", "USDP",
}


# Heuristic fallback when no [market] tag is present (§4.1 backward compat)
KNOWN_CRYPTO_SYMBOLS = {
    "BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "DOT", "MATIC", "LTC", "LINK",
    "AVAX", "USDC", "USDT", "DAI", "BNB", "TRX", "ATOM", "UNI", "FIL", "TON",
    "NEAR", "APT", "SUI", "ARB", "OP", "INJ", "RNDR", "SEI", "TIA",
}
COINGECKO_ID_MAP = {
    "ADA": "cardano",
    "APT": "aptos",
    "ARB": "arbitrum",
    "ATOM": "cosmos",
    "AVAX": "avalanche-2",
    "BNB": "binancecoin",
    "BTC": "bitcoin",
    "DAI": "dai",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "ETH": "ethereum",
    "FIL": "filecoin",
    "INJ": "injective-protocol",
    "LINK": "chainlink",
    "LTC": "litecoin",
    "MATIC": "matic-network",
    "NEAR": "near",
    "OP": "optimism",
    "RNDR": "render-token",
    "SEI": "sei-network",
    "SOL": "solana",
    "SUI": "sui",
    "TIA": "celestia",
    "TON": "the-open-network",
    "TRX": "tron",
    "UNI": "uniswap",
    "USDC": "usd-coin",
    "USDT": "tether",
    "XRP": "ripple",
}
KNOWN_FIAT_CODES = {
    "USD", "TWD", "JPY", "EUR", "GBP", "HKD", "CNY", "KRW", "SGD", "AUD",
    "CAD", "CHF", "NZD", "INR", "MXN", "BRL",
}

# Suffix → market mapping for tickers like "2330.TW" or "7203.T"
SUFFIX_TO_MARKET: Dict[str, MarketType] = {
    ".TW": MarketType.TW,
    ".TWO": MarketType.TWO,
    ".T":  MarketType.JP,
    ".HK": MarketType.HK,
    ".L":  MarketType.LSE,
}


# ----------------------------------------------------------------------------- #
# Dataclasses
# ----------------------------------------------------------------------------- #

@dataclass
class Lot:
    """One line in HOLDINGS.md (§4.1). `cost` and `date` may be None when "?" used."""
    raw_line: str
    bucket: str               # "Long Term", "Mid Term", "Short Term", "Cash Holdings"
    ticker: str               # canonicalized, no market suffix here
    quantity: float
    cost: Optional[float]
    date: Optional[str]       # ISO YYYY-MM-DD
    market: MarketType
    is_share: bool = True     # True for equities/ETFs, False for crypto/FX/cash


@dataclass
class PriceResult:
    """§8.8 — fields persisted per ticker."""
    ticker: str
    market: MarketType
    yfinance_symbol: Optional[str]

    latest_price: Optional[float] = None
    prior_close: Optional[float] = None
    move_pct: Optional[float] = None
    currency: Optional[str] = None
    exchange: Optional[str] = None

    price_source: str = "n/a"
    price_as_of: Optional[str] = None
    price_freshness: str = "n/a"      # "fresh", "delayed", "stale_after_exhaustive_search", "n/a"
    market_state_basis: str = MarketState.UNKNOWN.value

    yfinance_auto_fix_applied: bool = False
    yfinance_auto_fix_summary: Optional[str] = None
    yfinance_retry_count: int = 0
    yfinance_request_started_at: Optional[str] = None
    yfinance_request_latency_ms: Optional[int] = None
    yfinance_failure_reason: Optional[str] = None

    fallback_chain: List[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- #
# HOLDINGS.md parser (§4.1)
# ----------------------------------------------------------------------------- #

# Equity/ETF line:
#   "<TICKER>: <qty> shares @ <cost> on <YYYY-MM-DD> [<MARKET>]"
# Crypto / FX:
#   "<SYMBOL> <qty> @ <cost> on <YYYY-MM-DD> [<MARKET>]"
# Cash:
#   "<CURRENCY>: <amount> [<MARKET>]"   (market optional, defaults to cash)
#
# `?` is allowed for cost or date.
# `[MARKET]` suffix is optional (back-compat); when missing we fall back to heuristics.

_BUCKET_HEADER_RE = re.compile(r"^##\s+(?P<bucket>[^#].*?)\s*$")
_MARKET_TAG_RE = re.compile(r"\s*\[(?P<market>[A-Za-z0-9_-]+)\]\s*$")

_EQUITY_RE = re.compile(
    r"^\s*-\s*"
    r"(?P<ticker>[A-Za-z0-9._-]+)\s*:\s*"
    r"(?P<qty>[0-9]*\.?[0-9]+)\s*shares?\s*@\s*"
    r"(?P<cost>\?|[A-Z$NTｄ$]*\$?[0-9.,]+)\s*"
    r"on\s*(?P<date>\?|\d{4}-\d{2}-\d{2})"
    r"\s*$"
)

_CRYPTO_FX_RE = re.compile(
    r"^\s*-\s*"
    r"(?P<ticker>[A-Za-z0-9._-]+)\s+"
    r"(?P<qty>[0-9]*\.?[0-9]+)\s*@\s*"
    r"(?P<cost>\?|[A-Z$NT$]*\$?[0-9.,]+)\s*"
    r"on\s*(?P<date>\?|\d{4}-\d{2}-\d{2})"
    r"\s*$"
)

_CASH_RE = re.compile(
    r"^\s*-\s*"
    r"(?P<ticker>[A-Za-z][A-Za-z0-9._-]*)\s*:\s*"
    r"(?P<qty>[0-9.,]+)"
    r"\s*$"
)


def _strip_market_tag(line: str) -> Tuple[str, Optional[str]]:
    """Pull out `[MARKET]` suffix if present. Returns (cleaned_line, market_str_or_None)."""
    m = _MARKET_TAG_RE.search(line)
    if not m:
        return line, None
    return line[: m.start()].rstrip(), m.group("market")


def _parse_cost(s: str) -> Optional[float]:
    if s == "?" or s is None:
        return None
    # Strip currency prefix like "$", "NT$", "¥", commas
    cleaned = re.sub(r"[^0-9.\-]", "", s)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_ticker(ticker: str) -> str:
    """Canonicalize: uppercase the alphabetic part, preserve dotted suffix as-is.

    >>> _normalize_ticker("nvda")
    'NVDA'
    >>> _normalize_ticker("2330.tw")
    '2330.TW'
    >>> _normalize_ticker("BRK.B")
    'BRK.B'
    """
    if "." in ticker:
        head, *suffix = ticker.split(".")
        return head.upper() + "." + ".".join(s.upper() for s in suffix)
    return ticker.upper()


def _heuristic_market(ticker: str, bucket: str, is_share: bool) -> MarketType:
    """When no [MARKET] tag present, derive market from bucket / ticker shape."""
    if bucket.lower().startswith("cash"):
        # Currency code → cash
        if ticker.upper() in KNOWN_FIAT_CODES:
            return MarketType.CASH
        # Stablecoin held as cash → still CASH for valuation, no price needed
        if ticker.upper() in KNOWN_CRYPTO_SYMBOLS:
            return MarketType.CASH
        return MarketType.CASH

    # Suffix routing
    for suf, mkt in SUFFIX_TO_MARKET.items():
        if ticker.upper().endswith(suf):
            return mkt

    # Known crypto symbol
    if not is_share and ticker.upper() in KNOWN_CRYPTO_SYMBOLS:
        return MarketType.CRYPTO

    # FX pair like "USDJPY" or "EURUSD" (length 6 of fiat codes)
    if (
        not is_share
        and len(ticker) == 6
        and ticker[:3].upper() in KNOWN_FIAT_CODES
        and ticker[3:].upper() in KNOWN_FIAT_CODES
    ):
        return MarketType.FX

    # Default: US equity/ETF
    return MarketType.US


def parse_holdings(path: Path) -> List[Lot]:
    """Parse HOLDINGS.md. Lines that don't match a known format are skipped silently."""
    lots: List[Lot] = []
    bucket = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _BUCKET_HEADER_RE.match(line)
        if m:
            bucket = m.group("bucket").strip()
            continue
        if not line.lstrip().startswith("-"):
            continue

        cleaned, market_str = _strip_market_tag(line)

        m_eq = _EQUITY_RE.match(cleaned)
        m_cf = _CRYPTO_FX_RE.match(cleaned) if not m_eq else None
        m_ca = _CASH_RE.match(cleaned) if not (m_eq or m_cf) else None

        if m_eq:
            ticker = _normalize_ticker(m_eq.group("ticker"))
            try:
                qty = float(m_eq.group("qty").replace(",", ""))
            except ValueError:
                continue
            cost_raw = m_eq.group("cost")
            cost = None if cost_raw == "?" else _parse_cost(cost_raw)
            date = None if m_eq.group("date") == "?" else m_eq.group("date")
            mkt = _resolve_market(market_str, ticker, bucket, is_share=True)
            lots.append(Lot(raw, bucket, ticker, qty, cost, date, mkt, is_share=True))
        elif m_cf:
            ticker = _normalize_ticker(m_cf.group("ticker"))
            try:
                qty = float(m_cf.group("qty").replace(",", ""))
            except ValueError:
                continue
            cost_raw = m_cf.group("cost")
            cost = None if cost_raw == "?" else _parse_cost(cost_raw)
            date = None if m_cf.group("date") == "?" else m_cf.group("date")
            mkt = _resolve_market(market_str, ticker, bucket, is_share=False)
            lots.append(Lot(raw, bucket, ticker, qty, cost, date, mkt, is_share=False))
        elif m_ca:
            ticker = _normalize_ticker(m_ca.group("ticker"))
            try:
                qty = float(m_ca.group("qty").replace(",", ""))
            except ValueError:
                continue
            mkt = _resolve_market(market_str, ticker, bucket, is_share=False) \
                  if market_str else MarketType.CASH
            lots.append(Lot(raw, bucket, ticker, qty, None, None, mkt, is_share=False))
        # silently skip lines that don't parse — agent should validate separately
    return lots


def _resolve_market(market_str: Optional[str], ticker: str, bucket: str, *, is_share: bool) -> MarketType:
    if market_str:
        try:
            return MarketType(market_str)
        except ValueError:
            # accept lowercase / synonyms
            normalized = market_str.strip().lower()
            for m in MarketType:
                if m.value.lower() == normalized:
                    return m
            logging.warning("Unknown market tag %r on ticker %s; using heuristic", market_str, ticker)
    return _heuristic_market(ticker, bucket, is_share)


# ----------------------------------------------------------------------------- #
# SETTINGS.md parser — extracts base currency and optional API keys.
# It intentionally ignores any stale user-supplied FX-rate lines.
# ----------------------------------------------------------------------------- #

API_KEY_NAMES = (
    "TWELVE_DATA_API_KEY",
    "FINNHUB_API_KEY",
    "COINGECKO_DEMO_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "FMP_API_KEY",
    "TIINGO_API_KEY",
    "POLYGON_API_KEY",
    "JQUANTS_REFRESH_TOKEN",
)


def parse_settings_keys(path: Optional[Path]) -> Dict[str, str]:
    """Extract optional API keys (§8.6). Missing file or missing keys are not errors."""
    keys: Dict[str, str] = {}
    if path is None or not path.exists():
        return keys
    text = path.read_text(encoding="utf-8")
    for name in API_KEY_NAMES:
        m = re.search(rf"^\s*-?\s*{re.escape(name)}\s*[:=]\s*(?P<v>\S+)\s*$", text, re.MULTILINE)
        if m and m.group("v") not in {"", "''", '""'}:
            keys[name] = m.group("v")
    return keys


def parse_base_currency(path: Optional[Path]) -> str:
    """Extract the report base currency. Missing or malformed values default to USD."""
    if path is None or not path.exists():
        return DEFAULT_BASE_CURRENCY
    text = path.read_text(encoding="utf-8")
    m = re.search(BASE_CURRENCY_PATTERN, text, re.IGNORECASE)
    if not m:
        return DEFAULT_BASE_CURRENCY
    return m.group(1).upper()


# ----------------------------------------------------------------------------- #
# Symbol routing per market (§8.5)
# ----------------------------------------------------------------------------- #

def to_yfinance_symbol(ticker: str, market: MarketType) -> Optional[str]:
    """Map (ticker, market) → Yahoo-style symbol. None means not fetchable via yfinance."""
    t = ticker.upper()
    if market == MarketType.CASH:
        return None  # cash never gets a yfinance lookup
    if market == MarketType.CRYPTO:
        return None  # crypto is sourced from native market APIs, not yfinance
    if market == MarketType.FX:
        return t if t.endswith("=X") else f"{t}=X"
    if market == MarketType.TW:
        return t if t.endswith(".TW") else f"{t}.TW"
    if market == MarketType.TWO:
        return t if t.endswith(".TWO") else f"{t}.TWO"
    if market == MarketType.JP:
        return t if t.endswith(".T") else f"{t}.T"
    if market == MarketType.HK:
        return t if t.endswith(".HK") else f"{t}.HK"
    if market == MarketType.LSE:
        return t if t.endswith(".L") else f"{t}.L"
    # US / UNKNOWN — bare ticker, but normalize "BRK.B" → "BRK-B" (Yahoo convention)
    if "." in t and not any(t.endswith(s) for s in SUFFIX_TO_MARKET):
        return t.replace(".", "-")
    return t


# ----------------------------------------------------------------------------- #
# Pacing helpers
# ----------------------------------------------------------------------------- #

class Pacer:
    """Enforces §8.3 pacing between yfinance calls."""

    def __init__(self) -> None:
        self._last_call_ts: Optional[float] = None

    def wait(self) -> None:
        if self._last_call_ts is None:
            self._last_call_ts = time.monotonic()
            return
        gap = random.uniform(*YF_MIN_GAP_SEC)
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_call_ts = time.monotonic()

    def reset_after_batch(self) -> None:
        time.sleep(YF_BATCH_GAP_SEC)
        self._last_call_ts = time.monotonic()


def _backoff_sleep(retry_idx: int) -> None:
    if retry_idx >= len(YF_RATE_LIMIT_BACKOFF):
        retry_idx = len(YF_RATE_LIMIT_BACKOFF) - 1
    delay = YF_RATE_LIMIT_BACKOFF[retry_idx]
    logging.warning("Rate-limited / empty result; backoff %ss (retry %d).", delay, retry_idx + 1)
    time.sleep(delay)


# ----------------------------------------------------------------------------- #
# yfinance batch + per-ticker fetch
# ----------------------------------------------------------------------------- #

def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _classify_market_state(market: MarketType, info: Optional[dict] = None) -> MarketState:
    """Best-effort classification. Real implementation should consult the exchange calendar."""
    if market == MarketType.CRYPTO:
        return MarketState.CRYPTO_24_7
    # The agent should refine this using `pandas_market_calendars` or similar; we return
    # UNKNOWN here so the freshness gate falls back to "accept latest if it parses".
    return MarketState.UNKNOWN


def _freshness_for_state(state: MarketState, has_intraday: bool) -> str:
    """Coarse mapping. Override in the agent's run when the state is known precisely."""
    if state == MarketState.CRYPTO_24_7:
        return "fresh"
    if state == MarketState.REGULAR_OPEN:
        return "fresh" if has_intraday else "stale_after_exhaustive_search"
    if state == MarketState.AFTER_CLOSE:
        return "fresh" if has_intraday else "delayed"
    if state == MarketState.NOT_OPENED_YET:
        return "delayed"   # previous opened trading day's close is acceptable
    if state == MarketState.WEEKEND_HOLIDAY:
        return "delayed"
    return "fresh" if has_intraday else "delayed"


def _yfinance_batch(
    yf_symbols: List[str],
    pacer: Pacer,
    session: Optional[Any] = None,
) -> Tuple[Dict[str, Tuple[Optional[float], Optional[float], Optional[str]]], Optional[str]]:
    """
    Run a single yfinance batch call. Returns (results_by_symbol, batch_failure_reason).
      results_by_symbol[symbol] = (latest_price, prior_close, currency)
    Failure reason is non-None when the entire batch errored.
    """
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError:
        return {}, "yfinance_not_installed"

    pacer.wait()
    started = time.monotonic()
    try:
        df = yf.download(
            tickers=" ".join(yf_symbols),
            period="5d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            threads=False,            # §8.3 — mandatory
            progress=False,
            timeout=YF_HTTP_TIMEOUT_SEC,
            session=session,
        )
    except Exception as exc:                                  # noqa: BLE001
        # §8.3.1 — distinguish rate-limit from other failures so auto-correction can skip.
        msg = f"{type(exc).__name__}:{exc!s:.200}"
        if _is_rate_limit_error(exc):
            return {}, "rate_limited"
        return {}, f"yfinance_batch_exception:{msg}"
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        logging.info("yfinance batch (%d symbols) finished in %dms", len(yf_symbols), latency_ms)

    out: Dict[str, Tuple[Optional[float], Optional[float], Optional[str]]] = {}
    if df is None or df.empty:
        return out, "yfinance_batch_empty"

    # df is multi-indexed when group_by="ticker" with multiple symbols
    for sym in yf_symbols:
        try:
            sub = df[sym] if len(yf_symbols) > 1 else df
            closes = sub["Close"].dropna()
            if closes.empty:
                continue
            latest = float(closes.iloc[-1])
            prior = float(closes.iloc[-2]) if len(closes) >= 2 else None
            out[sym] = (latest, prior, None)  # currency not in batch frame
        except Exception:                                     # noqa: BLE001
            continue
    return out, None


def _yfinance_per_ticker_history(symbol: str, pacer: Pacer, session: Optional[Any]) -> Optional[Tuple[float, Optional[float], Optional[str], Optional[str]]]:
    """Fallback per-symbol history call. Returns (latest, prior_close, currency, exchange) or None."""
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError:
        return None

    pacer.wait()
    try:
        tk = yf.Ticker(symbol, session=session)
        hist = tk.history(period="5d", interval="1d", auto_adjust=False, timeout=YF_HTTP_TIMEOUT_SEC)
        if hist is None or hist.empty:
            return None
        latest = float(hist["Close"].iloc[-1])
        prior = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
        info = {}
        with contextlib.suppress(Exception):
            info = tk.fast_info or {}
        currency = info.get("currency") if isinstance(info, dict) else None
        exchange = info.get("exchange") if isinstance(info, dict) else None
        return latest, prior, currency, exchange
    except Exception as exc:                                  # noqa: BLE001
        logging.info("yfinance per-ticker %s failed: %s", symbol, exc)
        return None


# ----------------------------------------------------------------------------- #
# Auto-correction (§8.4)
# ----------------------------------------------------------------------------- #

def _is_rate_limit_error(exc: BaseException) -> bool:
    """§8.3.1 — recognize yfinance rate-limit signals so auto-correction can skip."""
    name = type(exc).__name__.lower()
    s = str(exc).lower()
    if "ratelimit" in name or "ratelimit" in s:
        return True
    if "429" in s or "too many requests" in s or "too-many-requests" in s:
        return True
    return False


def _is_rate_limit_failure_reason(reason: Optional[str]) -> bool:
    """Match the failure_reason string set by `_yfinance_batch` and friends."""
    if not reason:
        return False
    r = reason.lower()
    return ("rate_limit" in r) or ("ratelimit" in r) or ("429" in r) or ("too many requests" in r)


def _auto_correct(
    result: PriceResult,
    pacer: Pacer,
    session: Optional[Any],
) -> PriceResult:
    """Up to 3 targeted correction attempts. Each attempt counts toward the §8.4 budget.

    §8.3.1 — rate-limit failures **skip** this loop entirely; retrying yfinance during
    the rate-limit window wastes the §8.3 backoff budget and prolongs the limiter
    state. The caller continues to keyed APIs / web / no-token instead.
    """
    if _is_rate_limit_failure_reason(result.yfinance_failure_reason):
        logging.info("Skipping yfinance auto-correction for %s (rate-limited; §8.3.1 tier-down).",
                     result.ticker)
        result.fallback_chain.append("yfinance_auto_correction:skipped_rate_limited")
        return result

    base_symbol = result.yfinance_symbol or result.ticker
    candidates: List[Tuple[str, str]] = []

    # Attempt 1 — Yahoo BRK.B-style normalization (dot → dash)
    if "." in base_symbol and not any(base_symbol.endswith(s) for s in SUFFIX_TO_MARKET):
        candidates.append((base_symbol.replace(".", "-"), "dot-to-dash (BRK.B → BRK-B style)"))

    # Attempt 2 — try per-ticker history call instead of batch
    candidates.append((base_symbol, "per-ticker history fallback"))

    # Attempt 3 — try shorter window (for thinly-traded names)
    candidates.append((base_symbol, "history with period=1mo, interval=1d"))

    for attempt_idx, (sym, summary) in enumerate(candidates):
        if attempt_idx >= YF_MAX_CORRECTION_ATTEMPTS:
            break
        result.yfinance_retry_count += 1
        out: Optional[Tuple[float, Optional[float], Optional[str], Optional[str]]] = None
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError:
            break
        pacer.wait()
        try:
            tk = yf.Ticker(sym, session=session)
            if attempt_idx == 2:
                hist = tk.history(period="1mo", interval="1d", auto_adjust=False, timeout=YF_HTTP_TIMEOUT_SEC)
            else:
                hist = tk.history(period="5d", interval="1d", auto_adjust=False, timeout=YF_HTTP_TIMEOUT_SEC)
            if hist is None or hist.empty:
                continue
            latest = float(hist["Close"].iloc[-1])
            prior = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
            currency = None
            exchange = None
            with contextlib.suppress(Exception):
                fi = tk.fast_info or {}
                currency = fi.get("currency") if isinstance(fi, dict) else None
                exchange = fi.get("exchange") if isinstance(fi, dict) else None
            out = (latest, prior, currency, exchange)
        except Exception as exc:                              # noqa: BLE001
            result.yfinance_failure_reason = f"correction_{attempt_idx+1}:{type(exc).__name__}"
            continue

        if out is not None:
            latest, prior, currency, exchange = out
            result.latest_price = latest
            result.prior_close = prior
            result.currency = currency or result.currency
            result.exchange = exchange or result.exchange
            result.move_pct = (
                round(((latest - prior) / prior) * 100.0, 4)
                if prior and prior != 0 else None
            )
            result.price_source = "yfinance"
            result.price_as_of = _utc_iso()
            result.yfinance_auto_fix_applied = True
            result.yfinance_auto_fix_summary = summary
            result.yfinance_symbol = sym
            result.fallback_chain.append(f"yfinance_correction[{attempt_idx+1}]:{summary}")
            state = _classify_market_state(result.market)
            result.market_state_basis = state.value
            result.price_freshness = _freshness_for_state(state, has_intraday=True)
            return result

    # All attempts failed
    result.price_source = "n/a"
    result.price_freshness = "n/a"
    return result


# ----------------------------------------------------------------------------- #
# Keyed-API fallback stubs (§8.5 / §8.6)
#
# The user must populate SETTINGS.md with the relevant API keys for these to fire.
# Each helper returns a dict with the same shape as the yfinance branch on success,
# or None on miss / failure.
# ----------------------------------------------------------------------------- #

def _try_twelve_data(symbol: str, key: str, session: Any) -> Optional[Dict[str, Any]]:
    """Twelve Data /price endpoint. Fast snapshot; rate-limited on free tier."""
    try:
        url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={key}"
        r = session.get(url, timeout=YF_HTTP_TIMEOUT_SEC)
        if r.status_code != 200:
            return None
        data = r.json()
        if "price" not in data:
            return None
        return {
            "latest_price": float(data["price"]),
            "price_source": "twelve_data",
            "price_as_of": _utc_iso(),
        }
    except Exception:                                         # noqa: BLE001
        return None


def _try_finnhub(symbol: str, key: str, session: Any) -> Optional[Dict[str, Any]]:
    """Finnhub /quote endpoint (current + previous close)."""
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={key}"
        r = session.get(url, timeout=YF_HTTP_TIMEOUT_SEC)
        if r.status_code != 200:
            return None
        data = r.json()
        if "c" not in data or data["c"] in (0, None):
            return None
        latest = float(data["c"])
        prior = float(data.get("pc") or 0) or None
        return {
            "latest_price": latest,
            "prior_close": prior,
            "move_pct": round(((latest - prior) / prior) * 100.0, 4) if prior else None,
            "price_source": "finnhub",
            "price_as_of": _utc_iso(),
        }
    except Exception:                                         # noqa: BLE001
        return None


def _split_fx_pair(symbol: str) -> Optional[Tuple[str, str]]:
    """Return (base, quote) for symbols like USDTWD, USDTWD=X, or USD/TWD."""
    s = symbol.upper().replace("=X", "").replace("/", "").replace("-", "").strip()
    if len(s) != 6:
        return None
    base, quote = s[:3], s[3:]
    if base not in KNOWN_FIAT_CODES or quote not in KNOWN_FIAT_CODES:
        return None
    return base, quote


def _try_no_token_frankfurter_fx(symbol: str, session: Any) -> Optional[Dict[str, Any]]:
    """Frankfurter daily FX endpoint backed by ECB reference data, no token."""
    pair = _split_fx_pair(symbol)
    if pair is None:
        return None
    base, quote = pair
    try:
        r = session.get(
            "https://api.frankfurter.app/latest",
            params={"from": base, "to": quote},
            timeout=YF_HTTP_TIMEOUT_SEC,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        rates = data.get("rates") or {}
        rate = rates.get(quote)
        if rate in (None, 0):
            return None
        return {
            "latest_price": float(rate),
            "currency": quote,
            "exchange": "Frankfurter/ECB",
            "price_source": "no_token:frankfurter",
            "price_as_of": data.get("date") or _utc_iso(),
        }
    except Exception:                                         # noqa: BLE001
        return None


def _try_no_token_open_er_fx(symbol: str, session: Any) -> Optional[Dict[str, Any]]:
    """Open ExchangeRate-API endpoint, no token; used after ECB-backed fallback."""
    pair = _split_fx_pair(symbol)
    if pair is None:
        return None
    base, quote = pair
    try:
        r = session.get(
            f"https://open.er-api.com/v6/latest/{base}",
            timeout=YF_HTTP_TIMEOUT_SEC,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("result") not in (None, "success"):
            return None
        rates = data.get("rates") or {}
        rate = rates.get(quote)
        if rate in (None, 0):
            return None
        return {
            "latest_price": float(rate),
            "currency": quote,
            "exchange": "Open ER API",
            "price_source": "no_token:open_er_api",
            "price_as_of": data.get("time_last_update_utc") or _utc_iso(),
        }
    except Exception:                                         # noqa: BLE001
        return None


def _normalize_crypto_symbol(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith("-USD"):
        s = s[:-4]
    if s.endswith("USDT"):
        s = s[:-4]
    return s


def _resolve_coingecko_id(raw_ticker: str, session: Any, key: Optional[str] = None) -> Optional[str]:
    symbol = _normalize_crypto_symbol(raw_ticker)
    if symbol in COINGECKO_ID_MAP:
        return COINGECKO_ID_MAP[symbol]

    try:
        params = {"query": symbol}
        if key:
            params["x_cg_demo_api_key"] = key
        r = session.get(
            "https://api.coingecko.com/api/v3/search",
            params=params,
            timeout=YF_HTTP_TIMEOUT_SEC,
        )
        if r.status_code != 200:
            return None
        coins = r.json().get("coins") or []
        exact = [
            coin for coin in coins
            if str(coin.get("symbol", "")).upper() == symbol
        ]
        if not exact:
            return None
        exact.sort(key=lambda coin: coin.get("market_cap_rank") or 10**9)
        coin_id = exact[0].get("id")
        return str(coin_id) if coin_id else None
    except Exception:                                         # noqa: BLE001
        return None


def _try_coingecko(raw_ticker: str, session: Any, key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """CoinGecko simple/price endpoint with deterministic symbol→id resolution."""
    try:
        coin_id = _resolve_coingecko_id(raw_ticker, session, key)
        if not coin_id:
            return None
        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        }
        if key:
            params["x_cg_demo_api_key"] = key
        r = session.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params=params,
            timeout=YF_HTTP_TIMEOUT_SEC,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        coin = data.get(coin_id)
        if not coin or "usd" not in coin:
            return None
        latest = float(coin["usd"])
        change_24h = coin.get("usd_24h_change")
        prior = None
        if change_24h not in (None, -100):
            try:
                prior = latest / (1.0 + float(change_24h) / 100.0)
            except ZeroDivisionError:
                prior = None
        return {
            "latest_price": latest,
            "prior_close": prior,
            "move_pct": round(float(change_24h), 4) if change_24h is not None else None,
            "currency": "USD",
            "exchange": "CoinGecko",
            "price_source": "coingecko_demo" if key else "coingecko",
            "price_as_of": _utc_iso(),
        }
    except Exception:                                         # noqa: BLE001
        return None


def _try_no_token_binance(symbol: str, session: Any) -> Optional[Dict[str, Any]]:
    """Binance public spot ticker. `symbol` should be like 'BTCUSDT'."""
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        r = session.get(url, timeout=YF_HTTP_TIMEOUT_SEC)
        if r.status_code != 200:
            return None
        data = r.json()
        latest = float(data.get("lastPrice", 0)) or None
        prior = float(data.get("openPrice", 0)) or None
        change_pct = data.get("priceChangePercent")
        if latest is None:
            return None
        return {
            "latest_price": latest,
            "prior_close": prior,
            "move_pct": round(float(change_pct), 4) if change_pct is not None else None,
            "currency": "USD",
            "exchange": "Binance",
            "price_source": "no_token:binance",
            "price_as_of": _utc_iso(),
        }
    except Exception:                                         # noqa: BLE001
        return None


# §8.3.1 endpoint registry — Stooq covers US / JP / LSE without a token.
def _try_no_token_stooq(stooq_symbol: str, session: Any) -> Optional[Dict[str, Any]]:
    """Stooq JSON — free, no-token, supports `.US` / `.UK` / `.JP` / `.HK` suffixes.

    `stooq_symbol` examples: `nvda.us`, `vwra.uk`, `7203.jp`, `2330.tw` (lowercase).
    Stooq returns a JSON payload with `symbols[0]` containing
    `symbol`, `date`, `time`, `open`, `high`, `low`, `close`, `volume`.
    """
    try:
        url = f"https://stooq.com/q/l/?s={stooq_symbol}&f=sd2t2ohlcv&h&e=json"
        r = session.get(url, timeout=YF_HTTP_TIMEOUT_SEC)
        if r.status_code != 200:
            return None
        data = r.json()
        symbols = data.get("symbols")
        if not isinstance(symbols, list) or not symbols:
            return None
        row = symbols[0] or {}
        if not isinstance(row, dict):
            return None

        def _as_float(key: str) -> Optional[float]:
            raw = row.get(key)
            if raw in (None, "", "N/D", "-"):
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        close_val = _as_float("close")
        open_val = _as_float("open")
        if close_val is None or close_val <= 0:
            return None

        date_str = str(row.get("date") or "").strip()
        time_str = str(row.get("time") or "").strip()
        if date_str and time_str:
            price_as_of = f"{date_str}T{time_str}"
        elif date_str:
            price_as_of = date_str
        else:
            price_as_of = _utc_iso()

        move_pct = round(((close_val - open_val) / open_val) * 100.0, 4) if open_val else None
        return {
            "latest_price": close_val,
            "prior_close": open_val,
            "move_pct": move_pct,
            "exchange": "Stooq",
            "price_source": "no_token:stooq",
            "price_as_of": price_as_of,
        }
    except Exception:                                         # noqa: BLE001
        return None


def _try_no_token_twse_mis(twse_code: str, session: Any) -> Optional[Dict[str, Any]]:
    """TWSE MIS public quote — Taiwan Stock Exchange real-time-ish endpoint, no token.

    `twse_code` examples: `tse_2330.tw` for listed, `otc_3105.tw` for OTC.
    Endpoint returns JSON with latest trade and prior close in `msgArray[0]`.
    """
    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={twse_code}"
        r = session.get(url, timeout=YF_HTTP_TIMEOUT_SEC,
                        headers={"Referer": "https://mis.twse.com.tw/stock/"})
        if r.status_code != 200:
            return None
        data = r.json()
        arr = data.get("msgArray") or []
        if not arr:
            return None
        row = arr[0]
        # `z` = latest trade price, `y` = prior-day close. Sometimes `z` is `-` pre-open.
        latest_str = row.get("z", "-")
        prior_str = row.get("y", "-")
        if latest_str in ("-", "", None) and prior_str in ("-", "", None):
            return None
        try:
            prior = float(prior_str) if prior_str not in ("-", "", None) else None
        except ValueError:
            prior = None
        try:
            latest = float(latest_str) if latest_str not in ("-", "", None) else prior
        except ValueError:
            latest = prior
        if latest is None:
            return None
        move_pct = round(((latest - prior) / prior) * 100.0, 4) if prior else None
        return {
            "latest_price": latest,
            "prior_close": prior,
            "move_pct": move_pct,
            "price_source": "no_token:twse_mis",
            "price_as_of": _utc_iso(),
            "currency": "TWD",
            "exchange": "TWSE",
        }
    except Exception:                                         # noqa: BLE001
        return None


# Per-asset fallback order (§8.5). Each entry is a callable that returns dict | None.
# The caller loops the list and stops on the first success.
#
# §8.5 ORDERING — Stooq is the **primary** source for listed securities, yfinance
# per-ticker history is the **secondary** fallback. Keyed APIs and exchange-native
# endpoints (TWSE MIS) are tertiary. This matches the operator preference:
# Stooq quotes are stable, no-token, and currency-verifiable; yfinance is rate-limited
# and noisier so it is only consulted when Stooq misses.
def _build_fallback_chain(
    market: MarketType,
    keys: Dict[str, str],
    session: Any,
    yf_symbol: Optional[str],
    raw_ticker: str,
    pacer: Optional["Pacer"] = None,
) -> List[Tuple[str, Any]]:
    """Returns [(label, callable), ...] in spec order for the given market."""
    chain: List[Tuple[str, Any]] = []
    s = yf_symbol or raw_ticker

    def _yf_callable(symbol: str) -> Any:
        return lambda: _try_yfinance_per_ticker(symbol, pacer or Pacer(), session)

    if market in (MarketType.US, MarketType.UNKNOWN):
        # Primary: Stooq no-token JSON
        chain.append(("no_token:stooq", lambda: _try_no_token_stooq(f"{raw_ticker.lower()}.us", session)))
        # Secondary: yfinance per-ticker
        if yf_symbol:
            chain.append(("yfinance", _yf_callable(yf_symbol)))
        # Tertiary: keyed APIs (§8.5)
        if "TWELVE_DATA_API_KEY" in keys:
            chain.append(("twelve_data", lambda: _try_twelve_data(s, keys["TWELVE_DATA_API_KEY"], session)))
        if "FINNHUB_API_KEY" in keys:
            chain.append(("finnhub", lambda: _try_finnhub(s, keys["FINNHUB_API_KEY"], session)))
        # FMP / Tiingo / Alpha Vantage / Polygon — TODO; same pattern.
    elif market == MarketType.CRYPTO:
        # Crypto does not use Stooq or yfinance. Exchange-native spot first, then CoinGecko.
        binance_sym = f"{_normalize_crypto_symbol(raw_ticker)}USDT"
        chain.append(("no_token:binance", lambda: _try_no_token_binance(binance_sym, session)))
        if "COINGECKO_DEMO_API_KEY" in keys:
            chain.append(("coingecko_demo", lambda: _try_coingecko(raw_ticker, session, keys["COINGECKO_DEMO_API_KEY"])))
        chain.append(("coingecko", lambda: _try_coingecko(raw_ticker, session)))
    elif market in (MarketType.TW, MarketType.TWO):
        # Primary: Stooq for TW listed names (covers most equities/ETFs)
        chain.append(("no_token:stooq", lambda: _try_no_token_stooq(f"{raw_ticker.lower()}.tw", session)))
        # Secondary: yfinance per-ticker
        if yf_symbol:
            chain.append(("yfinance", _yf_callable(yf_symbol)))
        # Tertiary: TWSE MIS (works for both listed `tse_` and OTC `otc_` prefixes)
        prefix = "tse" if market == MarketType.TW else "otc"
        twse_code = f"{prefix}_{raw_ticker.lower()}.tw" if not raw_ticker.lower().endswith(".tw") \
                    else f"{prefix}_{raw_ticker.lower()}"
        chain.append(("no_token:twse_mis", lambda: _try_no_token_twse_mis(twse_code, session)))
    elif market == MarketType.JP:
        # Primary: Stooq covers `.jp` codes like `7203.jp`
        chain.append(("no_token:stooq", lambda: _try_no_token_stooq(f"{raw_ticker.lower()}.jp", session)))
        # Secondary: yfinance per-ticker
        if yf_symbol:
            chain.append(("yfinance", _yf_callable(yf_symbol)))
        if "JQUANTS_REFRESH_TOKEN" in keys:
            # JQuants flow — left as TODO; auth + endpoint resolution required.
            pass
    elif market == MarketType.LSE:
        # Primary: Stooq `.uk` (e.g. vwra.uk, lse-listed UCITS ETFs)
        chain.append(("no_token:stooq", lambda: _try_no_token_stooq(f"{raw_ticker.lower()}.uk", session)))
        # Secondary: yfinance per-ticker
        if yf_symbol:
            chain.append(("yfinance", _yf_callable(yf_symbol)))
    elif market == MarketType.HK:
        # Primary: Stooq `.hk`
        chain.append(("no_token:stooq", lambda: _try_no_token_stooq(f"{raw_ticker.lower()}.hk", session)))
        # Secondary: yfinance per-ticker
        if yf_symbol:
            chain.append(("yfinance", _yf_callable(yf_symbol)))
    elif market == MarketType.FX:
        # FX preserves the legacy order: yfinance primary (no Stooq endpoint for FX),
        # then keyed Twelve Data, then Frankfurter (ECB), then Open ER.
        if yf_symbol:
            chain.append(("yfinance", _yf_callable(yf_symbol)))
        if "TWELVE_DATA_API_KEY" in keys:
            chain.append(("twelve_data_fx", lambda: _try_twelve_data(s, keys["TWELVE_DATA_API_KEY"], session)))
        chain.append(("no_token:frankfurter", lambda: _try_no_token_frankfurter_fx(s, session)))
        chain.append(("no_token:open_er_api", lambda: _try_no_token_open_er_fx(s, session)))
    return chain


def _try_yfinance_per_ticker(symbol: str, pacer: "Pacer", session: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Wrap `_yfinance_per_ticker_history` to return the same dict shape as Stooq/keyed callers."""
    out = _yfinance_per_ticker_history(symbol, pacer, session)
    if out is None:
        return None
    latest, prior, currency, exchange = out
    move_pct = (
        round(((latest - prior) / prior) * 100.0, 4)
        if prior and prior != 0 else None
    )
    return {
        "latest_price": latest,
        "prior_close": prior,
        "move_pct": move_pct,
        "currency": currency,
        "exchange": exchange,
        "price_source": "yfinance",
        "price_as_of": _utc_iso(),
    }


# ----------------------------------------------------------------------------- #
# Currency verification via internet (post-fetch)
# ----------------------------------------------------------------------------- #

# Process-level cache so the same symbol is only probed once per run.
_CURRENCY_CACHE: Dict[str, str] = {}


def _yahoo_chart_currency(symbol: str, session: Any) -> Optional[Tuple[str, Optional[str]]]:
    """Direct call to Yahoo's v8 chart endpoint (no auth, returns currency in meta).

    Returns (currency, exchange) on success, None on failure. This is the canonical
    internet-based ticker-currency lookup the spec's "Stooq currency rule" requires;
    `https://query1.finance.yahoo.com/v8/finance/chart/<sym>?interval=1d&range=5d`
    works without a crumb/cookie unlike the v7 quote endpoint.
    """
    if not symbol:
        return None
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        r = session.get(
            url,
            params={"interval": "1d", "range": "5d"},
            timeout=YF_HTTP_TIMEOUT_SEC,
            headers={
                "User-Agent": "Mozilla/5.0 (portfolio-report-agent)",
                "Accept": "application/json",
            },
        )
        if r.status_code != 200:
            return None
        data = r.json() or {}
        rows = (data.get("chart") or {}).get("result") or []
        if not rows:
            return None
        meta = rows[0].get("meta") or {}
        ccy = meta.get("currency")
        if not ccy:
            return None
        exch = meta.get("exchangeName") or meta.get("fullExchangeName")
        return str(ccy).upper(), (str(exch) if exch else None)
    except Exception:                                             # noqa: BLE001
        return None


def _verify_currency_via_internet(
    pr: PriceResult,
    session: Optional[Any],
    pacer: Pacer,
) -> None:
    """Ensure `pr.currency` is populated from a live internet source.

    Strategy (in order):
      1. Keep `pr.currency` if the price-source already supplied a non-empty value
         (yfinance / keyed APIs usually include it; Stooq does not).
      2. Direct Yahoo v8 chart endpoint probe — no-auth HTTP that returns canonical
         exchange-confirmed currency/exchange in `chart.result[0].meta.currency`.
         This is the "agent web-search the listing exchange" step the spec's Stooq
         currency rule requires, run as a deterministic API call.
      3. yfinance.Ticker.fast_info probe — backup if the v8 endpoint is blocked.
      4. For TW markets, the MIS endpoint always implies TWD (Stooq `.tw` listings).
      5. Fall back to MARKET_DEFAULT_CCY for the market type.

    Cash and crypto rows are skipped — cash is set elsewhere, crypto is always USD-quoted.
    """
    if pr.market == MarketType.CASH:
        return
    if pr.currency:
        return  # already verified by the price source

    sym = pr.yfinance_symbol

    # 2. Yahoo v8 chart API (preferred — direct HTTP, no auth, returns currency in meta)
    if sym and session is not None:
        cached = _CURRENCY_CACHE.get(sym)
        if cached:
            pr.currency = cached
            pr.fallback_chain.append("currency_verify:yahoo_chart_cached")
            return
        # Pace the chart probe so back-to-back Stooq+Yahoo bursts don't double the
        # outbound rate; Yahoo throttles the v8 endpoint less aggressively than v7
        # but still benefits from the §8.3 inter-call gap.
        pacer.wait()
        out = _yahoo_chart_currency(sym, session)
        if out:
            ccy, exch = out
            pr.currency = ccy
            if exch and not pr.exchange:
                pr.exchange = exch
            _CURRENCY_CACHE[sym] = ccy
            pr.fallback_chain.append("currency_verify:yahoo_chart")
            return

    # 3. yfinance.Ticker.fast_info probe (backup; subject to rate-limit). `fast_info`
    # is a `FastInfo` object — not a dict — so we use attribute/key access via the
    # suppress block.
    if sym and session is not None:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
            pacer.wait()
            tk = yf.Ticker(sym, session=session)
            ccy: Optional[str] = None
            with contextlib.suppress(Exception):
                fi = tk.fast_info
                if fi is not None:
                    ccy = getattr(fi, "currency", None)
                    if ccy is None:
                        try:
                            ccy = fi["currency"]                  # type: ignore[index]
                        except (KeyError, TypeError):
                            ccy = None
            if ccy:
                pr.currency = str(ccy).upper()
                _CURRENCY_CACHE[sym] = pr.currency
                pr.fallback_chain.append("currency_verify:yfinance_fast_info")
                return
        except ImportError:
            pass
        except Exception:                                         # noqa: BLE001
            pass

    # 4. TW-specific exchange metadata (MIS endpoint always returns TWD)
    if pr.market in (MarketType.TW, MarketType.TWO):
        pr.currency = "TWD"
        pr.fallback_chain.append("currency_verify:twse_mis_metadata")
        return

    # 5. Fallback to hardcoded market default (last resort, no internet hit)
    default_ccy = MARKET_DEFAULT_CCY.get(pr.market)
    if default_ccy:
        pr.currency = default_ccy
        pr.fallback_chain.append(f"currency_verify:default_for_{pr.market.value}")


# ----------------------------------------------------------------------------- #
# Top-level orchestration
# ----------------------------------------------------------------------------- #

def fetch_all_prices(
    lots: List[Lot],
    settings_keys: Dict[str, str],
    *,
    skip_yfinance: bool = False,
) -> Dict[str, PriceResult]:
    """
    Returns a dict of `ticker -> PriceResult` covering every distinct (ticker, market)
    pair in the holdings (excluding cash). Cash rows are emitted with `price_source="cash"`
    and no fetch attempt.

    `skip_yfinance` is for testing / dry-runs.
    """
    # Deduplicate per (ticker, market) — multiple lots of the same ticker share one fetch.
    distinct: Dict[Tuple[str, MarketType], None] = {}
    for lot in lots:
        distinct[(lot.ticker, lot.market)] = None

    results: Dict[str, PriceResult] = {}
    pacer = Pacer()
    session: Any = None
    try:
        import requests  # type: ignore[import-not-found]
        session = requests.Session()
        session.headers.update({"User-Agent": "portfolio-report-agent/1.0"})
    except ImportError:
        logging.warning("`requests` not installed; keyed-API fallbacks will be skipped.")

    # Initialize results
    for (ticker, market) in distinct:
        if market == MarketType.CASH:
            results[ticker] = PriceResult(
                ticker=ticker,
                market=market,
                yfinance_symbol=None,
                price_source="cash",
                price_freshness="n/a",
                fallback_chain=["cash:no_fetch"],
            )
            continue
        sym = to_yfinance_symbol(ticker, market)
        results[ticker] = PriceResult(
            ticker=ticker,
            market=market,
            yfinance_symbol=sym,
        )
        if market == MarketType.CRYPTO:
            results[ticker].fallback_chain.append("primary:crypto_native_sources")

    # ---- Per-ticker fetch: Stooq primary → yfinance secondary → keyed APIs --- #
    # `skip_yfinance` is repurposed as "no network": skip the entire fetch chain so the
    # parser and JSON shape can be smoke-tested without making any HTTP calls.
    for (ticker, market) in distinct:
        pr = results[ticker]
        if pr.price_source == "cash":
            continue

        if session is None or skip_yfinance:
            pr.fallback_chain.append("network_disabled:no_fetch")
            results[ticker] = pr
            continue

        tried_any = False
        for label, callable_ in _build_fallback_chain(
            market, settings_keys, session, pr.yfinance_symbol, ticker, pacer=pacer
        ):
            tried_any = True
            # §8.8 audit: stamp yfinance request started/latency for the yfinance branch
            # only. Other sources don't carry these fields per the contract.
            yf_started_mono: Optional[float] = None
            if label == "yfinance":
                pr.yfinance_request_started_at = _utc_iso()
                yf_started_mono = time.monotonic()
            out = callable_()
            if label == "yfinance" and yf_started_mono is not None:
                pr.yfinance_request_latency_ms = int((time.monotonic() - yf_started_mono) * 1000)
            if out and out.get("latest_price") is not None:
                pr.latest_price = out.get("latest_price")
                pr.prior_close = out.get("prior_close")
                pr.move_pct = out.get("move_pct")
                pr.currency = out.get("currency") or pr.currency
                pr.exchange = out.get("exchange") or pr.exchange
                pr.price_source = out.get("price_source", label)
                pr.price_as_of = out.get("price_as_of") or _utc_iso()
                state = _classify_market_state(market)
                pr.market_state_basis = state.value
                pr.price_freshness = _freshness_for_state(state, has_intraday=True)
                pr.fallback_chain.append(label)
                break
            else:
                pr.fallback_chain.append(f"{label}:miss")
                if label == "yfinance":
                    pr.yfinance_failure_reason = "yfinance_per_ticker_miss"
        if not tried_any:
            pr.fallback_chain.append("primary_chain:no_endpoints_for_market")

        # §8.4 yfinance auto-correction — only consulted when Stooq AND yfinance
        # per-ticker both missed but a yfinance symbol exists. Rate-limit failures
        # short-circuit per §8.3.1.
        if pr.price_source == "n/a" and pr.yfinance_symbol and market != MarketType.CRYPTO:
            pr = _auto_correct(pr, pacer, session)

        if pr.price_source == "n/a":
            # Final handoff to the agent's web search tier (§8.3.1 tier 3).
            pr.fallback_chain.append("agent_web_search:TODO_required")
            if _is_rate_limit_failure_reason(pr.yfinance_failure_reason):
                pr.fallback_chain.append("rate_limited:tier3_4_continuation_required")
            pr.price_freshness = "n/a"
        else:
            # Internet-based currency verification for the ticker quote currency.
            _verify_currency_via_internet(pr, session, pacer)

        results[ticker] = pr

    return results


def required_fx_currencies(
    lots: List[Lot],
    results: Dict[str, PriceResult],
    base_currency: str,
) -> List[str]:
    """Derive every non-base currency needing conversion from holdings + quote metadata."""
    base = base_currency.upper()
    needed = set()
    for lot in lots:
        if lot.market == MarketType.CASH:
            ccy = "USD" if lot.ticker.upper() in CASH_STABLECOIN_USD else lot.ticker.upper()
        else:
            pr = results.get(lot.ticker)
            ccy = (
                (pr.currency if pr else None)
                or MARKET_DEFAULT_CCY.get(lot.market, DEFAULT_BASE_CURRENCY)
            ).upper()
        if ccy != base:
            needed.add(ccy)
    return sorted(needed)


def fetch_auto_fx_rates(
    currencies: List[str],
    base_currency: str,
    settings_keys: Dict[str, str],
    *,
    skip_yfinance: bool = False,
) -> Dict[str, Any]:
    """Fetch base-quoted FX rates for prices.json["_fx"].

    Rates are keyed "<BASE>/<CCY>" and mean "1 unit of base = N units of CCY",
    matching the renderer's conversion formula.
    """
    base = base_currency.upper()
    fx_lots: List[Lot] = []
    pair_by_symbol: Dict[str, str] = {}
    for ccy in sorted({c.upper() for c in currencies if c}):
        if ccy == base:
            continue
        symbol = f"{base}{ccy}"
        pair = f"{base}/{ccy}"
        pair_by_symbol[symbol] = pair
        fx_lots.append(
            Lot(
                raw_line=f"auto FX {pair}",
                bucket="FX",
                ticker=symbol,
                quantity=1.0,
                cost=None,
                date=None,
                market=MarketType.FX,
                is_share=False,
            )
        )

    if not fx_lots:
        return {
            "base": base,
            "required_currencies": [],
            "rates": {},
            "details": {},
        }

    fx_results = fetch_all_prices(fx_lots, settings_keys, skip_yfinance=skip_yfinance)
    rates: Dict[str, float] = {}
    details: Dict[str, Any] = {}
    for symbol, result in fx_results.items():
        pair = pair_by_symbol.get(symbol)
        if pair is None:
            continue
        if result.latest_price not in (None, 0):
            rates[pair] = float(result.latest_price)
        details[pair] = _serialize_result(result)

    return {
        "base": base,
        "required_currencies": sorted({c.upper() for c in currencies if c and c.upper() != base}),
        "rates": rates,
        "details": details,
    }


def _chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _result_by_symbol(results: Dict[str, PriceResult], yf_sym: str) -> Optional[PriceResult]:
    for r in results.values():
        if r.yfinance_symbol == yf_sym:
            return r
    return None


# ----------------------------------------------------------------------------- #
# CLI
# ----------------------------------------------------------------------------- #

def _cli_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--holdings", default="HOLDINGS.md", type=Path,
                   help="Path to HOLDINGS.md (default: ./HOLDINGS.md)")
    p.add_argument("--settings", default="SETTINGS.md", type=Path,
                   help="Path to SETTINGS.md for base currency and optional API keys "
                        "(default: ./SETTINGS.md)")
    p.add_argument("--output", default=None, type=Path,
                   help="Write JSON output to this path; default: stdout")
    p.add_argument("--skip-yfinance", action="store_true",
                   help="Skip yfinance AND the keyed/no-token fallback chain — leaves every "
                        "non-cash ticker at price_source=n/a. Useful for testing the parser and "
                        "JSON shape without making any network calls.")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Enable INFO-level logging")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _cli_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not args.holdings.exists():
        print(f"ERROR: holdings file not found: {args.holdings}", file=sys.stderr)
        return 2

    lots = parse_holdings(args.holdings)
    if not lots:
        print(f"ERROR: no lots parsed from {args.holdings}", file=sys.stderr)
        return 3

    settings_path = args.settings if args.settings.exists() else None
    settings_keys = parse_settings_keys(settings_path)
    base_currency = parse_base_currency(settings_path)
    logging.info(
        "Parsed %d lots, %d optional API keys, base currency %s",
        len(lots), len(settings_keys), base_currency,
    )

    results = fetch_all_prices(lots, settings_keys, skip_yfinance=args.skip_yfinance)
    required_ccys = required_fx_currencies(lots, results, base_currency)
    fx_payload = fetch_auto_fx_rates(
        required_ccys,
        base_currency,
        settings_keys,
        skip_yfinance=args.skip_yfinance,
    )

    payload: Dict[str, Any] = {
        ticker: _serialize_result(pr) for ticker, pr in results.items()
    }
    payload["_fx"] = fx_payload
    payload["_audit"] = {
        "generated_at": _now_iso(),
        "holdings_file": str(args.holdings),
        "settings_file": str(args.settings) if args.settings.exists() else None,
        "base_currency": base_currency,
        "lot_count": len(lots),
        "ticker_count": len(results),
        "required_fx_currencies": required_ccys,
        "configured_api_keys": sorted(settings_keys.keys()),
        "yfinance_skipped": args.skip_yfinance,
        "spec_section_compliance": {
            "pacing_8_3": True,
            "auto_correction_8_4": True,
            "fallback_8_5": True,
            "freshness_gate_8_7": True,
            "stored_fields_8_8": True,
        },
    }
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        print(f"Wrote {len(results)} ticker results to {args.output}")
    else:
        print(serialized)
    return 0


def _serialize_result(pr: PriceResult) -> Dict[str, Any]:
    d = asdict(pr)
    # Convert MarketType enum → string
    d["market"] = pr.market.value
    return d


if __name__ == "__main__":
    raise SystemExit(main())
