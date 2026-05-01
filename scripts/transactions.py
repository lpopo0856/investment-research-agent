#!/usr/bin/env python3
"""
transactions.db ledger engine.

Append-only event log for the portfolio. Captures the *operation mindset*
(rationale, tags, lot consumption) of every flow — buys, sells, deposits,
withdrawals, dividends, fees, and FX conversions.

This script provides:

  - SQLite event log for every transaction and cash flow
  - Legacy HOLDINGS.md parser for one-shot migration only
  - Replay engine: walk events in chronological order, build positions and
    cash balances at any cutoff date
  - Realized / unrealized P&L computation
  - Profit panel computation for periods 1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME
  - Migrate command: bootstrap transactions.db from existing HOLDINGS.md
  - Verify command: replay events and diff against materialized balance tables
  - Self-check unit tests

Usage
-----
    python scripts/transactions.py migrate --holdings HOLDINGS.md [--dry-run]

    python scripts/transactions.py verify

    python scripts/transactions.py pnl --prices prices.json [--settings SETTINGS.md]

    python scripts/transactions.py profit-panel \\
        --prices prices.json --settings SETTINGS.md --output profit_panel.json

    python scripts/transactions.py analytics \\
        --prices prices.json --settings SETTINGS.md --output transaction_analytics.json

    python scripts/transactions.py self-check
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as _dt
import json
import logging
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Allow import from sibling fetch_prices.py for legacy HOLDINGS.md parsing.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from fetch_prices import (  # type: ignore[import-not-found]
    KNOWN_CRYPTO_SYMBOLS,
    KNOWN_FIAT_CODES,
    Lot,
    MarketType,
    parse_holdings,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

TRANSACTION_TYPES = {
    "BUY", "SELL", "DEPOSIT", "WITHDRAW", "DIVIDEND",
    "FEE", "FX_CONVERT", "ADJUST", "REVERSAL",
}

# Types that move external cash boundary in/out of the portfolio.
# Dividends and fees flow into P&L, NOT external flows.
EXTERNAL_FLOW_TYPES = {"DEPOSIT", "WITHDRAW"}

# Heading: "## YYYY-MM-DD TYPE [TICKER]"
_TXN_HEADING_RE = re.compile(
    r"^##\s+(?P<date>\d{4}-\d{2}-\d{2})"
    r"\s+(?P<type>[A-Z_]+)"
    r"(?:\s+(?P<ticker>[A-Za-z0-9._-]+))?\s*$"
)

_FIELD_RE = re.compile(r"^\s*-\s*(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?P<value>.*?)\s*$")
_LOT_LINE_RE = re.compile(
    r"^\s+-\s+(?P<acq_date>\d{4}-\d{2}-\d{2})@(?P<cost>[^\s:]*[0-9][0-9.,]*)\s*:\s*(?P<qty>[0-9.,]+)\s*$"
)
_NUMERIC_RE = re.compile(r"-?[0-9]*\.?[0-9]+")


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #

@dataclass
class Transaction:
    """One entry from TRANSACTIONS.md."""
    seq: int                                    # 0-based file order; tiebreaker for same-day sort
    date: str                                   # ISO YYYY-MM-DD
    type: str                                   # one of TRANSACTION_TYPES
    ticker: Optional[str]                       # canonicalized; None for cash-only events
    raw_heading: str
    fields: Dict[str, str] = field(default_factory=dict)
    lots_consumed: List[Tuple[str, float, float]] = field(default_factory=list)  # (acq_date, cost, qty)
    rationale: str = ""
    tags: List[str] = field(default_factory=list)

    # Resolved numeric helpers — populated after parse
    qty: Optional[float] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    fees: Optional[float] = None
    realized_pnl: Optional[float] = None
    currency: Optional[str] = None
    cash_account: Optional[str] = None
    bucket: Optional[str] = None
    market: Optional[str] = None

    def signed_cash_delta_native(self) -> Tuple[Optional[str], float]:
        """Return (currency, delta) for the cash_account this txn touches.
        Positive = inflow to cash, negative = outflow.
        For FX_CONVERT and multi-leg, callers should use raw fields.
        """
        if self.type == "BUY":
            net = (self.qty or 0) * (self.price or 0)
            if self.fees:
                net += self.fees
            return self.cash_account or self.currency, -net
        if self.type == "SELL":
            net = (self.qty or 0) * (self.price or 0)
            if self.fees:
                net -= self.fees
            return self.cash_account or self.currency, net
        if self.type == "DEPOSIT":
            return self.cash_account or self.currency, (self.amount or 0)
        if self.type == "WITHDRAW":
            return self.cash_account or self.currency, -(self.amount or 0)
        if self.type == "DIVIDEND":
            return self.cash_account or self.currency, (self.amount or 0)
        if self.type == "FEE":
            return self.cash_account or self.currency, -(self.amount or 0)
        return None, 0.0


@dataclass
class OpenLot:
    """A still-open share/crypto position lot after replay."""
    ticker: str
    qty: float
    cost: float            # cost per unit, native currency
    acq_date: str          # ISO date
    bucket: str
    market: str
    currency: str          # trade currency, e.g. USD, TWD


@dataclass
class RealizedEvent:
    """A closed P&L impact (SELL leg, dividend, fee)."""
    date: str
    ticker: Optional[str]
    type: str              # "SELL_LOT", "DIVIDEND", "FEE"
    qty: float
    sell_price: Optional[float]
    cost: Optional[float]
    realized_native: float  # in native currency (P&L impact, signed)
    currency: str
    acq_date: Optional[str] = None


@dataclass
class ReplayState:
    """Snapshot of book state after replaying transactions up to a cutoff."""
    cutoff: str                                       # ISO date (inclusive)
    open_lots: Dict[str, List[OpenLot]] = field(default_factory=dict)  # by ticker
    cash: Dict[str, float] = field(default_factory=dict)               # by currency
    realized_events: List[RealizedEvent] = field(default_factory=list)
    deposits_native: Dict[str, float] = field(default_factory=dict)    # by currency
    withdrawals_native: Dict[str, float] = field(default_factory=dict) # by currency
    issues: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #

def _strip_currency(s: str) -> Optional[float]:
    """Parse amounts like '$211.208', 'NT$2,300', '0.0634', '-3.5', '1.00' -> float."""
    if s is None:
        return None
    s = s.strip()
    if not s or s == "?":
        return None
    cleaned = re.sub(r"[^\d.\-]", "", s)
    if cleaned in ("", ".", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_ticker(t: str) -> str:
    if "." in t:
        head, *rest = t.split(".")
        return head.upper() + "." + ".".join(r.upper() for r in rest)
    return t.upper()


def parse_transactions(path: Path) -> List[Transaction]:
    """Parse TRANSACTIONS.md. Returns transactions in file order with seq populated.

    File format:

        ## YYYY-MM-DD TYPE [TICKER]
        - field: value
        - lots:
            - 2026-04-10@$211.208: 5
        - tags: a, b, c
        - rationale: free text
    """
    if not path.exists():
        return []

    txns: List[Transaction] = []
    seq = 0
    cur: Optional[Transaction] = None
    in_lots_block = False
    body_lines = path.read_text(encoding="utf-8").splitlines()

    def _commit(t: Optional[Transaction]) -> None:
        if t is None:
            return
        # Resolve numeric helpers from fields
        f = t.fields
        t.qty = _strip_currency(f.get("qty"))
        t.price = _strip_currency(f.get("price"))
        t.amount = _strip_currency(f.get("amount"))
        t.fees = _strip_currency(f.get("fees"))
        t.realized_pnl = _strip_currency(f.get("realized_pnl"))
        t.currency = (f.get("currency") or "").strip().upper() or None
        t.cash_account = (f.get("cash_account") or t.currency or "").strip().upper() or None
        t.bucket = (f.get("bucket") or "").strip() or None
        t.market = (f.get("market") or "").strip() or None
        t.rationale = (f.get("rationale") or "").strip()
        if "tags" in f:
            t.tags = [tag.strip() for tag in f["tags"].split(",") if tag.strip()]
        txns.append(t)

    for raw in body_lines:
        line = raw.rstrip("\n")
        m_h = _TXN_HEADING_RE.match(line.strip())
        if m_h:
            _commit(cur)
            ticker = m_h.group("ticker")
            cur = Transaction(
                seq=seq,
                date=m_h.group("date"),
                type=m_h.group("type"),
                ticker=_normalize_ticker(ticker) if ticker else None,
                raw_heading=line.strip(),
            )
            seq += 1
            in_lots_block = False
            continue

        if cur is None:
            continue

        # Lots sub-block: lines indented under `- lots:`
        m_lot = _LOT_LINE_RE.match(line)
        if in_lots_block and m_lot:
            cost = _strip_currency(m_lot.group("cost"))
            qty = _strip_currency(m_lot.group("qty"))
            if cost is not None and qty is not None:
                cur.lots_consumed.append((m_lot.group("acq_date"), cost, qty))
            continue

        m_f = _FIELD_RE.match(line)
        if m_f:
            key = m_f.group("key").lower().replace("-", "_")
            val = m_f.group("value")
            cur.fields[key] = val
            in_lots_block = (key == "lots" and val.strip() == "")
            continue

        # Anything else ends the lots block
        in_lots_block = False

    _commit(cur)
    return txns


# --------------------------------------------------------------------------- #
# Replay engine
# --------------------------------------------------------------------------- #

def _txn_sort_key(t: Transaction) -> Tuple[str, int]:
    return (t.date, t.seq)


def replay(
    txns: List[Transaction],
    cutoff: Optional[str] = None,
) -> ReplayState:
    """Apply transactions in chronological order, up to and including `cutoff`.

    Returns the resulting state: open lots, cash balances, and realized events.
    """
    cutoff = cutoff or _dt.date.today().isoformat()
    state = ReplayState(cutoff=cutoff)

    sorted_txns = sorted(txns, key=_txn_sort_key)
    for t in sorted_txns:
        if t.date > cutoff:
            break
        try:
            _apply_one(t, state)
        except Exception as e:
            state.issues.append(f"{t.date} {t.type} {t.ticker or ''}: {e}")
    return state


def _bump_cash(state: ReplayState, currency: Optional[str], delta: float) -> None:
    if not currency:
        return
    state.cash[currency] = state.cash.get(currency, 0.0) + delta


def _apply_one(t: Transaction, state: ReplayState) -> None:
    if t.type == "BUY":
        if t.ticker is None:
            state.issues.append(f"{t.date} BUY missing ticker")
            return
        if t.qty is None or t.price is None:
            state.issues.append(f"{t.date} BUY {t.ticker} missing qty/price")
            return
        net = t.qty * t.price + (t.fees or 0.0)
        currency = t.currency or "USD"
        lot = OpenLot(
            ticker=t.ticker,
            qty=t.qty,
            cost=t.price,
            acq_date=t.date,
            bucket=t.bucket or "Mid Term",
            market=t.market or "US",
            currency=currency,
        )
        state.open_lots.setdefault(t.ticker, []).append(lot)
        _bump_cash(state, t.cash_account or currency, -net)

    elif t.type == "SELL":
        if t.ticker is None:
            state.issues.append(f"{t.date} SELL missing ticker")
            return
        if t.qty is None or t.price is None:
            state.issues.append(f"{t.date} SELL {t.ticker} missing qty/price")
            return
        currency = t.currency or "USD"
        lots = state.open_lots.get(t.ticker, [])
        if not lots:
            state.issues.append(f"{t.date} SELL {t.ticker} has no open lots")
            return

        # Consume lots directly. When the user supplied an explicit `lots:`
        # block, drain matching lots in declaration order; otherwise default
        # to highest-cost-first across all open lots. Either path mutates the
        # actual lot list, so two same-(acq_date, cost) lots are never
        # collapsed into a single match (the bug the previous lookup-by-key
        # implementation had).
        explicit = list(t.lots_consumed)
        remaining_total = t.qty
        if explicit:
            # Drain explicit pairs first, in order; then fall through to
            # highest-cost-first for any unmatched residue.
            for acq_date, cost, want_qty in explicit:
                want = want_qty
                for lot in lots:
                    if want <= 1e-9 or lot.qty <= 1e-9:
                        continue
                    if lot.acq_date != acq_date:
                        continue
                    if abs(lot.cost - cost) > 1e-6:
                        continue
                    take = min(lot.qty, want, remaining_total)
                    if take <= 1e-9:
                        continue
                    lot.qty -= take
                    want -= take
                    remaining_total -= take
                    state.realized_events.append(RealizedEvent(
                        date=t.date, ticker=t.ticker, type="SELL_LOT",
                        qty=take, sell_price=t.price, cost=cost,
                        realized_native=(t.price - cost) * take, currency=currency,
                        acq_date=acq_date,
                    ))
                if want > 1e-6:
                    state.issues.append(
                        f"{t.date} SELL {t.ticker} explicit lot {acq_date}@{cost} short by {want:g}"
                    )
        # Default path (or residue after explicit): highest-cost-first.
        if remaining_total > 1e-9:
            ordered = sorted(lots, key=lambda l: -l.cost)
            for lot in ordered:
                if remaining_total <= 1e-9:
                    break
                if lot.qty <= 1e-9:
                    continue
                take = min(lot.qty, remaining_total)
                lot.qty -= take
                remaining_total -= take
                state.realized_events.append(RealizedEvent(
                    date=t.date, ticker=t.ticker, type="SELL_LOT",
                    qty=take, sell_price=t.price, cost=lot.cost,
                    realized_native=(t.price - lot.cost) * take, currency=currency,
                    acq_date=lot.acq_date,
                ))
            if remaining_total > 1e-6:
                state.issues.append(
                    f"{t.date} SELL {t.ticker} qty {t.qty} exceeds open ({t.qty - remaining_total:g} matched)"
                )

        # Drop empty lots
        state.open_lots[t.ticker] = [l for l in state.open_lots.get(t.ticker, []) if l.qty > 1e-9]
        if not state.open_lots[t.ticker]:
            del state.open_lots[t.ticker]

        # Fees reduce realized P&L
        fees = t.fees or 0.0
        if fees:
            state.realized_events.append(RealizedEvent(
                date=t.date, ticker=t.ticker, type="FEE",
                qty=0, sell_price=None, cost=None,
                realized_native=-fees, currency=currency,
            ))
        net = t.qty * t.price - fees
        _bump_cash(state, t.cash_account or currency, net)

    elif t.type == "DEPOSIT":
        if t.amount is None:
            state.issues.append(f"{t.date} DEPOSIT missing amount")
            return
        currency = t.cash_account or t.currency or "USD"
        _bump_cash(state, currency, t.amount)
        state.deposits_native[currency] = state.deposits_native.get(currency, 0.0) + t.amount

    elif t.type == "WITHDRAW":
        if t.amount is None:
            state.issues.append(f"{t.date} WITHDRAW missing amount")
            return
        currency = t.cash_account or t.currency or "USD"
        _bump_cash(state, currency, -t.amount)
        state.withdrawals_native[currency] = state.withdrawals_native.get(currency, 0.0) + t.amount

    elif t.type == "DIVIDEND":
        if t.amount is None:
            state.issues.append(f"{t.date} DIVIDEND missing amount")
            return
        currency = t.cash_account or t.currency or "USD"
        _bump_cash(state, currency, t.amount)
        state.realized_events.append(RealizedEvent(
            date=t.date, ticker=t.ticker, type="DIVIDEND",
            qty=0, sell_price=None, cost=None,
            realized_native=t.amount, currency=currency,
        ))

    elif t.type == "FEE":
        if t.amount is None:
            state.issues.append(f"{t.date} FEE missing amount")
            return
        currency = t.cash_account or t.currency or "USD"
        _bump_cash(state, currency, -t.amount)
        state.realized_events.append(RealizedEvent(
            date=t.date, ticker=t.ticker, type="FEE",
            qty=0, sell_price=None, cost=None,
            realized_native=-t.amount, currency=currency,
        ))

    elif t.type == "FX_CONVERT":
        from_amount = _strip_currency(t.fields.get("from_amount"))
        to_amount = _strip_currency(t.fields.get("to_amount"))
        from_ccy = (t.fields.get("from_currency") or "").strip().upper()
        to_ccy = (t.fields.get("to_currency") or "").strip().upper()
        from_acct = (t.fields.get("from_cash_account") or from_ccy).strip().upper()
        to_acct = (t.fields.get("to_cash_account") or to_ccy).strip().upper()
        if from_amount is None or to_amount is None or not (from_ccy and to_ccy):
            state.issues.append(f"{t.date} FX_CONVERT incomplete")
            return
        if from_amount <= 0 or to_amount <= 0:
            state.issues.append(
                f"{t.date} FX_CONVERT requires positive from_amount and to_amount "
                f"(got from={from_amount}, to={to_amount})"
            )
            return
        _bump_cash(state, from_acct, -from_amount)
        _bump_cash(state, to_acct, to_amount)

    elif t.type in ("ADJUST", "REVERSAL"):
        # Manual corrections: agent should rarely use; replay just logs an issue
        # so the user is aware in verify output.
        state.issues.append(f"{t.date} {t.type} requires manual review (no auto-apply)")

    else:
        state.issues.append(f"{t.date} unknown transaction type: {t.type}")


# --------------------------------------------------------------------------- #
# Migration helpers
# --------------------------------------------------------------------------- #

def _market_for_lot(lot: Lot) -> str:
    return lot.market.value if isinstance(lot.market, MarketType) else str(lot.market)


def _currency_for_lot(lot: Lot) -> str:
    """Best-effort native trade currency for a holdings lot."""
    if lot.bucket.lower().startswith("cash"):
        return lot.ticker.upper()
    market = _market_for_lot(lot)
    if market == "TW" or market == "TWO":
        return "TWD"
    if market == "JP":
        return "JPY"
    if market == "HK":
        return "HKD"
    if market == "LSE":
        return "GBP"
    return "USD"


# --------------------------------------------------------------------------- #
# Profit panel
# --------------------------------------------------------------------------- #

def _date(d: str) -> _dt.date:
    return _dt.date.fromisoformat(d)


def _shift_calendar(d: _dt.date, *, days: int = 0, months: int = 0, years: int = 0) -> _dt.date:
    """Calendar shift, clamping day-of-month if needed."""
    if days:
        d = d - _dt.timedelta(days=days)
    if months or years:
        m = d.month - months
        y = d.year - years
        while m <= 0:
            m += 12
            y -= 1
        last = calendar.monthrange(y, m)[1]
        d = _dt.date(y, m, min(d.day, last))
    return d


def period_boundaries(today: _dt.date) -> Dict[str, _dt.date]:
    """Return the boundary date (exclusive *start*) per profit-panel period.

    The ending value is `today`. The starting value is portfolio value as-of
    end-of-day on the boundary date.
    """
    return {
        "1D": _shift_calendar(today, days=1),
        "7D": _shift_calendar(today, days=7),
        "MTD": _dt.date(today.year, today.month, 1) - _dt.timedelta(days=1),  # last close of prior month
        "1M": _shift_calendar(today, months=1),
        "YTD": _dt.date(today.year - 1, 12, 31),
        "1Y": _shift_calendar(today, years=1),
        # ALLTIME is filled in dynamically (earliest txn date)
    }


def _value_state(
    state: ReplayState,
    prices_at: Dict[str, float],            # native price by ticker
    fx: Dict[str, float],                   # base/native rate map (e.g. {"USD/TWD": 32.5})
    base: str,
) -> Tuple[float, List[str]]:
    """Compute total portfolio value (base currency) for a replay state.

    `prices_at` keyed by canonical ticker (UPPER, with .TW etc preserved).
    Missing prices for held tickers contribute n/a and are surfaced in audit.
    """
    audit: List[str] = []
    total = 0.0
    # Equities / crypto / FX
    for ticker, lots in state.open_lots.items():
        qty = sum(l.qty for l in lots)
        ccy = lots[0].currency if lots else "USD"
        latest = prices_at.get(ticker)
        if latest is None:
            audit.append(f"missing price for {ticker} at boundary")
            continue
        native_value = latest * qty
        rate = _fx_rate(fx, base, ccy, audit)
        if rate is None:
            continue
        total += native_value / rate

    # Cash
    for ccy, amount in state.cash.items():
        if abs(amount) < 1e-6:
            continue
        rate = _fx_rate(fx, base, ccy, audit)
        if rate is None:
            continue
        total += amount / rate
    return total, audit


def _fx_rate(fx: Dict[str, float], base: str, native: str, audit: List[str]) -> Optional[float]:
    """Return rate such that base_value = native_value / rate. Same as scripts/generate_report.py
    convention where fx[`{base}/{native}`] = rate."""
    if native == base:
        return 1.0
    # USD stablecoins map to USD rate
    USD_STABLES = {"USDC", "USDT", "DAI", "FDUSD", "USDP", "TUSD", "PYUSD", "BUSD"}
    if native in USD_STABLES:
        if base == "USD":
            return 1.0
        rate = fx.get(f"{base}/USD")
        if rate is None:
            audit.append(f"no FX rate for {base}/USD (stablecoin {native})")
            return None
        return rate
    rate = fx.get(f"{base}/{native}")
    if rate is None:
        audit.append(f"no FX rate for {base}/{native}")
        return None
    return rate


def _net_external_flows(txns: List[Transaction], start: str, end: str, fx: Dict[str, float], base: str, audit: List[str]) -> float:
    """Sum DEPOSIT − WITHDRAW within [start, end] (inclusive), base currency."""
    total = 0.0
    for t in txns:
        if t.date < start or t.date > end:
            continue
        if t.type not in EXTERNAL_FLOW_TYPES:
            continue
        amount = t.amount or 0.0
        ccy = (t.cash_account or t.currency or "USD").upper()
        sign = 1.0 if t.type == "DEPOSIT" else -1.0
        rate = _fx_rate(fx, base, ccy, audit)
        if rate is None:
            continue
        total += sign * amount / rate
    return total


def _realized_in_period(state: ReplayState, start: str, end: str, fx: Dict[str, float], base: str, audit: List[str]) -> float:
    """Sum realized events whose date falls in [start, end]."""
    total = 0.0
    for ev in state.realized_events:
        if ev.date < start or ev.date > end:
            continue
        rate = _fx_rate(fx, base, ev.currency, audit)
        if rate is None:
            continue
        total += ev.realized_native / rate
    return total


def _unrealized_pnl_state(
    state: ReplayState,
    prices_at: Dict[str, float],
    fx: Dict[str, float],
    base: str,
    audit_label: str,
) -> Tuple[float, List[str]]:
    """Open-lot unrealized P&L for a replay state.

    This is intentionally cost-basis based:
      Σ (mark_price - lot_cost) × open_qty

    Period unrealized delta is `ending_unrealized - boundary_unrealized`.
    That handles sold lots correctly because the boundary unrealized P&L of a
    lot sold during the period is removed while its sale gain moves into the
    realized column.
    """
    audit: List[str] = []
    total = 0.0
    for ticker, lots in state.open_lots.items():
        mark = prices_at.get(ticker)
        if mark is None:
            audit.append(f"missing price for {ticker} at {audit_label}; unrealized excluded")
            continue
        ccy = lots[0].currency if lots else "USD"
        rate = _fx_rate(fx, base, ccy, audit)
        if rate is None:
            continue
        native = sum((mark - lot.cost) * lot.qty for lot in lots)
        total += native / rate
    return total, audit


def _realized_in_period_by_market(
    state: ReplayState,
    start: str,
    end: str,
    fx: Dict[str, float],
    base: str,
    market_map: Dict[str, str],
    audit: List[str],
) -> Dict[str, float]:
    """Sum realized events in (start, end] grouped by asset-class code.

    Bucketed via `_asset_class_for_market`. Events on tickers not in
    `market_map` (which can happen if the ticker was fully closed before the
    market lookup ran) fall into "other" so the totals still balance.
    """
    out: Dict[str, float] = {}
    for ev in state.realized_events:
        if ev.date < start or ev.date > end:
            continue
        rate = _fx_rate(fx, base, ev.currency, audit)
        if rate is None:
            continue
        market_code = market_map.get(ev.ticker or "", "")
        cls = _asset_class_for_market(market_code) if market_code else "other"
        out[cls] = out.get(cls, 0.0) + ev.realized_native / rate
    return out


def _unrealized_pnl_state_by_market(
    state: ReplayState,
    prices_at: Dict[str, float],
    fx: Dict[str, float],
    base: str,
    market_map: Dict[str, str],
) -> Dict[str, float]:
    """Open-lot unrealized P&L grouped by asset-class code."""
    out: Dict[str, float] = {}
    for ticker, lots in state.open_lots.items():
        mark = prices_at.get(ticker)
        if mark is None or not lots:
            continue
        ccy = lots[0].currency
        rate = _fx_rate(fx, base, ccy, [])
        if rate is None:
            continue
        market_code = market_map.get(ticker, lots[0].market)
        cls = _asset_class_for_market(market_code)
        native = sum((mark - lot.cost) * lot.qty for lot in lots)
        out[cls] = out.get(cls, 0.0) + native / rate
    return out


# Minimum |starting position value| used as return denominator when positions-only.
_PROFIT_PANEL_MARKET_RETURN_EPS = 1.0


def _gross_position_value_by_market(
    state: ReplayState,
    prices_at: Dict[str, float],
    fx: Dict[str, float],
    base: str,
    market_map: Dict[str, str],
    audit: List[str],
) -> Dict[str, float]:
    """Gross mark-to-market value of open lots by asset-class code (no cash), base ccy."""
    out: Dict[str, float] = {}
    for ticker, lots in state.open_lots.items():
        if not lots:
            continue
        mark = prices_at.get(ticker)
        if mark is None:
            continue
        ccy = lots[0].currency if lots else "USD"
        rate = _fx_rate(fx, base, ccy, audit)
        if rate is None:
            continue
        qty = sum(l.qty for l in lots)
        native = float(mark) * qty
        market_code = market_map.get(ticker, lots[0].market)
        cls = _asset_class_for_market(market_code)
        out[cls] = out.get(cls, 0.0) + native / rate
    return out


def _earliest_txn_date(txns: List[Transaction]) -> Optional[str]:
    if not txns:
        return None
    return min(t.date for t in txns)


def _historical_close(history: Dict[str, List[Dict[str, Any]]], ticker: str, on_or_before: str) -> Optional[float]:
    """Latest close for ticker on-or-before the given date. None if not found."""
    series = history.get(ticker)
    if not series:
        return None
    best: Optional[Dict[str, Any]] = None
    for row in series:
        d = row.get("date")
        if d and d <= on_or_before:
            if best is None or d > best["date"]:
                best = row
    if best is None:
        return None
    try:
        return float(best.get("close"))
    except (TypeError, ValueError):
        return None


def _historical_fx(fx_history: Dict[str, List[Dict[str, Any]]], pair: str, on_or_before: str) -> Optional[float]:
    series = fx_history.get(pair)
    if not series:
        return None
    best: Optional[Dict[str, Any]] = None
    for row in series:
        d = row.get("date")
        if d and d <= on_or_before:
            if best is None or d > best["date"]:
                best = row
    if best is None:
        return None
    try:
        return float(best.get("rate"))
    except (TypeError, ValueError):
        return None


def _fx_at(
    boundary: str,
    fx_current: Dict[str, float],
    fx_history: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Dict[str, float], List[str]]:
    """Compose an FX map for the boundary date. Falls back to current rates with audit."""
    fx_at: Dict[str, float] = dict(fx_current)
    audit: List[str] = []
    for pair, series in (fx_history or {}).items():
        rate = _historical_fx(fx_history, pair, boundary)
        if rate is not None:
            fx_at[pair] = rate
        else:
            audit.append(f"no historical FX for {pair} at {boundary}; using current")
    if not fx_history:
        audit.append("no _fx_history in prices.json; profit-panel uses current FX (fx_approx)")
    return fx_at, audit


def compute_profit_panel(
    txns: List[Transaction],
    prices: Dict[str, Any],
    *,
    base: str = "USD",
    today: Optional[_dt.date] = None,
) -> Dict[str, Any]:
    """Compute the profit panel rows.

    `prices` is the full prices.json dict. It must contain:
      - per-ticker entries (with `latest_price`, `currency`)
      - `_fx` (current FX rates)
      - optional `_history` (per-ticker [{date, close}] daily closes)
      - optional `_fx_history` (per-pair [{date, rate}] daily rates)
    """
    today = today or _dt.date.today()
    today_iso = today.isoformat()

    # Build current latest-price map (canonical ticker → native latest price).
    latest_prices: Dict[str, float] = {}
    latest_currency: Dict[str, str] = {}
    for ticker, payload in prices.items():
        if ticker.startswith("_"):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("latest_price") is None:
            continue
        latest_prices[ticker.upper()] = float(payload["latest_price"])
        if payload.get("currency"):
            latest_currency[ticker.upper()] = str(payload["currency"]).upper()

    history = prices.get("_history") or {}
    fx_history = prices.get("_fx_history") or {}
    fx_current_payload = prices.get("_fx") or {}
    fx_current: Dict[str, float] = {}
    if isinstance(fx_current_payload, dict):
        for k, v in fx_current_payload.get("rates", {}).items():
            try:
                fx_current[k] = float(v)
            except (TypeError, ValueError):
                continue

    # Final state at today
    final_state = replay(txns, cutoff=today_iso)
    end_value, end_audit = _value_state(final_state, latest_prices, fx_current, base)
    end_unrealized, end_unrealized_audit = _unrealized_pnl_state(
        final_state, latest_prices, fx_current, base, today_iso
    )

    # Market lookup (ticker → market code) for the per-market period decomposition.
    market_map = _market_by_ticker(txns, final_state)
    end_unrealized_by_market = _unrealized_pnl_state_by_market(
        final_state, latest_prices, fx_current, base, market_map
    )
    gross_market_audit: List[str] = []
    end_gross_by_m = _gross_position_value_by_market(
        final_state, latest_prices, fx_current, base, market_map, gross_market_audit
    )

    boundaries = period_boundaries(today)
    earliest = _earliest_txn_date(txns)
    if earliest:
        boundaries["ALLTIME"] = _date(earliest)
    period_order = ["1D", "7D", "MTD", "1M", "YTD", "1Y", "ALLTIME"]

    rows: List[Dict[str, Any]] = []
    for period in period_order:
        if period not in boundaries:
            rows.append({
                "period": period, "pnl": None, "return_pct": None,
                "realized": None, "unrealized_delta": None, "net_flows": None,
                "starting_value": None, "ending_value": end_value,
                "per_market": {},
                "per_market_detail": {},
                "audit": ["no transactions yet"],
            })
            continue

        boundary = boundaries[period]
        boundary_iso = boundary.isoformat()
        if boundary_iso > today_iso:
            boundary_iso = today_iso

        period_audit: List[str] = []
        if period == "ALLTIME":
            # ALLTIME starts before the first event, so every DEPOSIT/WITHDRAW
            # is an external flow and there is no boundary portfolio value or
            # boundary unrealized P&L to subtract.
            starting_value = 0.0
            starting_unrealized = 0.0
            starting_unrealized_by_market: Dict[str, float] = {}
            start_gross_by_m: Dict[str, float] = {}
            start_inclusive = "0001-01-01"
        else:
            # State at boundary (inclusive)
            boundary_state = replay(txns, cutoff=boundary_iso)

            # Boundary FX
            fx_at_boundary, fx_audit = _fx_at(boundary_iso, fx_current, fx_history)
            period_audit.extend(fx_audit)

            # Boundary prices: historical close per ticker held in boundary_state
            boundary_prices: Dict[str, float] = {}
            for ticker, lots in boundary_state.open_lots.items():
                if not lots:
                    continue
                close = _historical_close(history, ticker, boundary_iso)
                if close is None:
                    # Fall back to latest price as a last resort with audit note
                    fallback = latest_prices.get(ticker)
                    if fallback is not None:
                        boundary_prices[ticker] = fallback
                        period_audit.append(f"{ticker}: no historical close at {boundary_iso}; using current latest")
                    else:
                        period_audit.append(f"{ticker}: no historical close at {boundary_iso} and no latest price")
                else:
                    boundary_prices[ticker] = close

            starting_value, val_audit = _value_state(
                boundary_state, boundary_prices, fx_at_boundary, base
            )
            period_audit.extend(val_audit)
            starting_unrealized, su_audit = _unrealized_pnl_state(
                boundary_state, boundary_prices, fx_at_boundary, base, boundary_iso
            )
            period_audit.extend(su_audit)
            starting_unrealized_by_market = _unrealized_pnl_state_by_market(
                boundary_state, boundary_prices, fx_at_boundary, base, market_map
            )
            start_gross_by_m = _gross_position_value_by_market(
                boundary_state, boundary_prices, fx_at_boundary, base, market_map, period_audit
            )
            start_inclusive = (_date(boundary_iso) + _dt.timedelta(days=1)).isoformat()

        # External flows in period.
        flow_audit: List[str] = []
        flows = _net_external_flows(
            txns,
            start_inclusive,
            today_iso,
            fx_current, base, flow_audit,
        )
        period_audit.extend(flow_audit)

        # Realized in period (whole-portfolio + per-market).
        realized_audit: List[str] = []
        realized = _realized_in_period(
            final_state,
            start_inclusive,
            today_iso,
            fx_current, base, realized_audit,
        )
        period_audit.extend(realized_audit)
        realized_by_market = _realized_in_period_by_market(
            final_state, start_inclusive, today_iso,
            fx_current, base, market_map, realized_audit,
        )

        pnl = end_value - starting_value - flows
        denom = starting_value + 0.5 * flows
        ret = (pnl / denom) if abs(denom) > 1e-6 else None

        unrealized_delta = end_unrealized - starting_unrealized
        component_gap = pnl - (realized + unrealized_delta)

        # Decompose the residual into named drift components so the agent can
        # tell mechanical FX-translation drift apart from genuine unmodelled
        # cash events. ALLTIME has no boundary state, so fx_drift is 0 by
        # construction; the entire residual is then cash-side.
        #
        # Caveat: when `_fx_at` falls back to current rates (no FX history at
        # the boundary), `fx_at_boundary == fx_current`, so `starting_value`
        # and `starting_value_curfx` agree and `fx_drift` collapses to ~0.
        # The whole residual is then reported as `cash_drift` even though
        # part of it could be unobserved FX motion. The audit line emitted by
        # `_fx_at` flags the missing history; consumers should treat
        # cash_drift>0 *with* an "no _fx_history" audit on the same row as
        # ambiguous, not as a confirmed cash gap.
        fx_drift = 0.0
        cash_drift = component_gap
        if period != "ALLTIME":
            starting_value_curfx, _ = _value_state(
                boundary_state, boundary_prices, fx_current, base
            )
            starting_unrealized_curfx, _ = _unrealized_pnl_state(
                boundary_state, boundary_prices, fx_current, base, boundary_iso
            )
            pnl_curfx = end_value - starting_value_curfx - flows
            ud_curfx = end_unrealized - starting_unrealized_curfx
            residual_curfx = pnl_curfx - (realized + ud_curfx)
            fx_drift = component_gap - residual_curfx
            cash_drift = residual_curfx

        if abs(component_gap) > 1.0:
            # Keep the legacy audit phrasing so report_accuracy._reconciliation_gaps
            # still penalises real reconciliation drift, then attach the structured
            # decomposition as a sibling line.
            period_audit.append(
                f"{period}: P&L differs from realized + unrealized_delta by {component_gap:.2f} "
                "(cash/FX drift or missing marks)"
            )
            period_audit.append(
                f"{period}: residual {component_gap:.2f} = "
                f"fx_drift {fx_drift:.2f} + cash_drift {cash_drift:.2f}"
            )

        # Per-market P&L decomposition: realized_in_period + unrealized_delta.
        # Cash/FX residual lives at portfolio level and is NOT distributed across
        # markets (deposits are not attributable to a market). Sum of per-market
        # P&L therefore differs from `pnl` by `pnl - realized - unrealized_delta`.
        per_market_keys = (
            set(realized_by_market)
            | set(end_unrealized_by_market)
            | set(starting_unrealized_by_market)
            | set(end_gross_by_m)
            | set(start_gross_by_m)
        )
        per_market: Dict[str, float] = {}
        per_market_detail: Dict[str, Dict[str, Any]] = {}
        for k in per_market_keys:
            r = realized_by_market.get(k, 0.0)
            ud = end_unrealized_by_market.get(k, 0.0) - starting_unrealized_by_market.get(k, 0.0)
            value = r + ud
            s_m = start_gross_by_m.get(k, 0.0)
            e_m = end_gross_by_m.get(k, 0.0)
            eps = _PROFIT_PANEL_MARKET_RETURN_EPS
            denom = max(abs(s_m), eps)
            if abs(s_m) < 1e-12 and abs(value) < 0.01:
                ret_m = None
            elif abs(s_m) < 1e-12:
                ret_m = None
            else:
                ret_m = round((value / denom) * 100.0, 4)
            per_market_detail[k] = {
                "pnl": round(value, 2),
                "realized": round(r, 2),
                "unrealized_delta": round(ud, 2),
                "return_pct": ret_m,
                "starting_position_value": round(s_m, 2),
                "ending_position_value": round(e_m, 2),
                "net_flows": None,
            }
            if abs(value) < 0.01:
                continue
            per_market[k] = round(value, 2)

        rows.append({
            "period": period,
            "boundary": boundary_iso,
            "starting_value": round(starting_value, 2),
            "ending_value": round(end_value, 2),
            "pnl": round(pnl, 2),
            "return_pct": round(ret * 100.0, 4) if ret is not None else None,
            "realized": round(realized, 2),
            "unrealized_delta": round(unrealized_delta, 2),
            "net_flows": round(flows, 2),
            "fx_drift": round(fx_drift, 2),
            "cash_drift": round(cash_drift, 2),
            "per_market": per_market,
            "per_market_detail": per_market_detail,
            "audit": period_audit,
        })

    return {
        "base_currency": base,
        "as_of": today_iso,
        "rows": rows,
        "open_position_audit": end_audit + end_unrealized_audit + gross_market_audit,
        "issues": final_state.issues,
    }


# --------------------------------------------------------------------------- #
# Pure realized + unrealized snapshot (no historical needed)
# --------------------------------------------------------------------------- #

def compute_realized_unrealized(
    txns: List[Transaction],
    prices: Dict[str, Any],
    *,
    base: str = "USD",
) -> Dict[str, Any]:
    """Compute lifetime realized + current unrealized P&L in base currency."""
    state = replay(txns)
    fx_payload = prices.get("_fx") or {}
    fx_rates: Dict[str, float] = {}
    if isinstance(fx_payload, dict):
        for k, v in fx_payload.get("rates", {}).items():
            try:
                fx_rates[k] = float(v)
            except (TypeError, ValueError):
                continue

    audit: List[str] = []
    realized_total = 0.0
    realized_breakdown = {"sell": 0.0, "dividend": 0.0, "fee": 0.0}
    for ev in state.realized_events:
        rate = _fx_rate(fx_rates, base, ev.currency, audit)
        if rate is None:
            continue
        base_amount = ev.realized_native / rate
        realized_total += base_amount
        if ev.type == "SELL_LOT":
            realized_breakdown["sell"] += base_amount
        elif ev.type == "DIVIDEND":
            realized_breakdown["dividend"] += base_amount
        elif ev.type == "FEE":
            realized_breakdown["fee"] += base_amount

    unrealized_total = 0.0
    per_ticker: Dict[str, float] = {}
    for ticker, lots in state.open_lots.items():
        payload = prices.get(ticker) or prices.get(ticker.upper()) or {}
        latest = payload.get("latest_price")
        if latest is None:
            audit.append(f"no latest price for {ticker}; unrealized excluded")
            continue
        ccy = lots[0].currency if lots else "USD"
        rate = _fx_rate(fx_rates, base, ccy, audit)
        if rate is None:
            continue
        u_native = sum((float(latest) - lot.cost) * lot.qty for lot in lots)
        u_base = u_native / rate
        unrealized_total += u_base
        per_ticker[ticker] = round(u_base, 2)

    return {
        "base_currency": base,
        "realized": round(realized_total, 2),
        "realized_breakdown": {k: round(v, 2) for k, v in realized_breakdown.items()},
        "unrealized": round(unrealized_total, 2),
        "unrealized_per_ticker": per_ticker,
        "total_pnl": round(realized_total + unrealized_total, 2),
        "audit": audit,
        "issues": state.issues,
    }


# --------------------------------------------------------------------------- #
# Transaction analytics: performance attribution, trade quality, discipline
# --------------------------------------------------------------------------- #

def _market_by_ticker(txns: List[Transaction], state: ReplayState) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for t in txns:
        if t.ticker and t.market:
            out[t.ticker] = t.market
    for ticker, lots in state.open_lots.items():
        if lots:
            out[ticker] = lots[0].market
    return out


def _asset_class_for_market(market: Optional[str]) -> str:
    """Return a stable, market-specific asset-class code.

    The renderer translates each code via `analytics.asset_class_<code>`. We
    keep the codes lowercase so they're locale-stable and pre-existing
    `analytics.asset_class_other` / `_cash` / `_fx` / `_crypto` keep working.
    """
    m = (market or "").upper()
    if m == "US":
        return "us"
    if m == "TW":
        return "tw"
    if m == "TWO":
        return "two"
    if m == "JP":
        return "jp"
    if m == "HK":
        return "hk"
    if m == "LSE":
        return "lse"
    if m == "CRYPTO":
        return "crypto"
    if m == "FX":
        return "fx"
    if m == "CASH":
        return "cash"
    return "other"


def _historical_close_on_or_after(
    history: Dict[str, List[Dict[str, Any]]],
    ticker: str,
    on_or_after: str,
) -> Optional[Tuple[str, float]]:
    series = history.get(ticker) or history.get(ticker.upper())
    if not series:
        return None
    best: Optional[Dict[str, Any]] = None
    for row in series:
        d = row.get("date")
        if d and d >= on_or_after:
            if best is None or d < best["date"]:
                best = row
    if best is None:
        return None
    try:
        return str(best.get("date")), float(best.get("close"))
    except (TypeError, ValueError):
        return None


def _money_weighted_return(
    txns: List[Transaction],
    ending_value: float,
    fx: Dict[str, float],
    base: str,
    today: _dt.date,
    audit: List[str],
) -> Optional[float]:
    """Annualized money-weighted return from external flows plus ending NAV.

    Investor perspective: deposits are negative cash flows, withdrawals and
    ending NAV are positive. Returns a ratio (0.10 = 10%), or None when the
    flow pattern is not solvable.
    """
    flows: List[Tuple[_dt.date, float]] = []
    for t in txns:
        if t.type not in EXTERNAL_FLOW_TYPES:
            continue
        amount = t.amount or 0.0
        ccy = (t.cash_account or t.currency or "USD").upper()
        rate = _fx_rate(fx, base, ccy, audit)
        if rate is None:
            continue
        signed = -amount / rate if t.type == "DEPOSIT" else amount / rate
        flows.append((_date(t.date), signed))
    flows.append((today, ending_value))
    if len(flows) < 2 or not any(v < 0 for _, v in flows) or not any(v > 0 for _, v in flows):
        return None
    start = min(d for d, _ in flows)

    def npv(rate: float) -> float:
        total = 0.0
        for d, value in flows:
            years = max((d - start).days / 365.25, 0.0)
            total += value / ((1.0 + rate) ** years)
        return total

    lo, hi = -0.999, 10.0
    n_lo, n_hi = npv(lo), npv(hi)
    if n_lo == 0:
        return lo
    if n_hi == 0:
        return hi
    if n_lo * n_hi > 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2.0
        n_mid = npv(mid)
        if abs(n_mid) < 1e-7:
            return mid
        if n_lo * n_mid <= 0:
            hi = mid
            n_hi = n_mid
        else:
            lo = mid
            n_lo = n_mid
    return (lo + hi) / 2.0


def compute_transaction_analytics(
    txns: List[Transaction],
    prices: Dict[str, Any],
    *,
    base: str = "USD",
    today: Optional[_dt.date] = None,
) -> Dict[str, Any]:
    """Higher-level analytics for report sections driven by transaction history."""
    today = today or _dt.date.today()
    today_iso = today.isoformat()
    history = prices.get("_history") or {}
    fx_history = prices.get("_fx_history") or {}
    fx_payload = prices.get("_fx") or {}
    fx_current: Dict[str, float] = {}
    if isinstance(fx_payload, dict):
        for k, v in fx_payload.get("rates", {}).items():
            try:
                fx_current[k] = float(v)
            except (TypeError, ValueError):
                continue

    latest_prices: Dict[str, float] = {}
    for ticker, payload in prices.items():
        if ticker.startswith("_") or not isinstance(payload, dict):
            continue
        if payload.get("latest_price") is None:
            continue
        latest_prices[ticker.upper()] = float(payload["latest_price"])

    state = replay(txns, cutoff=today_iso)
    ending_value, value_audit = _value_state(state, latest_prices, fx_current, base)
    panel = compute_profit_panel(txns, prices, base=base, today=today)
    mwr_audit: List[str] = []
    mwr = _money_weighted_return(txns, ending_value, fx_current, base, today, mwr_audit)

    period_rows: List[Dict[str, Any]] = []
    for row in panel.get("rows", []):
        pnl = row.get("pnl")
        realized = row.get("realized")
        unrealized = row.get("unrealized_delta")
        residual = None
        if pnl is not None and realized is not None and unrealized is not None:
            residual = round(float(pnl) - float(realized) - float(unrealized), 2)
        out = dict(row)
        out["residual"] = residual
        period_rows.append(out)

    market_map = _market_by_ticker(txns, state)
    realized_by_ticker: Dict[str, float] = {}
    realized_by_class: Dict[str, float] = {}
    realized_values: List[float] = []
    sell_events: List[RealizedEvent] = []
    for ev in state.realized_events:
        rate = _fx_rate(fx_current, base, ev.currency, value_audit)
        if rate is None:
            continue
        value = ev.realized_native / rate
        key = ev.ticker or ev.type.lower()
        realized_by_ticker[key] = realized_by_ticker.get(key, 0.0) + value
        asset_class = _asset_class_for_market(market_map.get(ev.ticker or ""))
        realized_by_class[asset_class] = realized_by_class.get(asset_class, 0.0) + value
        if ev.type == "SELL_LOT":
            sell_events.append(ev)
            realized_values.append(value)

    unrealized_by_ticker: Dict[str, float] = {}
    unrealized_by_class: Dict[str, float] = {}
    open_lot_rows: List[Dict[str, Any]] = []
    for ticker, lots in state.open_lots.items():
        latest = latest_prices.get(ticker)
        if latest is None:
            value_audit.append(f"missing latest price for {ticker}; analytics unrealized excluded")
            continue
        ccy = lots[0].currency if lots else "USD"
        rate = _fx_rate(fx_current, base, ccy, value_audit)
        if rate is None:
            continue
        asset_class = _asset_class_for_market(market_map.get(ticker))
        for lot in lots:
            unrealized = (latest - lot.cost) * lot.qty / rate
            unrealized_by_ticker[ticker] = unrealized_by_ticker.get(ticker, 0.0) + unrealized
            unrealized_by_class[asset_class] = unrealized_by_class.get(asset_class, 0.0) + unrealized
            hold_days = (today - _date(lot.acq_date)).days
            open_lot_rows.append({
                "ticker": ticker,
                "acq_date": lot.acq_date,
                "qty": round(lot.qty, 8),
                "cost": round(lot.cost, 6),
                "latest": round(latest, 6),
                "unrealized": round(unrealized, 2),
                "unrealized_pct": round((latest - lot.cost) / lot.cost * 100.0, 2) if lot.cost else None,
                "hold_days": hold_days,
                "bucket": lot.bucket,
            })

    ticker_contrib: Dict[str, float] = {}
    for ticker, value in realized_by_ticker.items():
        ticker_contrib[ticker] = ticker_contrib.get(ticker, 0.0) + value
    for ticker, value in unrealized_by_ticker.items():
        ticker_contrib[ticker] = ticker_contrib.get(ticker, 0.0) + value
    contributor_rows = [
        {
            "ticker": ticker,
            "total_pnl": round(value, 2),
            "realized": round(realized_by_ticker.get(ticker, 0.0), 2),
            "unrealized": round(unrealized_by_ticker.get(ticker, 0.0), 2),
        }
        for ticker, value in ticker_contrib.items()
    ]
    contributor_rows.sort(key=lambda r: r["total_pnl"], reverse=True)

    class_rows = []
    class_keys = set(realized_by_class) | set(unrealized_by_class)
    for key in sorted(class_keys):
        realized = realized_by_class.get(key, 0.0)
        unrealized = unrealized_by_class.get(key, 0.0)
        class_rows.append({
            "asset_class": key,
            "total_pnl": round(realized + unrealized, 2),
            "realized": round(realized, 2),
            "unrealized": round(unrealized, 2),
        })
    class_rows.sort(key=lambda r: abs(r["total_pnl"]), reverse=True)

    wins = [v for v in realized_values if v > 0]
    losses = [v for v in realized_values if v < 0]
    avg_hold_days_values = [
        (_date(ev.date) - _date(ev.acq_date)).days
        for ev in sell_events
        if ev.acq_date
    ]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else None

    sell_followups: List[Dict[str, Any]] = []
    for ev in sell_events:
        if ev.sell_price is None or ev.ticker is None:
            continue
        item: Dict[str, Any] = {
            "ticker": ev.ticker,
            "sell_date": ev.date,
            "qty": round(ev.qty, 8),
            "sell_price": round(ev.sell_price, 6),
            "realized": round(ev.realized_native, 2),
        }
        for days in (30, 90):
            target = (_date(ev.date) + _dt.timedelta(days=days)).isoformat()
            if target > today_iso:
                item[f"after_{days}d_pct"] = None
                item[f"after_{days}d_pnl"] = None
                continue
            future = _historical_close_on_or_after(history, ev.ticker, target)
            if future is None:
                item[f"after_{days}d_pct"] = None
                item[f"after_{days}d_pnl"] = None
                continue
            _, close = future
            native = (close - ev.sell_price) * ev.qty
            rate = _fx_rate(fx_current, base, ev.currency, value_audit)
            item[f"after_{days}d_pct"] = round((close - ev.sell_price) / ev.sell_price * 100.0, 2)
            item[f"after_{days}d_pnl"] = round(native / rate, 2) if rate else None
        sell_followups.append(item)
    sell_followups.sort(key=lambda r: abs(r.get("after_90d_pnl") or r.get("after_30d_pnl") or 0), reverse=True)

    buy_followups: List[Dict[str, Any]] = []
    for t in txns:
        if t.type != "BUY" or not t.ticker or not t.price or not t.qty:
            continue
        item = {"ticker": t.ticker, "buy_date": t.date, "qty": round(t.qty, 8), "buy_price": round(t.price, 6)}
        for days in (30, 90):
            target = (_date(t.date) + _dt.timedelta(days=days)).isoformat()
            if target > today_iso:
                item[f"after_{days}d_pct"] = None
                continue
            future = _historical_close_on_or_after(history, t.ticker, target)
            item[f"after_{days}d_pct"] = (
                round((future[1] - t.price) / t.price * 100.0, 2) if future else None
            )
        buy_followups.append(item)
    buy_followups.sort(key=lambda r: abs(r.get("after_90d_pct") or r.get("after_30d_pct") or 0), reverse=True)

    # Combined chronological recent-activity feed (BUY + SELL together,
    # most recent first). This is the daily-useful view: did my latest sells
    # leave money on the table, did my latest buys immediately tank? The
    # parallel sell/buy follow-up tables above are kept for back-compat but
    # not surfaced by the renderer.
    recent_activity: List[Dict[str, Any]] = []
    for t in txns:
        if t.ticker is None or t.price is None or t.qty is None:
            continue
        if t.type not in ("BUY", "SELL"):
            continue
        item: Dict[str, Any] = {
            "date": t.date,
            "action": t.type,
            "ticker": t.ticker,
            "qty": round(t.qty, 8),
            "price": round(t.price, 6),
            "currency": (t.currency or "USD").upper(),
            "market": t.market,
        }
        if t.type == "SELL":
            # Aggregate realized across the matching SELL_LOT events for this txn
            # (one SELL transaction can drain multiple lots → multiple events).
            realized_native = sum(
                ev.realized_native for ev in state.realized_events
                if ev.type == "SELL_LOT" and ev.ticker == t.ticker and ev.date == t.date
            )
            rate = _fx_rate(fx_current, base, t.currency or "USD", value_audit)
            item["realized"] = round(realized_native / rate, 2) if rate else None
        for days in (30, 90):
            target = (_date(t.date) + _dt.timedelta(days=days)).isoformat()
            if target > today_iso:
                item[f"after_{days}d_pct"] = None
                continue
            future = _historical_close_on_or_after(history, t.ticker, target)
            if future is None:
                item[f"after_{days}d_pct"] = None
            else:
                _, close = future
                item[f"after_{days}d_pct"] = round((close - t.price) / t.price * 100.0, 2)
        recent_activity.append(item)
    recent_activity.sort(key=lambda r: r["date"], reverse=True)

    deposits = [t for t in txns if t.type == "DEPOSIT"]
    sells = [t for t in txns if t.type == "SELL"]
    buys = [t for t in txns if t.type == "BUY"]

    def _days_to_next_buy(start_date: str) -> Optional[int]:
        future = [b for b in buys if b.date >= start_date]
        if not future:
            return None
        return (_date(future[0].date) - _date(start_date)).days

    deposit_deploy_days = [d for d in (_days_to_next_buy(t.date) for t in deposits) if d is not None]
    sell_redeploy_days = [d for d in (_days_to_next_buy(t.date) for t in sells) if d is not None]

    ticker_values: Dict[str, float] = {}
    for ticker, lots in state.open_lots.items():
        latest = latest_prices.get(ticker)
        if latest is None or not lots:
            continue
        rate = _fx_rate(fx_current, base, lots[0].currency, value_audit)
        if rate is None:
            continue
        ticker_values[ticker] = sum(l.qty for l in lots) * latest / rate
    concentration_rows = [
        {"ticker": ticker, "weight_pct": round(value / ending_value * 100.0, 2) if ending_value else None}
        for ticker, value in ticker_values.items()
    ]
    concentration_rows.sort(key=lambda r: r.get("weight_pct") or 0, reverse=True)

    recent_cutoff = (today - _dt.timedelta(days=30)).isoformat()
    recent_buys: Dict[str, int] = {}
    for t in buys:
        if t.date >= recent_cutoff and t.ticker:
            recent_buys[t.ticker] = recent_buys.get(t.ticker, 0) + 1

    short_stale = [
        r for r in open_lot_rows
        if str(r.get("bucket", "")).lower().startswith("short") and (r.get("hold_days") or 0) > 365
    ]
    high_cost_lots = sorted(open_lot_rows, key=lambda r: r.get("unrealized") or 0)[:8]
    best_lots = sorted(open_lot_rows, key=lambda r: r.get("unrealized") or 0, reverse=True)[:8]

    latest_cost_flags: List[Dict[str, Any]] = []
    for ticker, lots in state.open_lots.items():
        sorted_lots = sorted(lots, key=lambda l: l.acq_date)
        if len(sorted_lots) < 2:
            continue
        newest = sorted_lots[-1]
        older = sorted_lots[:-1]
        older_qty = sum(l.qty for l in older)
        if older_qty <= 1e-9:
            continue
        older_avg = sum(l.cost * l.qty for l in older) / older_qty
        if newest.cost > older_avg * 1.10:
            latest_cost_flags.append({
                "ticker": ticker,
                "newest_date": newest.acq_date,
                "newest_cost": round(newest.cost, 6),
                "older_avg_cost": round(older_avg, 6),
                "premium_pct": round((newest.cost / older_avg - 1.0) * 100.0, 2),
            })

    data_gaps = []
    for ticker, lots in state.open_lots.items():
        if ticker not in latest_prices:
            data_gaps.append(f"missing latest price for {ticker}")
        if ticker not in history:
            data_gaps.append(f"missing historical prices for {ticker}")
        for lot in lots:
            if lot.currency != base and f"{base}/{lot.currency}" not in fx_current:
                data_gaps.append(f"missing FX {base}/{lot.currency}")
    data_gaps.extend(value_audit)
    data_gaps.extend(mwr_audit)
    deduped_gaps: List[str] = []
    for gap in data_gaps:
        if gap and gap not in deduped_gaps:
            deduped_gaps.append(gap)

    return {
        "base_currency": base,
        "as_of": today_iso,
        "performance_attribution": {
            "ending_nav": round(ending_value, 2),
            "money_weighted_return_annualized": round(mwr * 100.0, 2) if mwr is not None else None,
            "periods": period_rows,
            "top_contributors": contributor_rows[:8],
            "top_detractors": sorted(contributor_rows, key=lambda r: r["total_pnl"])[:8],
            "asset_class_contribution": class_rows,
        },
        "trade_quality": {
            "closed_lot_count": len(sell_events),
            "win_rate_pct": round(len(wins) / len(realized_values) * 100.0, 2) if realized_values else None,
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
            "avg_realized": round(sum(realized_values) / len(realized_values), 2) if realized_values else None,
            "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
            "avg_hold_days": round(sum(avg_hold_days_values) / len(avg_hold_days_values), 1) if avg_hold_days_values else None,
            "sell_followups": sell_followups[:12],
            "buy_followups": buy_followups[:12],
            "recent_activity": recent_activity[:12],
        },
        "discipline_check": {
            "avg_days_deposit_to_buy": round(sum(deposit_deploy_days) / len(deposit_deploy_days), 1) if deposit_deploy_days else None,
            "avg_days_sell_to_buy": round(sum(sell_redeploy_days) / len(sell_redeploy_days), 1) if sell_redeploy_days else None,
            "top_position_weights": concentration_rows[:8],
            "recent_buy_counts_30d": [
                {"ticker": ticker, "count": count}
                for ticker, count in sorted(recent_buys.items(), key=lambda kv: -kv[1])
                if count >= 3
            ],
            "short_bucket_over_1y": short_stale[:8],
            "latest_lot_cost_flags": latest_cost_flags[:8],
            "largest_unrealized_losses": high_cost_lots,
            "largest_unrealized_gains": best_lots,
            "data_gaps": deduped_gaps,
        },
    }


# --------------------------------------------------------------------------- #
# Self-check unit tests
# --------------------------------------------------------------------------- #

def _selfcheck() -> int:
    failures: List[str] = []

    # 1. Parser: heading + fields + lots block
    sample = """\
# Transactions

## 2026-04-10 BUY NVDA
- qty: 30
- price: $211.208
- net: $6336.24
- bucket: Mid Term
- market: US
- currency: USD
- cash_account: USD
- rationale: AI capex
- tags: ai, semis

## 2026-04-29 SELL NVDA
- qty: 5
- price: $215.50
- fees: 1.00
- lots:
    - 2026-04-10@$211.208: 5
- realized_pnl: $20.46
- bucket: Mid Term
- market: US
- currency: USD
- cash_account: USD

## 2026-04-15 DEPOSIT
- amount: $5000
- currency: USD
- cash_account: USD

## 2026-04-12 DIVIDEND GOOG
- amount: $80
- currency: USD
- cash_account: USD
"""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(sample)
        tmp = Path(f.name)

    txns = parse_transactions(tmp)
    if len(txns) != 4:
        failures.append(f"parse: expected 4 txns, got {len(txns)}")
    if txns and txns[0].type != "BUY":
        failures.append(f"parse: expected first BUY, got {txns[0].type}")
    if txns and txns[1].type != "SELL":
        failures.append(f"parse: expected second SELL, got {txns[1].type}")
    if txns and len(txns[1].lots_consumed) != 1:
        failures.append("parse: expected 1 lot consumption on SELL")

    # 2. Replay: positions + realized
    state = replay(txns)
    if abs(state.cash.get("USD", 0.0) - (5000 - 6336.24 + 80 + (5 * 215.50 - 1.00))) > 1e-2:
        failures.append(f"replay: USD cash drift: {state.cash}")
    nvda_lots = state.open_lots.get("NVDA", [])
    nvda_open_qty = sum(l.qty for l in nvda_lots)
    if abs(nvda_open_qty - 25) > 1e-6:
        failures.append(f"replay: NVDA open qty expected 25, got {nvda_open_qty}")

    # 3. Realized P&L
    realized_native = sum(ev.realized_native for ev in state.realized_events if ev.type == "SELL_LOT")
    expected_realized = (215.50 - 211.208) * 5
    if abs(realized_native - expected_realized) > 1e-2:
        failures.append(f"realized: expected {expected_realized}, got {realized_native}")

    # 4. compute_realized_unrealized
    fake_prices = {
        "NVDA": {"latest_price": 220.0, "currency": "USD"},
        "_fx": {"rates": {}},
    }
    snap = compute_realized_unrealized(txns, fake_prices, base="USD")
    expected_unrealized = (220.0 - 211.208) * 25
    if abs(snap["unrealized"] - round(expected_unrealized, 2)) > 0.05:
        failures.append(f"unrealized: expected {expected_unrealized}, got {snap['unrealized']}")
    fees_term = -1.00
    div_term = 80.0
    expected_realized_total = (215.50 - 211.208) * 5 + fees_term + div_term
    if abs(snap["realized"] - round(expected_realized_total, 2)) > 0.05:
        failures.append(f"realized total: expected {expected_realized_total}, got {snap['realized']}")

    analytics_prices = {
        "NVDA": {"latest_price": 220.0, "currency": "USD"},
        "_fx": {"rates": {}},
        "_history": {
            "NVDA": [
                {"date": "2026-04-29", "close": 215.50},
                {"date": "2026-04-30", "close": 220.00},
            ],
        },
    }
    analytics = compute_transaction_analytics(txns, analytics_prices, base="USD", today=_dt.date(2026, 4, 30))
    tq = analytics.get("trade_quality", {})
    if tq.get("closed_lot_count") != 1:
        failures.append(f"analytics: closed_lot_count expected 1, got {tq.get('closed_lot_count')}")
    if tq.get("win_rate_pct") != 100.0:
        failures.append(f"analytics: win_rate_pct expected 100, got {tq.get('win_rate_pct')}")
    pa = analytics.get("performance_attribution", {})
    if not pa.get("top_contributors"):
        failures.append("analytics: expected top contributors")

    # 5. Period boundaries
    today = _dt.date(2026, 4, 30)
    bounds = period_boundaries(today)
    if bounds["1D"] != _dt.date(2026, 4, 29):
        failures.append(f"1D boundary wrong: {bounds['1D']}")
    if bounds["YTD"] != _dt.date(2025, 12, 31):
        failures.append(f"YTD boundary wrong: {bounds['YTD']}")
    if bounds["MTD"] != _dt.date(2026, 3, 31):
        failures.append(f"MTD boundary wrong: {bounds['MTD']}")
    if bounds["1M"] != _dt.date(2026, 3, 30):
        failures.append(f"1M boundary wrong: {bounds['1M']}")
    if bounds["1Y"] != _dt.date(2025, 4, 30):
        failures.append(f"1Y boundary wrong: {bounds['1Y']}")

    # 6. compute_profit_panel — basic shape
    fake_prices_full = {
        "NVDA": {"latest_price": 220.0, "currency": "USD"},
        "_fx": {"rates": {}},
        "_history": {
            "NVDA": [
                {"date": "2026-04-29", "close": 215.50},
                {"date": "2026-04-28", "close": 213.00},
            ],
        },
    }
    panel = compute_profit_panel(txns, fake_prices_full, base="USD", today=_dt.date(2026, 4, 30))
    if not panel.get("rows"):
        failures.append("profit_panel: no rows produced")
    elif panel["rows"][0]["period"] != "1D":
        failures.append(f"profit_panel: first period should be 1D, got {panel['rows'][0]['period']}")
    alltime_row = next((r for r in panel.get("rows", []) if r.get("period") == "ALLTIME"), None)
    if not alltime_row:
        failures.append("profit_panel: ALLTIME row missing")
    elif abs((alltime_row.get("net_flows") or 0) - 5000.0) > 1e-6:
        failures.append(f"profit_panel: ALLTIME net_flows should include first-day/whole-history deposits, got {alltime_row.get('net_flows')}")
    r1 = panel["rows"][0]
    pmd = r1.get("per_market_detail") or {}
    if not pmd:
        failures.append("profit_panel: per_market_detail missing on rows")
    else:
        usd = pmd.get("us")
        if not isinstance(usd, dict):
            failures.append("profit_panel: per_market_detail.us not a dict")
        elif usd.get("net_flows") is not None:
            failures.append("profit_panel: per_market_detail.us.net_flows should be null in v1")
        else:
            pnl_u = float(usd.get("pnl") or 0.0)
            comb = float(usd.get("realized") or 0.0) + float(usd.get("unrealized_delta") or 0.0)
            if abs(pnl_u - comb) > 0.02:
                failures.append(f"profit_panel: us pnl {pnl_u} != realized+unrealized {comb}")

    sold_lot_sample = """\
# Transactions

## 2026-04-01 DEPOSIT
- amount: $10000
- currency: USD
- cash_account: USD

## 2026-04-01 BUY ABC
- qty: 10
- price: $80
- bucket: Mid Term
- market: US
- currency: USD
- cash_account: USD

## 2026-04-29 SELL ABC
- qty: 10
- price: $120
- bucket: Mid Term
- market: US
- currency: USD
- cash_account: USD
"""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(sold_lot_sample)
        tmp_sold = Path(f.name)
    sold_prices = {
        "ABC": {"latest_price": 130.0, "currency": "USD"},
        "_fx": {"rates": {}},
        "_history": {"ABC": [{"date": "2026-04-23", "close": 100.0}]},
    }
    sold_panel = compute_profit_panel(parse_transactions(tmp_sold), sold_prices, base="USD", today=_dt.date(2026, 4, 30))
    sold_7d = next((r for r in sold_panel.get("rows", []) if r.get("period") == "7D"), None)
    if not sold_7d:
        failures.append("profit_panel sold lot: 7D row missing")
    else:
        if abs((sold_7d.get("realized") or 0) - 400.0) > 1e-6:
            failures.append(f"profit_panel sold lot: realized expected 400, got {sold_7d.get('realized')}")
        if abs((sold_7d.get("unrealized_delta") or 0) - (-200.0)) > 1e-6:
            failures.append(f"profit_panel sold lot: unrealized_delta expected -200, got {sold_7d.get('unrealized_delta')}")
        if abs((sold_7d.get("pnl") or 0) - 200.0) > 1e-6:
            failures.append(f"profit_panel sold lot: pnl expected 200, got {sold_7d.get('pnl')}")

    # 7. TW ticker with NT$ prefix round-trip
    tw_sample = """\
# Transactions

## 2026-04-29 BUY 2330
- qty: 50
- price: NT$2200
- bucket: Mid Term
- market: TW
- currency: TWD
- cash_account: TWD

## 2026-04-30 SELL 2330
- qty: 20
- price: NT$2300
- bucket: Mid Term
- market: TW
- currency: TWD
- cash_account: TWD
"""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(tw_sample)
        tmp_tw = Path(f.name)
    tw_txns = parse_transactions(tmp_tw)
    if len(tw_txns) != 2:
        failures.append(f"tw_round_trip: parsed {len(tw_txns)} txns, expected 2")
    elif abs((tw_txns[0].price or 0) - 2200.0) > 1e-6:
        failures.append(f"tw_round_trip: NT$ price not parsed: {tw_txns[0].price}")
    tw_state = replay(tw_txns)
    open_qty = sum(l.qty for lots in tw_state.open_lots.values() for l in lots)
    if abs(open_qty - 30) > 1e-6:
        failures.append(f"tw_round_trip: expected 30 open shares, got {open_qty}")

    # 8. SELL quantity overflow surfaces an issue
    overflow_sample = """\
# Transactions

## 2026-04-10 BUY ABC
- qty: 5
- price: $100
- bucket: Short Term
- market: US
- currency: USD
- cash_account: USD

## 2026-04-15 SELL ABC
- qty: 10
- price: $110
- bucket: Short Term
- market: US
- currency: USD
- cash_account: USD
"""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(overflow_sample)
        tmp_ov = Path(f.name)
    ov_state = replay(parse_transactions(tmp_ov))
    if not any("exceeds open" in i for i in ov_state.issues):
        failures.append("sell_overflow: no 'exceeds open' issue logged")
    if "ABC" in ov_state.open_lots:
        failures.append("sell_overflow: ABC lots should be drained even on overflow")

    # 9. Stablecoin via _fx_rate (TWD base, USDC native must triangulate via TWD/USD)
    audit_buf: List[str] = []
    rate = _fx_rate({"TWD/USD": 32.5}, "TWD", "USDC", audit_buf)
    if rate is None or abs(rate - 32.5) > 1e-6:
        failures.append(f"stablecoin: TWD/USDC rate via TWD/USD expected 32.5, got {rate}")

    # 10. FX_CONVERT moves cash atomically
    fx_sample = """\
# Transactions

## 2026-04-30 FX_CONVERT
- from_amount: $1000
- from_currency: USD
- from_cash_account: USD
- to_amount: NT$32500
- to_currency: TWD
- to_cash_account: TWD
- rate: 32.5
"""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(fx_sample)
        tmp_fx = Path(f.name)
    fx_state = replay(parse_transactions(tmp_fx))
    if abs(fx_state.cash.get("USD", 0) + 1000) > 1e-2:
        failures.append(f"fx_convert: USD cash expected -1000, got {fx_state.cash.get('USD')}")
    if abs(fx_state.cash.get("TWD", 0) - 32500) > 1e-2:
        failures.append(f"fx_convert: TWD cash expected 32500, got {fx_state.cash.get('TWD')}")

    # 11. Field name case insensitivity
    case_sample = """\
# Transactions

## 2026-04-30 DEPOSIT
- Amount: $500
- Currency: USD
- Cash_Account: USD
- Tags: cashflow
"""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(case_sample)
        tmp_c = Path(f.name)
    case_txns = parse_transactions(tmp_c)
    if not case_txns or case_txns[0].amount != 500:
        failures.append("case_insensitive: capitalized field names not normalized")

    # 12. SQLite roundtrip: import-md then load_transactions_db gives same replay state
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        md_path = td_path / "T.md"
        md_path.write_text(sample, encoding="utf-8")
        db_path = td_path / "t.db"
        db_init(db_path)
        inserted, errs = db_import_md(md_path, db_path)
        if errs or inserted != 4:
            failures.append(f"db_import_md: errs={errs}, inserted={inserted}")
        loaded = load_transactions_db(db_path)
        if len(loaded) != 4:
            failures.append(f"load_transactions_db: expected 4 txns, got {len(loaded)}")
        else:
            md_state = replay(parse_transactions(md_path))
            db_state = replay(loaded)
            md_open = sum(l.qty for lots in md_state.open_lots.values() for l in lots)
            db_open = sum(l.qty for lots in db_state.open_lots.values() for l in lots)
            if abs(md_open - db_open) > 1e-6:
                failures.append(f"db parity: open qty md={md_open} db={db_open}")
            if abs(md_state.cash.get("USD", 0) - db_state.cash.get("USD", 0)) > 1e-2:
                failures.append(
                    f"db parity: USD cash md={md_state.cash.get('USD')} db={db_state.cash.get('USD')}"
                )
            md_realized = sum(ev.realized_native for ev in md_state.realized_events
                              if ev.type == "SELL_LOT")
            db_realized = sum(ev.realized_native for ev in db_state.realized_events
                              if ev.type == "SELL_LOT")
            if abs(md_realized - db_realized) > 1e-2:
                failures.append(f"db parity: realized md={md_realized} db={db_realized}")

        # 13. CSV import: validation rejects missing required fields atomically
        csv_path = td_path / "bad.csv"
        csv_path.write_text(
            "date,type,ticker,qty,price,currency,cash_account\n"
            "2026-04-29,BUY,TSLA,5,$200,USD,USD\n"
            "2026-04-29,SELL,,,$300,USD,USD\n",  # missing ticker, qty
            encoding="utf-8",
        )
        db_csv = td_path / "csv.db"
        db_init(db_csv)
        inserted_c, errs_c = db_import_csv(csv_path, db_csv)
        if inserted_c != 0 or not errs_c:
            failures.append(f"csv import: expected validation failure, got inserted={inserted_c}")

        # 14. JSON import: SELL with embedded lots: block round-trips
        json_path = td_path / "good.json"
        json_path.write_text(json.dumps([
            {"date": "2026-04-10", "type": "DEPOSIT", "amount": 10000, "currency": "USD", "cash_account": "USD"},
            {"date": "2026-04-11", "type": "BUY", "ticker": "AAPL", "qty": 30,
             "price": 200, "currency": "USD", "cash_account": "USD",
             "bucket": "Mid Term", "market": "US"},
            {"date": "2026-04-15", "type": "SELL", "ticker": "AAPL", "qty": 10,
             "price": 220, "currency": "USD", "cash_account": "USD",
             "bucket": "Mid Term", "market": "US",
             "lots": [{"acq_date": "2026-04-11", "cost": 200, "qty": 10}]},
        ]), encoding="utf-8")
        db_json = td_path / "json.db"
        db_init(db_json)
        inserted_j, errs_j = db_import_json(json_path, db_json)
        if errs_j or inserted_j != 3:
            failures.append(f"json import: errs={errs_j}, inserted={inserted_j}")
        else:
            jstate = replay(load_transactions_db(db_json))
            j_realized = sum(ev.realized_native for ev in jstate.realized_events if ev.type == "SELL_LOT")
            if abs(j_realized - (220 - 200) * 10) > 1e-6:
                failures.append(f"json import: realized expected 200, got {j_realized}")

        # 15. db_add (message workflow): single record from JSON string
        db_msg = td_path / "msg.db"
        db_init(db_msg)
        inserted_m, errs_m = db_add(json.dumps({
            "date": "2026-04-30", "type": "DIVIDEND", "ticker": "GOOG",
            "amount": 80, "currency": "USD", "cash_account": "USD",
            "rationale": "Q1 GOOG", "tags": "dividend",
        }), db_msg)
        if errs_m or inserted_m != 1:
            failures.append(f"db_add: errs={errs_m}, inserted={inserted_m}")

        # 16. iteration-3: balance tables auto-rebuild after every import path.
        #     After db_import_md, open_lots and cash_balances must reflect the replay.
        conn = db_connect(db_path)
        try:
            ol_count = conn.execute("SELECT COUNT(*) AS n FROM open_lots").fetchone()["n"]
            cb_count = conn.execute("SELECT COUNT(*) AS n FROM cash_balances").fetchone()["n"]
            cb_usd = conn.execute(
                "SELECT amount FROM cash_balances WHERE currency='USD'"
            ).fetchone()
        finally:
            conn.close()
        if ol_count == 0:
            failures.append("v3 rebuild: open_lots is empty after db_import_md")
        if cb_count == 0:
            failures.append("v3 rebuild: cash_balances is empty after db_import_md")
        # USD cash from sample = 5000 + 80 + (5*215.50 - 1.00) - 30*211.208 = -250.04
        if cb_usd is None or abs(cb_usd["amount"] - (5000 + 80 + 5 * 215.50 - 1.00 - 30 * 211.208)) > 1e-2:
            failures.append(
                f"v3 rebuild: USD cash_balances drift (got {cb_usd['amount'] if cb_usd else None})"
            )

        # 17. iteration-3: load_holdings_lots returns Lot shape consumable by
        #     parse_holdings callers. Open NVDA lot must surface with qty 25.
        from fetch_prices import MarketType  # type: ignore[import-not-found]  # noqa: F401
        loaded_lots = load_holdings_lots(db_path)
        nvda_lots = [l for l in loaded_lots if l.ticker == "NVDA"]
        if not nvda_lots or abs(sum(l.quantity for l in nvda_lots) - 25) > 1e-6:
            failures.append(
                f"v3 load_holdings_lots: NVDA qty expected 25, "
                f"got {sum(l.quantity for l in nvda_lots) if nvda_lots else 0}"
            )
        cash_lots = [l for l in loaded_lots if l.bucket == "Cash Holdings" and l.ticker == "USD"]
        if not cash_lots:
            failures.append("v3 load_holdings_lots: USD cash row missing")

        # 18. iteration-3: db rebuild idempotent — running twice yields same row counts.
        before = db_rebuild_balances(db_path)
        again = db_rebuild_balances(db_path)
        if before != again:
            failures.append(f"v3 rebuild: not idempotent ({before} vs {again})")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("OK: transactions self-check passed.")
    return 0


# --------------------------------------------------------------------------- #
# SQLite store
# --------------------------------------------------------------------------- #

DEFAULT_DB_PATH = Path("transactions.db")
SCHEMA_VERSION = 3

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  date              TEXT    NOT NULL,
  type              TEXT    NOT NULL,
  ticker            TEXT,
  qty               REAL,
  price             REAL,
  gross             REAL,
  fees              REAL    DEFAULT 0,
  net               REAL,
  amount            REAL,
  currency          TEXT,
  cash_account      TEXT,
  bucket            TEXT,
  market            TEXT,
  rationale         TEXT,
  tags              TEXT,
  from_amount       REAL,
  from_currency     TEXT,
  from_cash_account TEXT,
  to_amount         REAL,
  to_currency       TEXT,
  to_cash_account   TEXT,
  rate              REAL,
  source            TEXT,
  source_ref        TEXT,
  created_at        TEXT    NOT NULL,
  target_id         INTEGER REFERENCES transactions(id)
);

CREATE TABLE IF NOT EXISTS sell_lot_consumption (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  transaction_id  INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
  acq_date        TEXT    NOT NULL,
  cost            REAL    NOT NULL,
  qty             REAL    NOT NULL
);

-- Iteration 3 — derived balance tables. Always rebuilt from the transactions
-- log; never edited directly. Gives O(1) "current state" reads to the
-- report renderer / fetch_prices / fetch_history without re-running replay.
CREATE TABLE IF NOT EXISTS open_lots (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker      TEXT    NOT NULL,
  qty         REAL    NOT NULL,
  cost        REAL    NOT NULL,
  acq_date    TEXT    NOT NULL,
  bucket      TEXT    NOT NULL,
  market      TEXT    NOT NULL,
  currency    TEXT    NOT NULL,
  is_share    INTEGER NOT NULL DEFAULT 1,
  updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_balances (
  currency    TEXT    PRIMARY KEY,
  amount      REAL    NOT NULL,
  updated_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_txn_date    ON transactions(date, id);
CREATE INDEX IF NOT EXISTS idx_txn_ticker  ON transactions(ticker);
CREATE INDEX IF NOT EXISTS idx_txn_type    ON transactions(type);
CREATE INDEX IF NOT EXISTS idx_lot_txn     ON sell_lot_consumption(transaction_id);
CREATE INDEX IF NOT EXISTS idx_lot_ticker  ON open_lots(ticker);
CREATE INDEX IF NOT EXISTS idx_lot_bucket  ON open_lots(bucket);
"""


def db_connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def db_init(path: Path) -> str:
    """Create transactions.db with schema. Idempotent — safe to call repeatedly.

    On a fresh DB the result is "created"; on an existing older DB the new
    materialized balance tables (`open_lots`, `cash_balances`) are added via
    `IF NOT EXISTS` and a balance rebuild is run so the derived view is
    populated. Returns "created" or "verified".
    """
    fresh = not path.exists()
    conn = db_connect(path)
    prior_version: Optional[int] = None
    try:
        if not fresh:
            try:
                row = conn.execute(
                    "SELECT value FROM schema_meta WHERE key='version'"
                ).fetchone()
                if row and row["value"]:
                    prior_version = int(row["value"])
            except sqlite3.Error:
                prior_version = None
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    finally:
        conn.close()
    # If we just upgraded to the current schema, populate the
    # balance tables now so consumers can read them immediately.
    if not fresh and (prior_version or 0) < SCHEMA_VERSION:
        db_rebuild_balances(path)
    return "created" if fresh else "verified"


def db_rebuild_balances(db_path: Path) -> Dict[str, int]:
    """Rebuild open_lots + cash_balances from the transactions log.

    Always called automatically at the tail of every import path; can also be
    invoked manually via `db rebuild` for ad-hoc recovery.
    """
    if not db_path.exists():
        return {"open_lots": 0, "cash_balances": 0}
    txns = load_transactions_db(db_path)
    state = replay(txns)
    now = _now_iso()
    conn = db_connect(db_path)
    try:
        conn.execute("DELETE FROM open_lots")
        conn.execute("DELETE FROM cash_balances")
        lot_rows = 0
        for ticker, lots in state.open_lots.items():
            for lot in lots:
                if lot.qty <= 1e-9:
                    continue
                conn.execute(
                    """INSERT INTO open_lots
                       (ticker, qty, cost, acq_date, bucket, market, currency, is_share, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ticker, lot.qty, lot.cost, lot.acq_date,
                        lot.bucket, lot.market, lot.currency,
                        1 if lot.market not in ("crypto", "FX") else 0,
                        now,
                    ),
                )
                lot_rows += 1
        cash_rows = 0
        for ccy, amount in state.cash.items():
            if abs(amount) < 1e-6:
                continue
            conn.execute(
                "INSERT INTO cash_balances (currency, amount, updated_at) VALUES (?, ?, ?)",
                (ccy, amount, now),
            )
            cash_rows += 1
        conn.commit()
    finally:
        conn.close()
    return {"open_lots": lot_rows, "cash_balances": cash_rows}


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _txn_to_db_row(t: Transaction, *, source: str, source_ref: Optional[str]) -> Dict[str, Any]:
    """Marshal a Transaction → dict of column → value for INSERT."""
    f = t.fields
    return {
        "date": t.date,
        "type": t.type,
        "ticker": t.ticker,
        "qty": t.qty,
        "price": t.price,
        "gross": _strip_currency(f.get("gross")),
        "fees": t.fees if t.fees is not None else 0,
        "net": _strip_currency(f.get("net")),
        "amount": t.amount,
        "currency": t.currency,
        "cash_account": t.cash_account,
        "bucket": t.bucket,
        "market": t.market,
        "rationale": t.rationale or None,
        "tags": ",".join(t.tags) if t.tags else None,
        "from_amount": _strip_currency(f.get("from_amount")),
        "from_currency": (f.get("from_currency") or "").strip().upper() or None,
        "from_cash_account": (f.get("from_cash_account") or "").strip().upper() or None,
        "to_amount": _strip_currency(f.get("to_amount")),
        "to_currency": (f.get("to_currency") or "").strip().upper() or None,
        "to_cash_account": (f.get("to_cash_account") or "").strip().upper() or None,
        "rate": _strip_currency(f.get("rate")),
        "source": source,
        "source_ref": source_ref,
        "created_at": _now_iso(),
        "target_id": None,
    }


_INSERT_COLS = (
    "date", "type", "ticker", "qty", "price", "gross", "fees", "net",
    "amount", "currency", "cash_account", "bucket", "market",
    "rationale", "tags",
    "from_amount", "from_currency", "from_cash_account",
    "to_amount", "to_currency", "to_cash_account", "rate",
    "source", "source_ref", "created_at", "target_id",
)


def _insert_transaction_row(
    conn: sqlite3.Connection,
    row: Dict[str, Any],
    lots_consumed: Optional[List[Tuple[str, float, float]]] = None,
) -> int:
    placeholders = ", ".join(["?"] * len(_INSERT_COLS))
    cols = ", ".join(_INSERT_COLS)
    cur = conn.execute(
        f"INSERT INTO transactions ({cols}) VALUES ({placeholders})",
        tuple(row.get(c) for c in _INSERT_COLS),
    )
    txn_id = cur.lastrowid
    if lots_consumed and txn_id is not None:
        conn.executemany(
            "INSERT INTO sell_lot_consumption (transaction_id, acq_date, cost, qty) VALUES (?, ?, ?, ?)",
            [(txn_id, ad, c, q) for ad, c, q in lots_consumed],
        )
    return txn_id or 0


def _validate_canonical_dict(d: Dict[str, Any]) -> List[str]:
    """Return a list of validation errors. Empty list = OK."""
    errs: List[str] = []
    if not d.get("date"):
        errs.append("missing required field: date")
    elif not re.match(r"^\d{4}-\d{2}-\d{2}$", str(d["date"])):
        errs.append(f"date must be YYYY-MM-DD, got {d['date']!r}")
    txn_type = (d.get("type") or "").upper()
    if txn_type not in TRANSACTION_TYPES:
        errs.append(f"unknown transaction type: {d.get('type')!r}")
    if txn_type in {"BUY", "SELL"}:
        if d.get("ticker") in (None, ""):
            errs.append(f"{txn_type} missing ticker")
        if d.get("qty") in (None, ""):
            errs.append(f"{txn_type} missing qty")
        if d.get("price") in (None, ""):
            errs.append(f"{txn_type} missing price")
    if txn_type in {"DEPOSIT", "WITHDRAW", "DIVIDEND", "FEE"} and d.get("amount") in (None, ""):
        errs.append(f"{txn_type} missing amount")
    if txn_type == "FX_CONVERT":
        for k in ("from_amount", "to_amount", "from_currency", "to_currency"):
            if d.get(k) in (None, ""):
                errs.append(f"FX_CONVERT missing {k}")
    return errs


def _dict_to_transaction(d: Dict[str, Any], *, seq: int) -> Transaction:
    """Turn a canonical dict (CSV row, JSON record) into a Transaction object."""
    fields: Dict[str, str] = {}
    for k, v in d.items():
        if v is None:
            continue
        if k in ("lots", "lots_json", "tags"):
            continue
        fields[k] = str(v)

    t = Transaction(
        seq=seq,
        date=str(d["date"]),
        type=str(d["type"]).upper(),
        ticker=_normalize_ticker(str(d["ticker"])) if d.get("ticker") else None,
        raw_heading=f"## {d.get('date')} {str(d.get('type','')).upper()} {d.get('ticker','') or ''}".strip(),
        fields=fields,
    )
    # Resolve helpers
    t.qty = _strip_currency(str(d["qty"])) if d.get("qty") not in (None, "") else None
    t.price = _strip_currency(str(d["price"])) if d.get("price") not in (None, "") else None
    t.amount = _strip_currency(str(d["amount"])) if d.get("amount") not in (None, "") else None
    t.fees = _strip_currency(str(d["fees"])) if d.get("fees") not in (None, "") else None
    t.realized_pnl = _strip_currency(str(d["realized_pnl"])) if d.get("realized_pnl") not in (None, "") else None
    t.currency = (str(d.get("currency") or "")).strip().upper() or None
    t.cash_account = (str(d.get("cash_account") or t.currency or "")).strip().upper() or None
    t.bucket = (str(d.get("bucket") or "")).strip() or None
    t.market = (str(d.get("market") or "")).strip() or None
    t.rationale = (str(d.get("rationale") or "")).strip()
    raw_tags = d.get("tags")
    if isinstance(raw_tags, list):
        t.tags = [str(x).strip() for x in raw_tags if str(x).strip()]
    elif isinstance(raw_tags, str) and raw_tags.strip():
        t.tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]

    # Lots block
    raw_lots = d.get("lots")
    if isinstance(raw_lots, str) and raw_lots.strip():
        try:
            raw_lots = json.loads(raw_lots)
        except json.JSONDecodeError:
            raw_lots = None
    if not raw_lots:
        raw_lots_json = d.get("lots_json")
        if isinstance(raw_lots_json, str) and raw_lots_json.strip():
            try:
                raw_lots = json.loads(raw_lots_json)
            except json.JSONDecodeError:
                raw_lots = None
    if isinstance(raw_lots, list):
        for lot in raw_lots:
            if not isinstance(lot, dict):
                continue
            ad = str(lot.get("acq_date") or "")
            c = _strip_currency(str(lot.get("cost") or ""))
            q = _strip_currency(str(lot.get("qty") or ""))
            if ad and c is not None and q is not None:
                t.lots_consumed.append((ad, c, q))
    return t


def db_import_records(
    db_path: Path,
    records: List[Dict[str, Any]],
    *,
    source: str,
    source_ref: Optional[str],
) -> Tuple[int, List[str]]:
    """Validate + insert a batch of canonical dicts. Atomic.

    Returns (rows_inserted, errors). On any validation failure, no rows are
    written.
    """
    db_init(db_path)
    errors: List[str] = []
    parsed: List[Tuple[Transaction, List[Tuple[str, float, float]]]] = []
    for i, rec in enumerate(records):
        rec_errs = _validate_canonical_dict(rec)
        if rec_errs:
            errors.extend(f"row {i + 1}: {e}" for e in rec_errs)
            continue
        t = _dict_to_transaction(rec, seq=i)
        parsed.append((t, t.lots_consumed))
    if errors:
        return 0, errors

    conn = db_connect(db_path)
    try:
        for t, lots in parsed:
            row = _txn_to_db_row(t, source=source, source_ref=source_ref)
            _insert_transaction_row(conn, row, lots)
        conn.commit()
    finally:
        conn.close()
    # Refresh the derived balance tables so subsequent reads see the new state.
    db_rebuild_balances(db_path)
    return len(parsed), []


def db_import_md(md_path: Path, db_path: Path) -> Tuple[int, List[str]]:
    """One-shot migration: parse TRANSACTIONS.md and INSERT every entry."""
    db_init(db_path)
    txns = parse_transactions(md_path)
    conn = db_connect(db_path)
    inserted = 0
    issues: List[str] = []
    try:
        for t in txns:
            row = _txn_to_db_row(t, source="md", source_ref=str(md_path))
            _insert_transaction_row(conn, row, t.lots_consumed)
            inserted += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        issues.append(f"db_import_md failed: {e}")
    finally:
        conn.close()
    if not issues:
        db_rebuild_balances(db_path)
    return inserted, issues


def _apply_csv_mapping(row: Dict[str, str], mapping: Dict[str, str]) -> Dict[str, Any]:
    """Translate broker-CSV column names → canonical fields. Mapping is
    {broker_column: canonical_field}; columns not in the mapping pass through
    only when they already match a canonical field name (case-insensitive)."""
    canon_fields = {
        "date", "type", "ticker", "qty", "price", "gross", "fees", "net",
        "amount", "currency", "cash_account", "bucket", "market",
        "rationale", "tags",
        "from_amount", "from_currency", "from_cash_account",
        "to_amount", "to_currency", "to_cash_account", "rate",
        "lots", "lots_json", "realized_pnl",
    }
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if v is None:
            continue
        v_clean = str(v).strip()
        if not v_clean:
            continue
        canonical = mapping.get(k)
        if canonical is None:
            canonical = mapping.get(k.strip())
        if canonical is None and k.strip().lower() in canon_fields:
            canonical = k.strip().lower()
        if canonical is None and k.strip().replace(" ", "_").lower() in canon_fields:
            canonical = k.strip().replace(" ", "_").lower()
        if canonical is None:
            continue
        out[canonical] = v_clean
    return out


def db_import_csv(
    csv_path: Path,
    db_path: Path,
    *,
    mapping: Optional[Dict[str, str]] = None,
) -> Tuple[int, List[str]]:
    """Import a CSV file. Mapping (optional) translates broker columns to
    canonical field names. Atomic."""
    mapping = mapping or {}
    records: List[Dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapped = _apply_csv_mapping(row, mapping)
            if mapped:
                records.append(mapped)
    return db_import_records(db_path, records, source="csv", source_ref=str(csv_path))


def db_import_json(json_path: Path, db_path: Path) -> Tuple[int, List[str]]:
    """Import a JSON array of canonical transaction dicts. Atomic."""
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return 0, ["JSON root must be a list of transaction objects (or a single object)"]
    return db_import_records(db_path, payload, source="json", source_ref=str(json_path))


def db_add(json_blob: str, db_path: Path) -> Tuple[int, List[str]]:
    """Insert a single transaction from a JSON string. Used by the message
    workflow once the agent has parsed natural language."""
    try:
        payload = json.loads(json_blob)
    except json.JSONDecodeError as e:
        return 0, [f"invalid JSON: {e}"]
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return 0, ["JSON must be an object or array of objects"]
    return db_import_records(db_path, payload, source="message", source_ref=None)


def load_transactions_db(db_path: Path) -> List[Transaction]:
    """Load all rows as Transaction objects in (date, id) order.

    The returned list is shape-compatible with `parse_transactions(md)` so
    every downstream `replay`, `compute_profit_panel`, `compute_realized_unrealized`
    function works unchanged.
    """
    if not db_path.exists():
        return []
    conn = db_connect(db_path)
    try:
        rows = list(conn.execute(
            "SELECT * FROM transactions ORDER BY date ASC, id ASC"
        ))
        lots_by_txn: Dict[int, List[Tuple[str, float, float]]] = {}
        for r in conn.execute(
            "SELECT transaction_id, acq_date, cost, qty FROM sell_lot_consumption"
        ):
            lots_by_txn.setdefault(r["transaction_id"], []).append(
                (r["acq_date"], float(r["cost"]), float(r["qty"]))
            )
    finally:
        conn.close()

    out: List[Transaction] = []
    for seq, row in enumerate(rows):
        fields: Dict[str, str] = {}
        for k in row.keys():
            v = row[k]
            if v is None or k in ("id", "created_at", "source", "source_ref", "target_id"):
                continue
            fields[k] = str(v)
        ticker = row["ticker"]
        t = Transaction(
            seq=seq,
            date=row["date"],
            type=row["type"],
            ticker=_normalize_ticker(ticker) if ticker else None,
            raw_heading=f"## {row['date']} {row['type']} {ticker or ''}".strip(),
            fields=fields,
        )
        t.qty = row["qty"]
        t.price = row["price"]
        t.amount = row["amount"]
        t.fees = row["fees"]
        t.currency = (row["currency"] or "").upper() or None
        t.cash_account = (row["cash_account"] or t.currency or "").upper() or None
        t.bucket = row["bucket"]
        t.market = row["market"]
        t.rationale = row["rationale"] or ""
        if row["tags"]:
            t.tags = [tag.strip() for tag in str(row["tags"]).split(",") if tag.strip()]
        t.lots_consumed = lots_by_txn.get(row["id"], [])
        out.append(t)
    return out


def db_dump(db_path: Path) -> List[Dict[str, Any]]:
    """Dump all transactions as JSON-serializable dicts (with their lots)."""
    if not db_path.exists():
        return []
    conn = db_connect(db_path)
    try:
        out: List[Dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM transactions ORDER BY date ASC, id ASC"):
            d = {k: row[k] for k in row.keys()}
            lots = list(conn.execute(
                "SELECT acq_date, cost, qty FROM sell_lot_consumption WHERE transaction_id = ?",
                (row["id"],),
            ))
            if lots:
                d["lots"] = [{"acq_date": l["acq_date"], "cost": l["cost"], "qty": l["qty"]} for l in lots]
            out.append(d)
        return out
    finally:
        conn.close()


def db_stats(db_path: Path) -> Dict[str, Any]:
    if not db_path.exists():
        return {"db_exists": False}
    conn = db_connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]
        by_type = {
            r["type"]: r["n"]
            for r in conn.execute("SELECT type, COUNT(*) AS n FROM transactions GROUP BY type")
        }
        tickers = [
            r["ticker"]
            for r in conn.execute("SELECT DISTINCT ticker FROM transactions WHERE ticker IS NOT NULL ORDER BY ticker")
        ]
        date_range = conn.execute(
            "SELECT MIN(date) AS first, MAX(date) AS last FROM transactions"
        ).fetchone()
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
        return {
            "db_exists": True,
            "schema_version": int(version["value"]) if version else None,
            "total_transactions": total,
            "by_type": by_type,
            "tickers": tickers,
            "first_date": date_range["first"],
            "last_date": date_range["last"],
        }
    finally:
        conn.close()


def load_holdings_lots(db_path: Path) -> List[Lot]:
    """Return the projected open-position view (open_lots + cash_balances) as
    `List[Lot]`, drop-in compatible with the legacy `parse_holdings()` shape.

    Consumers (`scripts/fetch_prices.py`, `scripts/fetch_history.py`,
    `scripts/generate_report.py`) call this in place of `parse_holdings()`.

    If the DB predates the materialized balance tables, this upgrades the
    schema and rebuilds them before reading. If the balance tables are empty
    (e.g. on a freshly-created DB before anything has been imported), this
    returns `[]`.
    """
    if not db_path.exists():
        return []
    db_init(db_path)
    conn_check = db_connect(db_path)
    try:
        txn_count = conn_check.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]
        balance_count = (
            conn_check.execute("SELECT COUNT(*) AS n FROM open_lots").fetchone()["n"]
            + conn_check.execute("SELECT COUNT(*) AS n FROM cash_balances").fetchone()["n"]
        )
    finally:
        conn_check.close()
    if txn_count and balance_count == 0:
        db_rebuild_balances(db_path)
    conn = db_connect(db_path)
    out: List[Lot] = []
    try:
        for row in conn.execute(
            "SELECT * FROM open_lots ORDER BY bucket ASC, ticker ASC, acq_date ASC, id ASC"
        ):
            ticker = row["ticker"]
            qty = float(row["qty"])
            cost = float(row["cost"])
            acq_date = row["acq_date"]
            bucket = row["bucket"]
            currency = row["currency"]
            market_str = row["market"]
            try:
                market_enum = MarketType(market_str) if market_str else MarketType.UNKNOWN
            except ValueError:
                market_enum = MarketType.UNKNOWN
            is_share = bool(row["is_share"])
            # Synthesise a raw_line for any code path that prints/logs it.
            unit = "shares " if is_share else ""
            ccy_prefix = {
                "USD": "$", "TWD": "NT$", "JPY": "¥",
                "EUR": "€", "GBP": "£", "HKD": "HK$",
            }.get(currency, "")
            raw_line = (
                f"- {ticker}: {qty:g} {unit}@ {ccy_prefix}{cost:g} on {acq_date} [{market_str}]"
                if is_share else
                f"- {ticker} {qty:g} @ {ccy_prefix}{cost:g} on {acq_date} [{market_str}]"
            )
            out.append(Lot(
                raw_line=raw_line,
                bucket=bucket,
                ticker=ticker,
                quantity=qty,
                cost=cost,
                date=acq_date,
                market=market_enum,
                is_share=is_share,
            ))
        for row in conn.execute(
            "SELECT currency, amount FROM cash_balances ORDER BY currency ASC"
        ):
            ccy = row["currency"]
            amount = float(row["amount"])
            out.append(Lot(
                raw_line=f"- {ccy}: {amount:g} [cash]",
                bucket="Cash Holdings",
                ticker=ccy,
                quantity=amount,
                cost=None,
                date=None,
                market=MarketType.CASH,
                is_share=False,
            ))
    finally:
        conn.close()
    return out


def load_fetch_universe_lots(db_path: Path) -> List[Lot]:
    """Return the price-fetch universe: today's open lots + cash UNION stub
    lots for every ticker that ever transacted but is no longer in open_lots.

    Why: ``compute_profit_panel`` replays state to past period boundaries
    (1D, 7D, MTD, 1M, YTD, 1Y, ALLTIME). Sold-off tickers reappear in those
    boundary states. ``load_holdings_lots`` returns only currently-held lots,
    so the price-fetch and history-fetch pipelines miss those tickers and
    the profit panel ends up with no boundary close + no latest price for
    them. The stub lots carry the (ticker, market, currency, bucket,
    is_share) routing metadata the fetcher needs; ``quantity = 0`` keeps
    valuation/replay code paths unaffected because they all weight by qty.

    Stub buckets are kept identical to the most recent transaction's bucket
    so reports that group by bucket still classify the ticker correctly.
    """
    if not db_path.exists():
        return []
    current = load_holdings_lots(db_path)
    held: set[str] = {l.ticker for l in current if l.market != MarketType.CASH}

    db_init(db_path)
    conn = db_connect(db_path)
    try:
        # Pick the most recent BUY/SELL row per ticker so (market, currency,
        # bucket) come from a single, deterministic source row. SQLite's
        # bare-column rule is unreliable when two rows tie on MAX(date), and
        # DEPOSIT/WITHDRAW rows can have empty bucket/market — neither belongs
        # in the trading-history universe, so restrict to the trade types.
        rows = conn.execute(
            """
            SELECT t1.ticker,
                   COALESCE(NULLIF(t1.market, ''), '')   AS market,
                   COALESCE(NULLIF(t1.currency, ''), '') AS currency,
                   COALESCE(NULLIF(t1.bucket, ''), '')   AS bucket,
                   t1.date                               AS last_date
              FROM transactions t1
             WHERE t1.ticker IS NOT NULL AND t1.ticker != ''
               AND t1.type IN ('BUY','SELL')
               AND t1.id = (
                   SELECT t2.id FROM transactions t2
                    WHERE t2.ticker = t1.ticker
                      AND t2.type IN ('BUY','SELL')
                    ORDER BY t2.date DESC, t2.id DESC
                    LIMIT 1
               )
            """
        ).fetchall()
    finally:
        conn.close()

    by_ticker: Dict[str, Dict[str, str]] = {}
    for row in rows:
        ticker = row["ticker"]
        if ticker in held:
            continue
        by_ticker[ticker] = {
            "market": row["market"],
            "currency": row["currency"],
            "bucket": row["bucket"] or "Mid Term (1y+)",
            "last_date": row["last_date"],
        }

    stubs: List[Lot] = []
    for ticker, meta in sorted(by_ticker.items()):
        try:
            market_enum = MarketType(meta["market"]) if meta["market"] else MarketType.UNKNOWN
        except ValueError:
            market_enum = MarketType.UNKNOWN
        is_share = market_enum not in (MarketType.CRYPTO, MarketType.FX, MarketType.CASH)
        # `currency` here is purely cosmetic (used to pick the prefix glyph
        # in the synthetic raw_line below). The runtime currency is derived
        # from `lot.market` everywhere downstream.
        ccy_prefix = {
            "USD": "$", "TWD": "NT$", "JPY": "¥",
            "EUR": "€", "GBP": "£", "HKD": "HK$",
        }.get(meta["currency"], "")
        stubs.append(Lot(
            raw_line=f"- {ticker} 0 @ {ccy_prefix}0 (sold; last txn {meta['last_date']}) [{meta['market']}]",
            bucket=meta["bucket"],
            ticker=ticker,
            quantity=0.0,
            cost=0.0,
            date=meta["last_date"],
            market=market_enum,
            is_share=is_share,
        ))

    return current + stubs


def load_transactions(
    *,
    db: Optional[Path] = None,
    md: Optional[Path] = None,
) -> List[Transaction]:
    """Load transactions from DB. The optional md fallback exists only for
    direct migration tests; runtime CLI paths use transactions.db."""
    if db and db.exists():
        return load_transactions_db(db)
    if md and md.exists():
        return parse_transactions(md)
    return []


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _add_source_args(sp: argparse.ArgumentParser) -> None:
    """Common --db flag."""
    sp.add_argument("--db", default=DEFAULT_DB_PATH, type=Path,
                    help="SQLite store (default: transactions.db)")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    # ---- migrate (HOLDINGS.md -> DB) -------------------------------------- #
    m = sub.add_parser("migrate", help="Bootstrap transactions.db from HOLDINGS.md (synthetic BUY+DEPOSIT entries)")
    m.add_argument("--holdings", default="HOLDINGS.md", type=Path)
    m.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)
    m.add_argument("--dry-run", action="store_true",
                   help="Print proposed records as JSON, do not write")

    # ---- verify (DB replay vs balance tables) ----------------------------- #
    v = sub.add_parser("verify", help="Replay transactions.db and reconcile against open_lots + cash_balances")
    v.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)

    # ---- pnl --------------------------------------------------------------- #
    pn = sub.add_parser("pnl", help="Print realized + unrealized snapshot")
    pn.add_argument("--prices", default="prices.json", type=Path)
    pn.add_argument("--settings", default="SETTINGS.md", type=Path)
    _add_source_args(pn)

    # ---- profit-panel ------------------------------------------------------ #
    pp = sub.add_parser("profit-panel", help="Compute profit-panel rows")
    pp.add_argument("--prices", default="prices.json", type=Path)
    pp.add_argument("--settings", default="SETTINGS.md", type=Path)
    pp.add_argument("--output", default=None, type=Path,
                    help="Write JSON output here (suitable for merging into report_context.json)")
    pp.add_argument("--today", default=None, help="Override today (YYYY-MM-DD); default: local date")
    _add_source_args(pp)

    # ---- analytics --------------------------------------------------------- #
    an = sub.add_parser("analytics", help="Compute transaction-driven report analytics")
    an.add_argument("--prices", default="prices.json", type=Path)
    an.add_argument("--settings", default="SETTINGS.md", type=Path)
    an.add_argument("--output", default=None, type=Path,
                    help="Write JSON output here (merge into report_context.json as transaction_analytics)")
    an.add_argument("--today", default=None, help="Override today (YYYY-MM-DD); default: local date")
    _add_source_args(an)

    # ---- snapshot ---------------------------------------------------------- #
    sn = sub.add_parser("snapshot",
                        help="Materialize the full report snapshot (aggregates, totals, "
                             "fx, book_pacing, risk_heat, special_checks, profit_panel, "
                             "realized_unrealized, transaction_analytics) into one JSON "
                             "for `python scripts/generate_report.py --snapshot`.")
    sn.add_argument("--prices", default="prices.json", type=Path,
                    help="prices.json from scripts/fetch_prices.py")
    sn.add_argument("--settings", default="SETTINGS.md", type=Path)
    sn.add_argument("--output", default=Path("report_snapshot.json"), type=Path,
                    help="Snapshot path; default: ./report_snapshot.json")
    sn.add_argument("--today", default=None, help="Override today (YYYY-MM-DD); default: local date")
    _add_source_args(sn)

    # ---- replay ------------------------------------------------------------ #
    rp = sub.add_parser("replay", help="Print replay state at cutoff")
    rp.add_argument("--cutoff", default=None, help="ISO date; default: today")
    _add_source_args(rp)

    sub.add_parser("self-check", help="Run unit tests")

    # ---- db <subcommand> --------------------------------------------------- #
    db = sub.add_parser("db", help="SQLite store: init, import, add, dump, stats")
    db_sub = db.add_subparsers(dest="db_cmd", required=True)

    di = db_sub.add_parser("init", help="Create transactions.db with schema (idempotent)")
    di.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)

    dim = db_sub.add_parser("import-md", help="One-shot migration: import TRANSACTIONS.md into the DB")
    dim.add_argument("--input", required=True, type=Path)
    dim.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)
    dim.add_argument("--delete-after", action="store_true",
                     help="Delete the source markdown file after a successful import")

    dic = db_sub.add_parser("import-csv", help="Import a CSV file (canonical or broker-mapped columns)")
    dic.add_argument("--input", required=True, type=Path)
    dic.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)
    dic.add_argument("--mapping", default=None, type=Path,
                     help="Optional JSON: {broker_column: canonical_field}")

    dij = db_sub.add_parser("import-json", help="Import a JSON array / object of canonical transactions")
    dij.add_argument("--input", required=True, type=Path)
    dij.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)

    da = db_sub.add_parser("add", help="Insert one transaction from an inline JSON blob")
    da.add_argument("--json", required=True, help="Canonical JSON object (or list)")
    da.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)

    dd = db_sub.add_parser("dump", help="Dump all transactions as JSON")
    dd.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)

    ds = db_sub.add_parser("stats", help="Print summary stats (counts by type, distinct tickers, date range)")
    ds.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)

    drb = db_sub.add_parser("rebuild", help="Force-rebuild open_lots + cash_balances from the transactions log")
    drb.add_argument("--db", default=DEFAULT_DB_PATH, type=Path)

    return p


def _base_currency_from_settings(path: Path) -> str:
    if not path.exists():
        return "USD"
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*-\s*Base currency\s*:\s*(?P<c>[A-Z]{3})", raw)
        if m:
            return m.group("c").upper()
    return "USD"


def _resolve_txns(args: argparse.Namespace) -> List[Transaction]:
    """Resolve transactions from transactions.db."""
    db = getattr(args, "db", None)
    if db and Path(db).exists():
        db_init(Path(db))
        return load_transactions_db(Path(db))
    return []


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.cmd == "self-check":
        return _selfcheck()

    if args.cmd == "migrate":
        # HOLDINGS.md → synthetic BUY/DEPOSIT entries → transactions.db (or print).
        records = _holdings_to_records(args.holdings)
        if args.dry_run:
            print(json.dumps(records, indent=2, ensure_ascii=False))
            return 0
        db_init(args.db)
        # If the DB already has rows, refuse to clobber unless dry-run.
        existing = db_stats(args.db).get("total_transactions", 0)
        if existing > 0:
            print(f"ERROR: {args.db} already has {existing} transaction(s). "
                  f"Migration would duplicate. Delete the DB or use --dry-run.",
                  file=sys.stderr)
            return 3
        inserted, errs = db_import_records(args.db, records, source="migrate", source_ref=str(args.holdings))
        if errs:
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 4
        print(f"Migrated {inserted} record(s) from {args.holdings} → {args.db}.")
        return 0

    if args.cmd == "verify":
        ok, mismatches = _verify_balance_tables(args)
        if ok:
            print("OK: replay matches open_lots + cash_balances.")
            return 0
        print("MISMATCH (balance tables drifted from log replay; run `db rebuild`):")
        for m in mismatches:
            print(f"  - {m}")
        return 1

    if args.cmd == "replay":
        txns = _resolve_txns(args)
        state = replay(txns, cutoff=args.cutoff)
        out = {
            "cutoff": state.cutoff,
            "open_lots": {
                t: [
                    {"qty": l.qty, "cost": l.cost, "acq_date": l.acq_date,
                     "bucket": l.bucket, "market": l.market, "currency": l.currency}
                    for l in lots
                ]
                for t, lots in state.open_lots.items()
            },
            "cash": state.cash,
            "realized_event_count": len(state.realized_events),
            "issues": state.issues,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "pnl":
        txns = _resolve_txns(args)
        prices = json.loads(args.prices.read_text(encoding="utf-8")) if args.prices.exists() else {}
        base = _base_currency_from_settings(args.settings)
        snap = compute_realized_unrealized(txns, prices, base=base)
        print(json.dumps(snap, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "profit-panel":
        txns = _resolve_txns(args)
        prices = json.loads(args.prices.read_text(encoding="utf-8")) if args.prices.exists() else {}
        base = _base_currency_from_settings(args.settings)
        today = _dt.date.fromisoformat(args.today) if args.today else _dt.date.today()
        panel = compute_profit_panel(txns, prices, base=base, today=today)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(panel, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote profit panel to {args.output}.")
        else:
            print(json.dumps(panel, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "snapshot":
        # Pipeline materialization: every numeric/structural field the renderer
        # needs lives in the snapshot. The agent then authors editorial
        # context.json (news, events, alerts, adjustments, action list,
        # theme/sector HTML) and runs `generate_report.py --snapshot`.
        try:
            from portfolio_snapshot import (              # noqa: WPS433
                BUILTIN_UI_LOCALES,
                compute_snapshot,
                parse_settings_profile,
                write_snapshot,
            )
        except ImportError as exc:
            print(f"ERROR: cannot import portfolio_snapshot ({exc}). "
                  "Make sure scripts/portfolio_snapshot.py exists alongside transactions.py.",
                  file=sys.stderr)
            return 5
        # Defense-in-depth: the snapshot bakes settings_locale / display_name /
        # raw_language / base_currency into the JSON; the renderer reads them
        # from the snapshot and ignores its own --settings flag for those
        # fields. So a demo --db with the root --settings default silently
        # renders the report in the root profile's language. Mirror the
        # generate_report.py guard but trigger off --db instead of --output.
        db_under_demo = (
            args.db is not None
            and "demo" in {p.lower() for p in Path(args.db).resolve().parts}
        )
        if (
            db_under_demo
            and Path(args.settings).resolve().name == "SETTINGS.md"
            and Path(args.settings).resolve().parent.name != "demo"
        ):
            print(
                f"WARNING: --db {args.db} appears to be the demo ledger but --settings "
                f"is the root default ({args.settings}). Pass --settings demo/SETTINGS.md "
                "so the snapshot bakes the demo locale / base currency — generate_report.py "
                "reads those from the snapshot, not from its own --settings flag.",
                file=sys.stderr,
            )
        if not args.prices.exists():
            print(f"ERROR: --prices file {args.prices} not found "
                  "(run scripts/fetch_prices.py first).", file=sys.stderr)
            return 3
        prices = json.loads(args.prices.read_text(encoding="utf-8"))
        settings = parse_settings_profile(args.settings)
        today = _dt.date.fromisoformat(args.today) if args.today else _dt.date.today()
        snap = compute_snapshot(
            db_path=args.db,
            prices=prices,
            settings=settings,
            today=today,
        )
        if not snap.aggregates:
            print(f"ERROR: {args.db} has no open_lots / cash_balances. "
                  "Run `python scripts/transactions.py db init` and import transactions first.",
                  file=sys.stderr)
            return 4
        n_bytes = write_snapshot(snap, args.output)
        gaps = []
        if snap.profit_panel_error:
            gaps.append(f"profit_panel: {snap.profit_panel_error}")
        if snap.realized_unrealized_error:
            gaps.append(f"realized_unrealized: {snap.realized_unrealized_error}")
        if snap.transaction_analytics_error:
            gaps.append(f"transaction_analytics: {snap.transaction_analytics_error}")
        if snap.missing_fx:
            gaps.append(f"missing FX: {', '.join(snap.missing_fx)}")
        print(
            f"Wrote snapshot to {args.output} "
            f"({n_bytes:,} bytes; {len(snap.aggregates)} positions, base={snap.base_currency})."
        )
        for g in gaps:
            print(f"  - gap: {g}")
        # Phase-0 hard gate (early surface, complements the renderer's hard
        # exit-8): when the SETTINGS locale has no built-in UI dictionary, the
        # executing agent MUST translate `scripts/i18n/report_ui.en.json` into
        # `$REPORT_RUN_DIR/report_ui.<locale>.json` and pass it via
        # `--ui-dict` to `generate_report.py`. We surface the instruction
        # right here — before context authoring begins — so the agent can
        # do the translation in parallel with Phase A research instead of
        # discovering the requirement at render time. See
        # `docs/portfolio_report_agent_guidelines/02-inputs-to-self-containment.md`
        # §5.1 for the contract.
        if snap.settings_locale and snap.settings_locale not in BUILTIN_UI_LOCALES:
            run_dir = Path(args.output).resolve().parent
            target = run_dir / f"report_ui.{snap.settings_locale}.json"
            source = Path(__file__).resolve().parent / "i18n" / "report_ui.en.json"
            print(
                "\n" + "=" * 72 + "\n"
                f"NEXT STEP REQUIRED — locale '{snap.settings_locale}' "
                f"({snap.settings_display_name}) has no built-in UI dictionary.\n"
                f"Built-in locales: {list(BUILTIN_UI_LOCALES)}.\n"
                "\n"
                "Translate the dictionary YOURSELF (in-context), with the same\n"
                "model running this pipeline. Do NOT call Google Translate /\n"
                "DeepL / Bing / Papago / any external translation service or\n"
                "HTTP API — generic translators mangle finance terms (R:R,\n"
                "MWR annualized, Profit Factor, pp of NAV) and drop {format}\n"
                "placeholders. The dictionary is small (~245 keys, ~5 KB).\n"
                "\n"
                "Read every value in:\n"
                f"  {source}\n"
                "translate it into the target language, and write the result to:\n"
                f"  {target}\n"
                "Preserve every key, every `{format}` placeholder, every special\n"
                "character (<, >, &, Δ, ·, —). Token values stay English\n"
                "(e.g. `consensus-aligned`, `variant`, `contrarian`, `rebalance`).\n"
                "Then pass `--ui-dict " + str(target) + "` to "
                "`generate_report.py`.\n"
                "Without this, `generate_report.py` will exit with code 8 and "
                "refuse to render — chrome must match SETTINGS language.\n"
                "Spec: docs/portfolio_report_agent_guidelines/"
                "02-inputs-to-self-containment.md §5.1.1.\n"
                + "=" * 72,
                file=sys.stderr,
            )
        return 0

    if args.cmd == "analytics":
        txns = _resolve_txns(args)
        prices = json.loads(args.prices.read_text(encoding="utf-8")) if args.prices.exists() else {}
        base = _base_currency_from_settings(args.settings)
        today = _dt.date.fromisoformat(args.today) if args.today else _dt.date.today()
        analytics = compute_transaction_analytics(txns, prices, base=base, today=today)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(analytics, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote transaction analytics to {args.output}.")
        else:
            print(json.dumps(analytics, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "db":
        return _dispatch_db(args)

    return 2


# --------------------------------------------------------------------------- #
# CLI helpers — DB dispatch + holdings→records reused by migrate
# --------------------------------------------------------------------------- #

def _holdings_to_records(holdings_path: Path) -> List[Dict[str, Any]]:
    """Build canonical records from HOLDINGS.md. One DEPOSIT per cash currency
    sized to fund all BUYs + leave the current cash residual; one BUY per
    non-cash lot."""
    lots = parse_holdings(holdings_path)
    today_iso = _dt.date.today().isoformat()

    buy_outflow: Dict[str, float] = {}
    current_cash: Dict[str, float] = {}
    for lot in lots:
        if lot.bucket.lower().startswith("cash"):
            ccy = lot.ticker.upper()
            current_cash[ccy] = current_cash.get(ccy, 0.0) + lot.quantity
            continue
        if lot.cost is None or lot.date is None:
            continue
        ccy = _currency_for_lot(lot)
        buy_outflow[ccy] = buy_outflow.get(ccy, 0.0) + (lot.quantity * lot.cost)

    earliest = min((lot.date for lot in lots
                    if lot.date and not lot.bucket.lower().startswith("cash")),
                   default=today_iso)
    bootstrap_date = (
        (_dt.date.fromisoformat(earliest) - _dt.timedelta(days=1)).isoformat()
        if earliest != today_iso else today_iso
    )

    records: List[Dict[str, Any]] = []
    for ccy in sorted(set(current_cash) | set(buy_outflow)):
        amt = current_cash.get(ccy, 0.0) + buy_outflow.get(ccy, 0.0)
        if abs(amt) < 1e-6:
            continue
        records.append({
            "date": bootstrap_date,
            "type": "DEPOSIT",
            "amount": amt,
            "currency": ccy,
            "cash_account": ccy,
            "rationale": "bootstrap from HOLDINGS.md (synthetic; sized to fund pre-existing lots)",
            "tags": "migrated,bootstrap",
        })
    for lot in lots:
        if lot.bucket.lower().startswith("cash"):
            continue
        if lot.cost is None or lot.date is None:
            continue
        ccy = _currency_for_lot(lot)
        gross = lot.quantity * lot.cost
        records.append({
            "date": lot.date,
            "type": "BUY",
            "ticker": lot.ticker,
            "qty": lot.quantity,
            "price": lot.cost,
            "gross": gross,
            "fees": 0,
            "net": gross,
            "bucket": lot.bucket,
            "market": _market_for_lot(lot),
            "currency": ccy,
            "cash_account": ccy,
            "rationale": "bootstrap from HOLDINGS.md (synthetic, original mindset not recorded)",
            "tags": "migrated,bootstrap",
        })
    return records


def _verify_balance_tables(args: argparse.Namespace) -> Tuple[bool, List[str]]:
    """Replay the transactions log and reconcile against the materialized
    balance tables (open_lots + cash_balances).

    Drift here means the balance tables were edited outside the rebuild path
    — a defensive check. The `verify` command is the user-visible entry
    point; it implicitly runs after every import via the auto-rebuild.
    """
    db_path = Path(args.db) if hasattr(args, "db") else DEFAULT_DB_PATH
    if not db_path.exists():
        return False, [f"{db_path} not found"]
    db_init(db_path)
    txns = load_transactions_db(db_path)
    state = replay(txns)

    # Build expected balances from replay
    expected_qty: Dict[str, float] = {
        ticker: sum(l.qty for l in lots) for ticker, lots in state.open_lots.items()
    }
    expected_cash = {
        ccy: amt for ccy, amt in state.cash.items() if abs(amt) > 1e-6
    }

    # Read actual balance tables
    actual_qty: Dict[str, float] = {}
    actual_cash: Dict[str, float] = {}
    if db_path.exists():
        conn = db_connect(db_path)
        try:
            for row in conn.execute("SELECT ticker, qty FROM open_lots"):
                actual_qty[row["ticker"]] = actual_qty.get(row["ticker"], 0.0) + float(row["qty"])
            for row in conn.execute("SELECT currency, amount FROM cash_balances"):
                actual_cash[row["currency"]] = float(row["amount"])
        finally:
            conn.close()

    mismatches: List[str] = []
    for ticker in sorted(set(expected_qty) | set(actual_qty)):
        e = expected_qty.get(ticker, 0.0)
        a = actual_qty.get(ticker, 0.0)
        if abs(e - a) > 1e-6:
            mismatches.append(f"{ticker}: replay={e:g} vs open_lots={a:g}")
    for ccy in sorted(set(expected_cash) | set(actual_cash)):
        e = expected_cash.get(ccy, 0.0)
        a = actual_cash.get(ccy, 0.0)
        if abs(e - a) > 1e-3:
            mismatches.append(f"cash {ccy}: replay={e:g} vs cash_balances={a:g}")
    for issue in state.issues:
        mismatches.append(f"replay issue: {issue}")
    return len(mismatches) == 0, mismatches


def _dispatch_db(args: argparse.Namespace) -> int:
    db = args.db

    if args.db_cmd == "init":
        status = db_init(db)
        print(f"Schema {status} at {db} (version {SCHEMA_VERSION}).")
        return 0

    if args.db_cmd == "import-md":
        if not args.input.exists():
            print(f"ERROR: {args.input} not found", file=sys.stderr)
            return 2
        db_init(db)
        existing = db_stats(db).get("total_transactions", 0)
        if existing > 0:
            print(f"ERROR: {db} already has {existing} transaction(s). Delete the DB before importing.",
                  file=sys.stderr)
            return 3
        inserted, errs = db_import_md(args.input, db)
        if errs:
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 4
        print(f"Imported {inserted} markdown entry(ies) → {db}.")
        if args.delete_after:
            args.input.unlink()
            print(f"Deleted source file {args.input}.")
        return 0

    if args.db_cmd == "import-csv":
        if not args.input.exists():
            print(f"ERROR: {args.input} not found", file=sys.stderr)
            return 2
        db_init(db)
        mapping: Optional[Dict[str, str]] = None
        if args.mapping and args.mapping.exists():
            mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
        inserted, errs = db_import_csv(args.input, db, mapping=mapping)
        if errs:
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 4
        print(f"Imported {inserted} CSV row(s) → {db}.")
        return 0

    if args.db_cmd == "import-json":
        if not args.input.exists():
            print(f"ERROR: {args.input} not found", file=sys.stderr)
            return 2
        db_init(db)
        inserted, errs = db_import_json(args.input, db)
        if errs:
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 4
        print(f"Imported {inserted} JSON record(s) → {db}.")
        return 0

    if args.db_cmd == "add":
        db_init(db)
        inserted, errs = db_add(args.json, db)
        if errs:
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 4
        print(f"Added {inserted} transaction(s) → {db}.")
        return 0

    if args.db_cmd == "dump":
        out = db_dump(db)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.db_cmd == "stats":
        out = db_stats(db)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.db_cmd == "rebuild":
        if not db.exists():
            print(f"ERROR: {db} not found", file=sys.stderr)
            return 2
        result = db_rebuild_balances(db)
        print(json.dumps({"rebuilt": result}, indent=2, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
