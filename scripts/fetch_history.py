#!/usr/bin/env python3
"""
Historical daily close retrieval for the profit panel.

Companion to scripts/fetch_prices.py. Reads projected positions/cash from
transactions.db, fetches up to N days of daily closes for every non-cash
position and every required FX pair, and writes the result to a JSON file.
The output is suitable for merging into prices.json (or referencing alongside
it) as `_history` and `_fx_history`.

Sourcing
--------
- Listed equities / ETFs: Stooq CSV, direct Yahoo chart API, then yfinance.
- Crypto: Binance klines, Coinbase Exchange candles, CoinGecko market chart,
  direct Yahoo chart API, then yfinance.
- FX pairs: direct Yahoo chart API, Frankfurter time series, then yfinance.

Output schema
-------------
    {
      "_history": {
        "NVDA":   [{"date": "2026-04-29", "close": 215.5}, ...],
        "2330.TW":[{"date": "2026-04-29", "close": 2300}, ...],
        ...
      },
      "_fx_history": {
        "USD/TWD": [{"date": "2026-04-29", "rate": 32.5}, ...],
        ...
      },
      "_history_meta": {
        "as_of":          "2026-04-30T03:35:00Z",
        "lookback_days":  400,
        "base_currency":  "USD",
        "tickers_ok":     ["NVDA", ...],
        "tickers_failed": [{"ticker": "ABC", "reason": "no data"}],
        "fx_ok":          ["USD/TWD", ...],
        "fx_failed":      []
      }
    }

CLI
---
    python scripts/fetch_history.py \\
        --settings SETTINGS.md \\
        --output prices_history.json [--lookback-days 400] [--merge-into prices.json]
        [--cache market_data_cache.db] [--no-cache]

By default the script uses `market_data_cache.db` as a cache-first store for
daily closes and FX rates. `transactions.db` remains the canonical user-action
ledger; the market-data cache is derived and disposable.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import random
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Match scripts/fetch_prices.py pacing rules so we don't trip yfinance rate limits.
_YF_MIN_GAP = (1.5, 2.5)
_YF_LAST_CALL_AT: Dict[str, float] = {"t": 0.0}


def _yf_pace() -> None:
    elapsed = time.monotonic() - _YF_LAST_CALL_AT["t"]
    gap = random.uniform(*_YF_MIN_GAP)
    if elapsed < gap:
        time.sleep(gap - elapsed)
    _YF_LAST_CALL_AT["t"] = time.monotonic()

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from fetch_prices import (  # type: ignore[import-not-found]
    COINGECKO_ID_MAP,
    KNOWN_CRYPTO_SYMBOLS,
    Lot,
    MarketType,
    parse_base_currency,
    to_yfinance_symbol,
)


def _utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _requests_get_json(url: str, *, params: Optional[Dict[str, Any]] = None, timeout: int = 12) -> Optional[Any]:
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        r = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 investment-report-history-fetcher"},
        )
        if r.status_code != 200:
            logging.info("history source HTTP %s for %s", r.status_code, url)
            return None
        return r.json()
    except Exception as e:
        logging.info("history source failed for %s: %s", url, e)
        return None


def _date_to_unix(d: _dt.date) -> int:
    return int(_dt.datetime.combine(d, _dt.time.min, tzinfo=_dt.timezone.utc).timestamp())


def _dedupe_rows(rows: List[Dict[str, Any]], value_key: str = "close") -> List[Dict[str, Any]]:
    by_date: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        date = str(row.get("date") or "")
        if not date:
            continue
        try:
            value = float(row.get(value_key))
        except (TypeError, ValueError):
            continue
        by_date[date] = {"date": date, value_key: round(value, 6)}
    return [by_date[d] for d in sorted(by_date)]


# --------------------------------------------------------------------------- #
# Market-data cache
# --------------------------------------------------------------------------- #

DEFAULT_CACHE_PATH = Path("market_data_cache.db")


def cache_init(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                ticker     TEXT NOT NULL,
                market     TEXT NOT NULL,
                date       TEXT NOT NULL,
                close      REAL NOT NULL,
                currency   TEXT,
                source     TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (ticker, market, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fx_history (
                base       TEXT NOT NULL,
                quote      TEXT NOT NULL,
                date       TEXT NOT NULL,
                rate       REAL NOT NULL,
                source     TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (base, quote, date)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_lookup ON price_history(ticker, market, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fx_history_lookup ON fx_history(base, quote, date)")


def _cache_cutoff(lookback_days: int) -> str:
    return (_dt.date.today() - _dt.timedelta(days=lookback_days)).isoformat()


def _cache_rows_fresh(
    rows: List[Dict[str, Any]],
    lookback_days: int,
    *,
    max_stale_days: int,
) -> bool:
    if not rows:
        return False
    dates = sorted(str(r.get("date")) for r in rows if r.get("date"))
    if not dates:
        return False
    start = _dt.date.today() - _dt.timedelta(days=lookback_days)
    latest_ok = _dt.date.today() - _dt.timedelta(days=max_stale_days)
    try:
        first = _dt.date.fromisoformat(dates[0])
        latest = _dt.date.fromisoformat(dates[-1])
    except ValueError:
        return False
    # Allow a few non-trading days at the beginning of the requested range.
    return first <= start + _dt.timedelta(days=7) and latest >= latest_ok


def cache_get_price_rows(path: Path, ticker: str, market: MarketType, lookback_days: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    cutoff = _cache_cutoff(lookback_days)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT date, close
            FROM price_history
            WHERE ticker = ? AND market = ? AND date >= ?
            ORDER BY date ASC
            """,
            (ticker, market.value, cutoff),
        ).fetchall()
    return [{"date": r["date"], "close": round(float(r["close"]), 6)} for r in rows]


def cache_put_price_rows(
    path: Path,
    ticker: str,
    market: MarketType,
    rows: List[Dict[str, Any]],
    *,
    source: str,
    currency: Optional[str] = None,
) -> None:
    if not rows:
        return
    cache_init(path)
    fetched_at = _utc_iso()
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO price_history (ticker, market, date, close, currency, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, market, date) DO UPDATE SET
                close = excluded.close,
                currency = COALESCE(excluded.currency, price_history.currency),
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            [
                (ticker, market.value, r["date"], float(r["close"]), currency, source, fetched_at)
                for r in rows
                if r.get("date") and r.get("close") is not None
            ],
        )


def cache_get_fx_rows(path: Path, pair: str, lookback_days: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    base, quote = pair.split("/")
    cutoff = _cache_cutoff(lookback_days)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT date, rate
            FROM fx_history
            WHERE base = ? AND quote = ? AND date >= ?
            ORDER BY date ASC
            """,
            (base, quote, cutoff),
        ).fetchall()
    return [{"date": r["date"], "rate": round(float(r["rate"]), 8)} for r in rows]


def cache_put_fx_rows(path: Path, pair: str, rows: List[Dict[str, Any]], *, source: str) -> None:
    if not rows:
        return
    base, quote = pair.split("/")
    cache_init(path)
    fetched_at = _utc_iso()
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO fx_history (base, quote, date, rate, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(base, quote, date) DO UPDATE SET
                rate = excluded.rate,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            [
                (base, quote, r["date"], float(r["rate"]), source, fetched_at)
                for r in rows
                if r.get("date") and r.get("rate") is not None
            ],
        )


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #

def _yahoo_chart_history(symbol: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Direct Yahoo chart API fallback. Returns [{date, close}], or [] on failure."""
    start = _dt.date.today() - _dt.timedelta(days=lookback_days + 7)
    end = _dt.date.today() + _dt.timedelta(days=1)
    payload = _requests_get_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={
            "period1": _date_to_unix(start),
            "period2": _date_to_unix(end),
            "interval": "1d",
            "events": "history",
        },
    )
    try:
        result = (((payload or {}).get("chart") or {}).get("result") or [])[0]
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
    except (AttributeError, IndexError, TypeError):
        return []
    rows: List[Dict[str, Any]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        try:
            date = _dt.datetime.fromtimestamp(int(ts), tz=_dt.timezone.utc).date().isoformat()
            rows.append({"date": date, "close": float(close)})
        except (TypeError, ValueError, OSError):
            continue
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback_days)).isoformat()
    return [r for r in _dedupe_rows(rows) if r["date"] >= cutoff]

def _yf_history(symbol: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Return [{date, close}] from yfinance, or [] on failure."""
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError:
        return []
    period = _yf_period_for(lookback_days)
    _yf_pace()
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period=period, interval="1d", auto_adjust=False, timeout=15)
    except Exception as e:
        logging.warning("yfinance history failed for %s: %s", symbol, e)
        return []
    if df is None or df.empty:
        return []
    out: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        date = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        close = row.get("Close")
        if close is None:
            continue
        try:
            close_f = float(close)
        except (TypeError, ValueError):
            continue
        out.append({"date": date, "close": round(close_f, 6)})
    return out


def _yf_period_for(days: int) -> str:
    if days <= 5:
        return "5d"
    if days <= 30:
        return "1mo"
    if days <= 90:
        return "3mo"
    if days <= 180:
        return "6mo"
    if days <= 365:
        return "1y"
    if days <= 730:
        return "2y"
    return "5y"


def _stooq_history(stooq_symbol: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Stooq daily CSV: https://stooq.com/q/d/l/?s=<sym>&i=d"""
    try:
        import requests  # type: ignore[import-not-found]
    except ImportError:
        return []
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    try:
        r = requests.get(url, timeout=12)
        if r.status_code != 200 or not r.text:
            return []
    except Exception as e:
        logging.warning("stooq history failed for %s: %s", stooq_symbol, e)
        return []
    lines = r.text.strip().splitlines()
    if len(lines) < 2:
        return []
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback_days)).isoformat()
    out: List[Dict[str, Any]] = []
    headers = [h.strip().lower() for h in lines[0].split(",")]
    try:
        date_idx = headers.index("date")
        close_idx = headers.index("close")
    except ValueError:
        return []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= max(date_idx, close_idx):
            continue
        date = parts[date_idx].strip()
        if date < cutoff:
            continue
        try:
            close = float(parts[close_idx])
        except ValueError:
            continue
        out.append({"date": date, "close": round(close, 6)})
    return out


def _binance_klines_history(ticker: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Binance spot daily klines for crypto symbols quoted in USDT."""
    symbol = f"{ticker.upper()}USDT"
    limit = min(max(lookback_days + 10, 1), 1000)
    payload = _requests_get_json(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": symbol, "interval": "1d", "limit": limit},
    )
    if not isinstance(payload, list):
        return []
    rows: List[Dict[str, Any]] = []
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback_days)).isoformat()
    for row in payload:
        try:
            date = _dt.datetime.fromtimestamp(int(row[0]) / 1000, tz=_dt.timezone.utc).date().isoformat()
            close = float(row[4])
        except (TypeError, ValueError, IndexError, OSError):
            continue
        if date >= cutoff:
            rows.append({"date": date, "close": close})
    return _dedupe_rows(rows)


def _coinbase_candles_history(ticker: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Coinbase Exchange public candles. Max 300 daily candles per request."""
    product_id = f"{ticker.upper()}-USD"
    start = _dt.datetime.combine(
        _dt.date.today() - _dt.timedelta(days=lookback_days + 3),
        _dt.time.min,
        tzinfo=_dt.timezone.utc,
    )
    end = _dt.datetime.combine(_dt.date.today() + _dt.timedelta(days=1), _dt.time.min, tzinfo=_dt.timezone.utc)
    rows: List[Dict[str, Any]] = []
    cursor = start
    step = _dt.timedelta(days=299)
    while cursor < end:
        chunk_end = min(cursor + step, end)
        payload = _requests_get_json(
            f"https://api.exchange.coinbase.com/products/{product_id}/candles",
            params={
                "granularity": 86400,
                "start": cursor.isoformat().replace("+00:00", "Z"),
                "end": chunk_end.isoformat().replace("+00:00", "Z"),
            },
        )
        if isinstance(payload, list):
            for row in payload:
                try:
                    date = _dt.datetime.fromtimestamp(int(row[0]), tz=_dt.timezone.utc).date().isoformat()
                    close = float(row[4])
                except (TypeError, ValueError, IndexError, OSError):
                    continue
                rows.append({"date": date, "close": close})
        # Allow one boundary overlap between chunks; `_dedupe_rows` removes
        # duplicate dates and avoids skipping a candle when an endpoint treats
        # the end timestamp as exclusive.
        cursor = chunk_end
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback_days)).isoformat()
    return [r for r in _dedupe_rows(rows) if r["date"] >= cutoff]


def _coingecko_market_chart_history(ticker: str, lookback_days: int) -> List[Dict[str, Any]]:
    coin_id = COINGECKO_ID_MAP.get(ticker.upper())
    if not coin_id:
        return []
    payload = _requests_get_json(
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
        params={"vs_currency": "usd", "days": str(max(lookback_days + 3, 1)), "interval": "daily"},
    )
    prices = (payload or {}).get("prices") if isinstance(payload, dict) else None
    if not isinstance(prices, list):
        return []
    rows: List[Dict[str, Any]] = []
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback_days)).isoformat()
    for item in prices:
        try:
            date = _dt.datetime.fromtimestamp(int(item[0]) / 1000, tz=_dt.timezone.utc).date().isoformat()
            close = float(item[1])
        except (TypeError, ValueError, IndexError, OSError):
            continue
        if date >= cutoff:
            rows.append({"date": date, "close": close})
    return _dedupe_rows(rows)


def _stooq_symbol_for(ticker: str, market: MarketType) -> Optional[str]:
    """Best-effort Stooq symbol mapping (matches fetch_prices.py routing)."""
    t = ticker.upper()
    if market == MarketType.US:
        return f"{t.replace('.', '-')}.us"
    if market == MarketType.TW:
        if t.endswith(".TW"):
            t = t[:-3]
        return f"{t}.tw"
    if market == MarketType.TWO:
        if t.endswith(".TWO"):
            t = t[:-4]
        return f"{t}.tw"  # Stooq uses .tw for TPEx too in many cases; best-effort
    if market == MarketType.JP:
        if t.endswith(".T"):
            t = t[:-2]
        return f"{t}.jp"
    if market == MarketType.HK:
        if t.endswith(".HK"):
            t = t[:-3]
        return f"{t}.hk"
    if market == MarketType.LSE:
        if t.endswith(".L"):
            t = t[:-2]
        return f"{t}.uk"
    if market == MarketType.CRYPTO:
        # Stooq has a few crypto symbols, but coverage is uneven; skip.
        return None
    if market == MarketType.FX:
        return None
    return None


def _crypto_yf_symbol(ticker: str) -> Optional[str]:
    t = ticker.upper()
    if t in KNOWN_CRYPTO_SYMBOLS:
        return f"{t}-USD"
    return None


def fetch_ticker_history(
    ticker: str,
    market: MarketType,
    lookback_days: int,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Return (rows, failure_reason). Empty rows + None reason means OK with no data."""
    if market == MarketType.CASH:
        return [], None

    failures: List[str] = []
    if market == MarketType.CRYPTO:
        for name, fn in (
            ("binance_klines", lambda: _binance_klines_history(ticker, lookback_days)),
            ("coinbase_candles", lambda: _coinbase_candles_history(ticker, lookback_days)),
            ("coingecko_market_chart", lambda: _coingecko_market_chart_history(ticker, lookback_days)),
        ):
            rows = fn()
            if rows:
                logging.info("history %s resolved %s (%d rows)", name, ticker, len(rows))
                return rows, None
            failures.append(name)

    # Stooq direct CSV for listed securities.
    stooq_sym = _stooq_symbol_for(ticker, market)
    if stooq_sym:
        rows = _stooq_history(stooq_sym, lookback_days)
        if rows:
            logging.info("history stooq resolved %s (%d rows)", ticker, len(rows))
            return rows, None
        failures.append("stooq")

    # Direct Yahoo chart API before yfinance, because it avoids the yfinance
    # library's metadata calls and often survives partial yfinance rate limits.
    yf_sym = None
    if market == MarketType.CRYPTO:
        yf_sym = _crypto_yf_symbol(ticker)
    else:
        yf_sym = to_yfinance_symbol(ticker, market)
    if yf_sym:
        rows = _yahoo_chart_history(yf_sym, lookback_days)
        if rows:
            logging.info("history yahoo_chart resolved %s (%d rows)", ticker, len(rows))
            return rows, None
        failures.append("yahoo_chart")

        rows = _yf_history(yf_sym, lookback_days)
        if rows:
            logging.info("history yfinance resolved %s (%d rows)", ticker, len(rows))
            return rows, None
        failures.append("yfinance")

    return [], "no-data:" + ",".join(failures or ["no_source"])


# --------------------------------------------------------------------------- #
# FX pairs
# --------------------------------------------------------------------------- #

def required_fx_pairs(lots: List[Lot], base: str) -> List[str]:
    """Return the list of `base/native` FX pairs needed for non-cash holdings."""
    pairs: List[str] = []
    seen = set()
    for lot in lots:
        if lot.bucket.lower().startswith("cash"):
            ccy = lot.ticker.upper()
        else:
            ccy = _native_ccy_for_market(lot.market)
        if not ccy or ccy == base:
            continue
        pair = f"{base}/{ccy}"
        if pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)
    return pairs


def _native_ccy_for_market(market: MarketType) -> str:
    if market == MarketType.TW or market == MarketType.TWO:
        return "TWD"
    if market == MarketType.JP:
        return "JPY"
    if market == MarketType.HK:
        return "HKD"
    if market == MarketType.LSE:
        return "GBP"
    return "USD"


def _frankfurter_fx_history(pair: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Frankfurter public FX time series. Pair is `base/native`."""
    base, native = pair.split("/")
    start = (_dt.date.today() - _dt.timedelta(days=lookback_days + 7)).isoformat()
    end = _dt.date.today().isoformat()
    payload = _requests_get_json(
        "https://api.frankfurter.dev/v2/rates",
        params={"from": start, "to": end, "base": base, "quotes": native},
    )
    rates = (payload or {}).get("rates") if isinstance(payload, dict) else None
    if not isinstance(rates, dict):
        return []
    rows: List[Dict[str, Any]] = []
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback_days)).isoformat()
    for date, values in rates.items():
        if date < cutoff or not isinstance(values, dict):
            continue
        try:
            rate = float(values[native])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({"date": date, "rate": rate})
    return _dedupe_rows(rows, value_key="rate")


def fetch_fx_history(pair: str, lookback_days: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Pair like 'USD/TWD'. yfinance symbol: TWD=X (=X is base USD; pair denoted as native=X).

    For pairs where base != USD we rely on triangulation through USD.
    """
    base, native = pair.split("/")
    if native == base:
        return [], None

    failures: List[str] = []
    yf_sym = f"{native}=X" if base == "USD" else f"{base}{native}=X"
    rows = _yahoo_chart_history(yf_sym, lookback_days)
    if rows:
        return [{"date": r["date"], "rate": r["close"]} for r in rows], None
    failures.append("yahoo_chart")

    rows = _frankfurter_fx_history(pair, lookback_days)
    if rows:
        return rows, None
    failures.append("frankfurter")

    rows = _yf_history(yf_sym, lookback_days)
    if rows:
        return [{"date": r["date"], "rate": r["close"]} for r in rows], None
    failures.append("yfinance")

    # Try the inverse/direct Yahoo convention as a final FX fallback; if it is
    # the inverse of the desired pair, invert the close values.
    inverse_sym = f"{native}{base}=X"
    if inverse_sym != yf_sym:
        rows = _yahoo_chart_history(inverse_sym, lookback_days)
        if rows:
            inv_rows = []
            for r in rows:
                close = r.get("close")
                if close:
                    inv_rows.append({"date": r["date"], "rate": round(1.0 / float(close), 8)})
            if inv_rows:
                return inv_rows, None
        failures.append("yahoo_inverse")

    return [], "no-data:" + ",".join(failures)


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def collect_history(
    lots: List[Lot],
    settings: Path,
    *,
    lookback_days: int = 400,
    cache_path: Optional[Path] = DEFAULT_CACHE_PATH,
    cache_max_stale_days: int = 5,
) -> Dict[str, Any]:
    """Collect history for lots loaded from transactions.db."""
    base = parse_base_currency(settings) if settings.exists() else "USD"
    use_cache = cache_path is not None
    if use_cache:
        cache_init(cache_path)

    by_ticker: Dict[Tuple[str, MarketType], List[Lot]] = {}
    for lot in lots:
        if lot.bucket.lower().startswith("cash"):
            continue
        by_ticker.setdefault((lot.ticker, lot.market), []).append(lot)

    history: Dict[str, List[Dict[str, Any]]] = {}
    tickers_ok: List[str] = []
    tickers_failed: List[Dict[str, str]] = []
    cache_hits: List[str] = []
    network_fetches: List[str] = []

    for (ticker, market), _ in by_ticker.items():
        cached = cache_get_price_rows(cache_path, ticker, market, lookback_days) if use_cache and cache_path else []
        if _cache_rows_fresh(cached, lookback_days, max_stale_days=cache_max_stale_days):
            history[ticker] = cached
            tickers_ok.append(ticker)
            cache_hits.append(ticker)
            continue

        rows, reason = fetch_ticker_history(ticker, market, lookback_days)
        if rows:
            if use_cache and cache_path:
                cache_put_price_rows(cache_path, ticker, market, rows, source="api_fallback_chain")
                rows = cache_get_price_rows(cache_path, ticker, market, lookback_days)
            else:
                rows = _dedupe_rows(cached + rows)
            history[ticker] = rows
            tickers_ok.append(ticker)
            network_fetches.append(ticker)
        elif cached:
            history[ticker] = cached
            tickers_ok.append(ticker)
            cache_hits.append(ticker)
            tickers_failed.append({"ticker": ticker, "reason": f"{reason or 'unknown'}; using stale cache"})
        else:
            tickers_failed.append({"ticker": ticker, "reason": reason or "unknown"})

    fx_pairs = required_fx_pairs(lots, base)
    fx_history: Dict[str, List[Dict[str, Any]]] = {}
    fx_ok: List[str] = []
    fx_failed: List[Dict[str, str]] = []
    fx_cache_hits: List[str] = []
    fx_network_fetches: List[str] = []
    for pair in fx_pairs:
        cached = cache_get_fx_rows(cache_path, pair, lookback_days) if use_cache and cache_path else []
        if _cache_rows_fresh(cached, lookback_days, max_stale_days=cache_max_stale_days):
            fx_history[pair] = cached
            fx_ok.append(pair)
            fx_cache_hits.append(pair)
            continue

        rows, reason = fetch_fx_history(pair, lookback_days)
        if rows:
            if use_cache and cache_path:
                cache_put_fx_rows(cache_path, pair, rows, source="api_fallback_chain")
                rows = cache_get_fx_rows(cache_path, pair, lookback_days)
            else:
                rows = _dedupe_rows(cached + rows, value_key="rate")
            fx_history[pair] = rows
            fx_ok.append(pair)
            fx_network_fetches.append(pair)
        elif cached:
            fx_history[pair] = cached
            fx_ok.append(pair)
            fx_cache_hits.append(pair)
            fx_failed.append({"pair": pair, "reason": f"{reason or 'unknown'}; using stale cache"})
        else:
            fx_failed.append({"pair": pair, "reason": reason or "unknown"})

    return {
        "_history": history,
        "_fx_history": fx_history,
        "_history_meta": {
            "as_of": _utc_iso(),
            "lookback_days": lookback_days,
            "base_currency": base,
            "tickers_ok": sorted(tickers_ok),
            "tickers_failed": tickers_failed,
            "fx_ok": sorted(fx_ok),
            "fx_failed": fx_failed,
            "cache": {
                "enabled": use_cache,
                "path": str(cache_path) if cache_path else None,
                "max_stale_days": cache_max_stale_days,
                "ticker_cache_hits": sorted(cache_hits),
                "ticker_network_fetches": sorted(network_fetches),
                "fx_cache_hits": sorted(fx_cache_hits),
                "fx_network_fetches": sorted(fx_network_fetches),
            },
        },
    }


def merge_into_prices(prices_path: Path, history: Dict[str, Any]) -> None:
    if not prices_path.exists():
        prices_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    existing = json.loads(prices_path.read_text(encoding="utf-8"))
    existing["_history"] = history.get("_history", {})
    existing["_fx_history"] = history.get("_fx_history", {})
    existing["_history_meta"] = history.get("_history_meta", {})
    prices_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=Path("transactions.db"), type=Path,
                   help="Path to transactions.db (canonical source; default: ./transactions.db)")
    p.add_argument("--settings", default="SETTINGS.md", type=Path)
    p.add_argument("--output", default=Path("prices_history.json"), type=Path)
    p.add_argument("--lookback-days", default=400, type=int,
                   help="How many trading days of history to fetch (default: 400)")
    p.add_argument("--cache", default=DEFAULT_CACHE_PATH, type=Path,
                   help="SQLite market-data cache path (default: market_data_cache.db)")
    p.add_argument("--no-cache", action="store_true",
                   help="Disable cache reads/writes for this run")
    p.add_argument("--cache-max-stale-days", default=5, type=int,
                   help="Use cache without network when latest cached row is within this many days (default: 5)")
    p.add_argument("--merge-into", default=None, type=Path,
                   help="Optional: merge _history/_fx_history into this existing prices.json")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.db and args.db.exists():
        # Use the fetch *universe* (current holdings + sold-off tickers) so
        # historical-boundary valuations in compute_profit_panel can resolve
        # closes for tickers that have since been fully sold.
        from transactions import load_fetch_universe_lots  # type: ignore[import-not-found]
        lots = load_fetch_universe_lots(args.db)
    else:
        print(f"ERROR: no source found at --db {args.db}. "
              f"Run `python scripts/transactions.py db init` and import transactions first.",
              file=sys.stderr)
        return 2
    history = collect_history(
        lots,
        args.settings,
        lookback_days=args.lookback_days,
        cache_path=None if args.no_cache else args.cache,
        cache_max_stale_days=args.cache_max_stale_days,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.output}: "
          f"{len(history.get('_history', {}))} tickers, "
          f"{len(history.get('_fx_history', {}))} FX pairs.")
    if args.merge_into:
        merge_into_prices(args.merge_into, history)
        print(f"Merged history into {args.merge_into}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
