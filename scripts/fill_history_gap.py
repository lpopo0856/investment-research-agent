"""Inject web-researched OHLC / FX rows after fetch_history.py reports a gap.

When `fetch_history.py` exits 5 with a gap list, the agent must web-search the
missing entries and use this helper to persist them. Rows go to the SQLite cache given by ``--cache`` (default: cwd
``market_data_cache.db``, so subsequent ``fetch_history.py`` runs see them as
cache hits) and optionally merged into ``prices.json``. **Demo ledger runs**
must use the same ``--cache demo/market_data_cache.db`` as ``fetch_history.py``.

Per /docs/portfolio_report_agent_guidelines/03-latest-price-retrieval.md, the
attribution `agent_web_search` is the durable source-of-truth tag for any
manually-injected row.

Usage:
    # Stock / ETF
    python scripts/fill_history_gap.py ticker \\
        --ticker NVDA --market US \\
        --rows-json '[{"date":"2026-04-30","close":923.50},
                      {"date":"2026-04-29","close":914.10}]' \\
        --merge-into prices.json

    # FX
    python scripts/fill_history_gap.py fx \\
        --pair USD/TWD \\
        --rows-json '[{"date":"2026-04-30","rate":32.55}]' \\
        --merge-into prices.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Reuse cache writers + canonical types from the fetcher.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_history import (  # noqa: E402
    DEFAULT_CACHE_PATH,
    cache_put_fx_rows,
    cache_put_price_rows,
)
from fetch_prices import MarketType  # noqa: E402

AGENT_SOURCE = "agent_web_search"


def _validate_price_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clean: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError(f"row must be a dict, got: {r!r}")
        date = r.get("date")
        close = r.get("close")
        if not date or close is None:
            raise ValueError(f"price row missing date/close: {r!r}")
        clean.append({"date": str(date), "close": float(close)})
    if not clean:
        raise ValueError("--rows-json produced zero usable rows")
    return clean


def _validate_fx_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clean: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError(f"row must be a dict, got: {r!r}")
        date = r.get("date")
        rate = r.get("rate")
        if not date or rate is None:
            raise ValueError(f"fx row missing date/rate: {r!r}")
        clean.append({"date": str(date), "rate": float(rate)})
    if not clean:
        raise ValueError("--rows-json produced zero usable rows")
    return clean


def _merge_ticker_into_prices(prices_path: Path,
                              ticker: str,
                              rows: List[Dict[str, Any]]) -> None:
    payload = json.loads(prices_path.read_text(encoding="utf-8"))
    hist = payload.setdefault("_history", {})
    existing = hist.get(ticker) or []
    by_date: Dict[str, Dict[str, Any]] = {r["date"]: r for r in existing if r.get("date")}
    for r in rows:
        by_date[r["date"]] = r
    hist[ticker] = sorted(by_date.values(), key=lambda r: r["date"])

    meta = payload.setdefault("_history_meta", {})
    ok = set(meta.get("tickers_ok") or [])
    ok.add(ticker)
    meta["tickers_ok"] = sorted(ok)
    meta["tickers_failed"] = [
        f for f in (meta.get("tickers_failed") or [])
        if f.get("ticker") != ticker
    ]
    prices_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                           encoding="utf-8")


def _merge_fx_into_prices(prices_path: Path,
                          pair: str,
                          rows: List[Dict[str, Any]]) -> None:
    payload = json.loads(prices_path.read_text(encoding="utf-8"))
    fx = payload.setdefault("_fx_history", {})
    existing = fx.get(pair) or []
    by_date: Dict[str, Dict[str, Any]] = {r["date"]: r for r in existing if r.get("date")}
    for r in rows:
        by_date[r["date"]] = r
    fx[pair] = sorted(by_date.values(), key=lambda r: r["date"])

    meta = payload.setdefault("_history_meta", {})
    ok = set(meta.get("fx_ok") or [])
    ok.add(pair)
    meta["fx_ok"] = sorted(ok)
    meta["fx_failed"] = [
        f for f in (meta.get("fx_failed") or [])
        if f.get("pair") != pair
    ]
    prices_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                           encoding="utf-8")


def fill_ticker(ticker: str,
                market: MarketType,
                rows: List[Dict[str, Any]],
                cache_path: Path = DEFAULT_CACHE_PATH,
                merge_into: Optional[Path] = None,
                currency: Optional[str] = None) -> Dict[str, Any]:
    clean = _validate_price_rows(rows)
    cache_put_price_rows(cache_path, ticker, market, clean,
                         source=AGENT_SOURCE, currency=currency)
    if merge_into:
        if not merge_into.exists():
            raise FileNotFoundError(
                f"--merge-into {merge_into} does not exist; run fetch_history.py "
                "with --merge-into first to seed it."
            )
        _merge_ticker_into_prices(merge_into, ticker, clean)
    return {"ticker": ticker, "market": market.value, "rows_written": len(clean),
            "cache_path": str(cache_path),
            "merged_into": str(merge_into) if merge_into else None}


def fill_fx(pair: str,
            rows: List[Dict[str, Any]],
            cache_path: Path = DEFAULT_CACHE_PATH,
            merge_into: Optional[Path] = None) -> Dict[str, Any]:
    if "/" not in pair:
        raise ValueError(f"--pair must be 'BASE/QUOTE' (got {pair!r})")
    clean = _validate_fx_rows(rows)
    cache_put_fx_rows(cache_path, pair, clean, source=AGENT_SOURCE)
    if merge_into:
        if not merge_into.exists():
            raise FileNotFoundError(
                f"--merge-into {merge_into} does not exist; run fetch_history.py "
                "with --merge-into first to seed it."
            )
        _merge_fx_into_prices(merge_into, pair, clean)
    return {"pair": pair, "rows_written": len(clean),
            "cache_path": str(cache_path),
            "merged_into": str(merge_into) if merge_into else None}


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default=DEFAULT_CACHE_PATH, type=Path,
                   help=f"Market-data cache path (default: {DEFAULT_CACHE_PATH})")
    p.add_argument("--merge-into", default=None, type=Path,
                   help="Optional: also merge rows into this prices.json so the "
                        "active pipeline run sees them without re-fetch.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pt = sub.add_parser("ticker", help="Fill a missing equity / ETF / crypto history")
    pt.add_argument("--ticker", required=True)
    pt.add_argument("--market", required=True,
                    choices=[m.value for m in MarketType],
                    help="Market tag (US, TW, TWO, JP, HK, LSE, crypto, FX, ...).")
    pt.add_argument("--rows-json", required=True,
                    help='JSON array of {"date":"YYYY-MM-DD","close":N} rows.')
    pt.add_argument("--currency", default=None,
                    help="Quote currency for the cache row (optional).")

    pf = sub.add_parser("fx", help="Fill a missing FX-pair history")
    pf.add_argument("--pair", required=True,
                    help="BASE/QUOTE, e.g. USD/TWD")
    pf.add_argument("--rows-json", required=True,
                    help='JSON array of {"date":"YYYY-MM-DD","rate":N} rows.')

    args = p.parse_args(argv)
    try:
        rows = json.loads(args.rows_json)
        if not isinstance(rows, list):
            raise ValueError("--rows-json must decode to a JSON array")
        if args.cmd == "ticker":
            result = fill_ticker(
                ticker=args.ticker,
                market=MarketType(args.market),
                rows=rows,
                cache_path=args.cache,
                merge_into=args.merge_into,
                currency=args.currency,
            )
        else:
            result = fill_fx(
                pair=args.pair,
                rows=rows,
                cache_path=args.cache,
                merge_into=args.merge_into,
            )
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
