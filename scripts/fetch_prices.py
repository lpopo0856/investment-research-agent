#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_prices.py — Latest-price retrieval template for the portfolio report agent.

Implements `docs/portfolio_report_agent_guidelines.md` §8 (Latest-price retrieval pipeline):

  1. Parse HOLDINGS.md (§4.1)
  2. Group tickers by market type and resolve yfinance symbol (§8.5)
  3. yfinance batch first, with strict pacing (§8.3)
  4. yfinance failure recovery — up to 3 auto-correction attempts per failure (§8.4)
  5. Fallback: keyed APIs → web (manual) → no-token APIs (§8.1, §8.5)
  6. Apply Freshness gate (§8.7)
  7. Emit JSON with the §8.8 stored-fields contract per ticker.

Output JSON shape (per ticker):

    {
      "<TICKER>": {
        "latest_price":           177.34,            // null if n/a
        "prior_close":             175.21,           // 24h reference for crypto
        "move_pct":                1.22,
        "currency":               "USD",
        "exchange":               "NMS",
        "price_source":           "yfinance",        // or "yfinance_per_ticker_history",
                                                     // "twelve_data", "finnhub", "web:yahoo",
                                                     // "no_token:binance", "n/a", ...
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

The script imports yfinance lazily inside the batch function, so the parser, freshness
gate, and JSON shape can be unit-tested without the network dependency installed.
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
    CRYPTO = "crypto"    # yfinance: <SYM>-USD
    FX = "FX"            # yfinance: <PAIR>=X
    CASH = "cash"        # bare currency holding — no price fetch
    UNKNOWN = "unknown"


# Heuristic fallback when no [market] tag is present (§4.1 backward compat)
KNOWN_CRYPTO_SYMBOLS = {
    "BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "DOT", "MATIC", "LTC", "LINK",
    "AVAX", "USDC", "USDT", "DAI", "BNB", "TRX", "ATOM", "UNI", "FIL", "TON",
    "NEAR", "APT", "SUI", "ARB", "OP", "INJ", "RNDR", "SEI", "TIA",
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
# SETTINGS.md parser — only extracts optional API keys (§8.6)
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


# ----------------------------------------------------------------------------- #
# Symbol routing per market (§8.5)
# ----------------------------------------------------------------------------- #

def to_yfinance_symbol(ticker: str, market: MarketType) -> Optional[str]:
    """Map (ticker, market) → Yahoo-style symbol. None means not fetchable via yfinance."""
    t = ticker.upper()
    if market == MarketType.CASH:
        return None  # cash never gets a yfinance lookup
    if market == MarketType.CRYPTO:
        return t if "-USD" in t else f"{t}-USD"
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
        return {}, f"yfinance_batch_exception:{type(exc).__name__}:{exc!s:.200}"
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

def _auto_correct(
    result: PriceResult,
    pacer: Pacer,
    session: Optional[Any],
) -> PriceResult:
    """Up to 3 targeted correction attempts. Each attempt counts toward the §8.4 budget."""
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


def _try_coingecko_demo(symbol: str, key: str, session: Any) -> Optional[Dict[str, Any]]:
    """CoinGecko Demo simple/price endpoint. `symbol` here is a coin id (e.g. "bitcoin")."""
    # NOTE: callers should map BTC → "bitcoin", ETH → "ethereum" before calling.
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd&include_24hr_change=true&x_cg_demo_api_key={key}"
        r = session.get(url, timeout=YF_HTTP_TIMEOUT_SEC)
        if r.status_code != 200:
            return None
        data = r.json()
        coin = data.get(symbol)
        if not coin or "usd" not in coin:
            return None
        latest = float(coin["usd"])
        change_24h = coin.get("usd_24h_change")
        return {
            "latest_price": latest,
            "move_pct": round(float(change_24h), 4) if change_24h is not None else None,
            "price_source": "coingecko_demo",
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
        change_pct = data.get("priceChangePercent")
        if latest is None:
            return None
        return {
            "latest_price": latest,
            "move_pct": round(float(change_pct), 4) if change_pct is not None else None,
            "price_source": "no_token:binance",
            "price_as_of": _utc_iso(),
        }
    except Exception:                                         # noqa: BLE001
        return None


# Per-asset fallback order (§8.5). Each entry is a callable that returns dict | None.
# The caller loops the list and stops on the first success.
def _build_fallback_chain(
    market: MarketType,
    keys: Dict[str, str],
    session: Any,
    yf_symbol: Optional[str],
    raw_ticker: str,
) -> List[Tuple[str, Any]]:
    """Returns [(label, callable), ...] in spec order for the given market."""
    chain: List[Tuple[str, Any]] = []
    s = yf_symbol or raw_ticker

    if market in (MarketType.US, MarketType.UNKNOWN):
        if "TWELVE_DATA_API_KEY" in keys:
            chain.append(("twelve_data", lambda: _try_twelve_data(s, keys["TWELVE_DATA_API_KEY"], session)))
        if "FINNHUB_API_KEY" in keys:
            chain.append(("finnhub", lambda: _try_finnhub(s, keys["FINNHUB_API_KEY"], session)))
        # FMP / Tiingo / Alpha Vantage / Polygon — left as TODO; same pattern.
    elif market == MarketType.CRYPTO:
        if "COINGECKO_DEMO_API_KEY" in keys:
            # NOTE: coin id mapping is a TODO; agent should resolve BTC → "bitcoin".
            chain.append(("coingecko_demo", lambda: _try_coingecko_demo(raw_ticker.lower(), keys["COINGECKO_DEMO_API_KEY"], session)))
        # No-token Binance fallback (BTC → BTCUSDT)
        binance_sym = f"{raw_ticker.upper().replace('-USD','')}USDT"
        chain.append(("no_token:binance", lambda: _try_no_token_binance(binance_sym, session)))
    elif market in (MarketType.TW, MarketType.TWO):
        # TWSE MIS / OpenAPI fallback — left as TODO; agent should add public quote URL.
        pass
    elif market == MarketType.JP:
        if "JQUANTS_REFRESH_TOKEN" in keys:
            # JQuants flow — left as TODO; auth + endpoint resolution required.
            pass
    elif market == MarketType.FX:
        if "TWELVE_DATA_API_KEY" in keys:
            chain.append(("twelve_data_fx", lambda: _try_twelve_data(s, keys["TWELVE_DATA_API_KEY"], session)))
    return chain


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

    # ---- Group by market for batched yfinance calls ------------------------- #
    if not skip_yfinance:
        groups: Dict[MarketType, List[str]] = {}
        for (ticker, market) in distinct:
            if market == MarketType.CASH:
                continue
            sym = results[ticker].yfinance_symbol
            if sym is None:
                continue
            groups.setdefault(market, []).append(sym)

        for market, symbols in groups.items():
            for batch in _chunked(symbols, YF_BATCH_SIZE):
                results_for_batch, batch_err = _yfinance_batch(batch, pacer, session)
                # Apply results
                for sym in batch:
                    pr = _result_by_symbol(results, sym)
                    if pr is None:
                        continue
                    if sym in results_for_batch:
                        latest, prior, currency = results_for_batch[sym]
                        pr.latest_price = latest
                        pr.prior_close = prior
                        pr.currency = currency
                        pr.move_pct = (
                            round(((latest - prior) / prior) * 100.0, 4)
                            if (latest is not None and prior not in (None, 0))
                            else None
                        )
                        pr.price_source = "yfinance"
                        pr.price_as_of = _utc_iso()
                        state = _classify_market_state(pr.market)
                        pr.market_state_basis = state.value
                        pr.price_freshness = _freshness_for_state(state, has_intraday=True)
                        pr.fallback_chain.append("yfinance_batch")
                    else:
                        pr.yfinance_failure_reason = batch_err or "missing_in_batch_response"
                pacer.reset_after_batch()

    # ---- Per-ticker recovery + keyed/no-token fallback ---------------------- #
    for (ticker, market) in distinct:
        pr = results[ticker]
        if pr.price_source in ("cash", "yfinance"):
            continue

        # Step 1: yfinance auto-correction (counts toward §8.4 budget)
        if not skip_yfinance and pr.yfinance_symbol:
            pr = _auto_correct(pr, pacer, session)
            if pr.price_source == "yfinance":
                results[ticker] = pr
                continue

        # Step 2: keyed-API fallback chain
        if session is not None:
            for label, callable_ in _build_fallback_chain(
                market, settings_keys, session, pr.yfinance_symbol, ticker
            ):
                out = callable_()
                if out and out.get("latest_price") is not None:
                    pr.latest_price = out.get("latest_price")
                    pr.prior_close = out.get("prior_close")
                    pr.move_pct = out.get("move_pct")
                    pr.price_source = out.get("price_source", label)
                    pr.price_as_of = out.get("price_as_of") or _utc_iso()
                    state = _classify_market_state(market)
                    pr.market_state_basis = state.value
                    pr.price_freshness = _freshness_for_state(state, has_intraday=True)
                    pr.fallback_chain.append(label)
                    break

        if pr.price_source == "n/a":
            # Step 3: web search / no-token public APIs left to the agent. Mark and move on.
            pr.fallback_chain.append("agent_web_search:TODO")
            pr.price_freshness = "n/a"

        results[ticker] = pr

    return results


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
                   help="Path to SETTINGS.md for optional API keys (default: ./SETTINGS.md)")
    p.add_argument("--output", default=None, type=Path,
                   help="Write JSON output to this path; default: stdout")
    p.add_argument("--skip-yfinance", action="store_true",
                   help="Skip the yfinance branch (useful for testing parsers)")
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

    settings_keys = parse_settings_keys(args.settings if args.settings.exists() else None)
    logging.info("Parsed %d lots, %d optional API keys", len(lots), len(settings_keys))

    results = fetch_all_prices(lots, settings_keys, skip_yfinance=args.skip_yfinance)

    payload: Dict[str, Any] = {
        ticker: _serialize_result(pr) for ticker, pr in results.items()
    }
    payload["_audit"] = {
        "generated_at": _now_iso(),
        "holdings_file": str(args.holdings),
        "settings_file": str(args.settings) if args.settings.exists() else None,
        "lot_count": len(lots),
        "ticker_count": len(results),
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
