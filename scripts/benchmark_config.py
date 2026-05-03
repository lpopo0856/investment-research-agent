#!/usr/bin/env python3
"""Benchmark ETF defaults and SETTINGS.md override parsing.

The report pipeline uses this module to make benchmark tickers part of the
same latest-price/history universe as portfolio holdings.  Numeric benchmark
returns are still computed downstream from ``prices.json`` by the snapshot
math layer; the renderer only formats precomputed fields.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class BenchmarkSpec:
    ticker: str
    market: str = "US"


DEFAULT_GLOBAL_BENCHMARK = BenchmarkSpec("VT", "US")

# Market codes match transactions._asset_class_for_market / renderer ordering.
DEFAULT_MARKET_BENCHMARKS: Dict[str, Optional[BenchmarkSpec]] = {
    "us": BenchmarkSpec("VTI", "US"),
    "tw": BenchmarkSpec("0050.TW", "TW"),
    "two": BenchmarkSpec("00928.TW", "TW"),
    "jp": BenchmarkSpec("EWJ", "US"),
    "hk": BenchmarkSpec("EWH", "US"),
    "lse": BenchmarkSpec("EWU", "US"),
    # Explicitly unbenchmarked in v1: no clean broad-market ETF in the same
    # semantics as the equity market buckets.
    "crypto": None,
    "fx": None,
    "cash": None,
    "other": None,
}

_SECTION_RE = re.compile(r"^##\s+Benchmark ETFs(?:\s+\(optional\))?\s*$", re.IGNORECASE)
_HEADING_RE = re.compile(r"^##\s+")
_BULLET_RE = re.compile(r"^\s*-\s*(?P<key>[^:]+):\s*(?P<value>.+?)\s*$")
_MARKET_TAG_RE = re.compile(r"\[(?P<market>[A-Za-z0-9_.-]+)\]\s*$")
_NONE_VALUES = {"", "-", "—", "none", "n/a", "na", "null", "no benchmark"}

_KEY_TO_CODE: Dict[str, str] = {
    "global": "global",
    "global benchmark": "global",
    "portfolio benchmark": "global",
    "total benchmark": "global",
    "us": "us",
    "us market": "us",
    "us market benchmark": "us",
    "united states": "us",
    "united states benchmark": "us",
    "taiwan": "tw",
    "taiwan listed": "tw",
    "taiwan listed benchmark": "tw",
    "tw": "tw",
    "tw market": "tw",
    "taiwan otc": "two",
    "taiwan otc benchmark": "two",
    "two": "two",
    "two market": "two",
    "japan": "jp",
    "japan market": "jp",
    "japan market benchmark": "jp",
    "jp": "jp",
    "hong kong": "hk",
    "hong kong market": "hk",
    "hong kong market benchmark": "hk",
    "hk": "hk",
    "london": "lse",
    "london market": "lse",
    "london market benchmark": "lse",
    "uk": "lse",
    "uk market": "lse",
    "lse": "lse",
    "crypto": "crypto",
    "crypto benchmark": "crypto",
    "fx": "fx",
    "fx benchmark": "fx",
    "cash": "cash",
    "cash benchmark": "cash",
    "other": "other",
    "other benchmark": "other",
}


def _normalize_ticker(ticker: str) -> str:
    ticker = ticker.strip()
    if "." not in ticker:
        return ticker.upper()
    head, *suffix = ticker.split(".")
    return head.upper() + "." + ".".join(s.upper() for s in suffix)


def infer_market_for_ticker(ticker: str, default: str = "US") -> str:
    t = ticker.upper()
    if t.endswith(".TW"):
        return "TW"
    if t.endswith(".TWO"):
        return "TWO"
    if t.endswith(".T"):
        return "JP"
    if t.endswith(".HK"):
        return "HK"
    if t.endswith(".L"):
        return "LSE"
    if t.endswith("=X"):
        return "FX"
    return default


def _parse_spec(raw: str, *, default_market: str = "US") -> Optional[BenchmarkSpec]:
    value = raw.strip().strip("`")
    if value.lower() in _NONE_VALUES:
        return None
    market = None
    m = _MARKET_TAG_RE.search(value)
    if m:
        market = m.group("market").strip()
        value = value[: m.start()].strip()
    # Allow "TICKER MARKET" only when the second token looks like a market tag.
    parts = value.split()
    if len(parts) >= 2 and parts[-1].upper() in {"US", "TW", "TWO", "JP", "HK", "LSE", "FX", "CRYPTO", "CASH"}:
        market = parts[-1]
        value = " ".join(parts[:-1]).strip()
    ticker = _normalize_ticker(value)
    if not ticker:
        return None
    return BenchmarkSpec(ticker=ticker, market=(market or infer_market_for_ticker(ticker, default_market)).upper())


def _iter_benchmark_bullets(text: str) -> Iterable[tuple[str, str]]:
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if _HEADING_RE.match(line):
            in_section = bool(_SECTION_RE.match(line))
            continue
        if not in_section:
            continue
        m = _BULLET_RE.match(line)
        if not m:
            continue
        yield m.group("key").strip().lower(), m.group("value").strip()


def load_benchmark_config(path: Optional[Path]) -> Dict[str, Any]:
    """Return serializable benchmark config with defaults plus SETTINGS overrides."""
    global_spec: Optional[BenchmarkSpec] = DEFAULT_GLOBAL_BENCHMARK
    markets: Dict[str, Optional[BenchmarkSpec]] = dict(DEFAULT_MARKET_BENCHMARKS)
    source = "defaults"

    if path is not None and path.exists():
        text = path.read_text(encoding="utf-8")
        for raw_key, raw_value in _iter_benchmark_bullets(text):
            code = _KEY_TO_CODE.get(raw_key)
            if code is None:
                continue
            if code == "global":
                global_spec = _parse_spec(raw_value, default_market="US")
            else:
                markets[code] = _parse_spec(raw_value, default_market="US")
            source = "defaults+settings"

    return {
        "source": source,
        "global": asdict(global_spec) if global_spec else None,
        "markets": {
            code: (asdict(spec) if spec else None)
            for code, spec in markets.items()
        },
    }


def iter_benchmark_specs(config: Dict[str, Any]) -> List[BenchmarkSpec]:
    specs: List[BenchmarkSpec] = []
    global_spec = config.get("global")
    if isinstance(global_spec, dict) and global_spec.get("ticker"):
        specs.append(BenchmarkSpec(str(global_spec["ticker"]).upper(), str(global_spec.get("market") or "US").upper()))
    markets = config.get("markets") if isinstance(config.get("markets"), dict) else {}
    for spec in markets.values():
        if isinstance(spec, dict) and spec.get("ticker"):
            specs.append(BenchmarkSpec(str(spec["ticker"]).upper(), str(spec.get("market") or "US").upper()))
    # Stable de-dupe by (ticker, market).
    out: List[BenchmarkSpec] = []
    seen: set[tuple[str, str]] = set()
    for spec in specs:
        key = (spec.ticker, spec.market)
        if key in seen:
            continue
        seen.add(key)
        out.append(spec)
    return out
