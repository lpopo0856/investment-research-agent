#!/usr/bin/env python3
"""
Investment ledger engine.

Append-only event log for the portfolio. Captures the *operation mindset*
(rationale, tags, lot consumption) of every flow — buys, sells, deposits,
withdrawals, dividends, fees, and FX conversions.

This script provides:

  - Canonical account-local Markdown ledger for every transaction and cash flow
  - Legacy SQLite import/archive tooling for migration evidence only
  - Replay engine: walk events in chronological order, build positions and
    cash balances at any cutoff date
  - Realized / unrealized P&L computation
  - Profit panel computation for periods 1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME
  - Verify command: replay events and diff against materialized balance tables
  - Self-check unit tests

Usage
-----
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
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from fetch_prices import (  # type: ignore[import-not-found]
    KNOWN_CRYPTO_SYMBOLS,
    KNOWN_FIAT_CODES,
    Lot,
    MarketType,
)

from account import (  # type: ignore[import-not-found]
    add_account_args,
    resolve_account,
    autodetect_and_migrate_or_exit,
    detect_legacy_layout,
    prompt_and_migrate,
    validate_account_name,
    list_accounts,
    read_account_description,
    create_account_scaffold,
    read_active_pointer,
    write_active_pointer,
    check_pairing,
    check_ledger_pairing,
)
from benchmark_config import load_benchmark_config  # type: ignore[import-not-found]
from ledger_markdown import (  # type: ignore[import-not-found]
    CUTOVER_PROPOSAL_READY,
    DB_CANONICAL,
    DO_NOT_EDIT,
    DUAL_READ_PARITY,
    LEDGER_SCHEMA,
    MARKDOWN_CANONICAL,
    STORE_STATES,
    ensure_ledger_skeleton,
    event_id_for,
    event_path_for,
    events_dir,
    generated_dir,
    generated_payload,
    hash_tree,
    load_event_dicts,
    migrations_dir,
    now_utc,
    ordinal_from_event_id,
    parse_number,
    validate_event_set,
    write_event_file,
    write_json,
    read_json,
    sha256_file,
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
    """One ledger event in replay shape.

    Markdown-origin rows carry stable ``event_id`` / ``target_event_id``.
    Legacy-import metadata remains auditable without becoming canonical runtime identity.
    """
    seq: int                                    # 0-based file order; tiebreaker for same-day sort
    date: str                                   # ISO YYYY-MM-DD
    type: str                                   # one of TRANSACTION_TYPES
    ticker: Optional[str]                       # canonicalized; None for cash-only events
    raw_heading: str
    db_id: Optional[int] = None                 # legacy import id, when present
    target_id: Optional[int] = None             # target transaction for REVERSAL rows
    event_id: Optional[str] = None              # stable Markdown event identity
    target_event_id: Optional[str] = None       # stable Markdown target reference
    legacy_db_id: Optional[int] = None          # migration-only source SQLite id
    legacy_target_id: Optional[int] = None      # migration-only source target_id
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
        t.target_id = int(f["target_id"]) if f.get("target_id") else None
        t.event_id = (f.get("id") or f.get("event_id") or "").strip() or t.event_id
        t.target_event_id = (f.get("target_event_id") or "").strip() or None
        t.legacy_db_id = int(f["legacy_db_id"]) if f.get("legacy_db_id") else None
        t.legacy_target_id = int(f["legacy_target_id"]) if f.get("legacy_target_id") else None
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
    txns_by_id = {t.db_id: t for t in sorted_txns if t.db_id is not None}
    txns_by_event_id = {t.event_id: t for t in sorted_txns if t.event_id}
    for t in sorted_txns:
        if t.date > cutoff:
            break
        try:
            _apply_one(t, state, txns_by_id=txns_by_id, txns_by_event_id=txns_by_event_id)
        except Exception as e:
            state.issues.append(f"{t.date} {t.type} {t.ticker or ''}: {e}")
    return state


def _bump_cash(state: ReplayState, currency: Optional[str], delta: float) -> None:
    if not currency:
        return
    state.cash[currency] = state.cash.get(currency, 0.0) + delta


def _apply_one(
    t: Transaction,
    state: ReplayState,
    *,
    txns_by_id: Optional[Dict[int, Transaction]] = None,
    txns_by_event_id: Optional[Dict[str, Transaction]] = None,
) -> None:
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

    elif t.type == "REVERSAL":
        _apply_reversal(t, state, txns_by_id or {}, txns_by_event_id or {})

    elif t.type == "ADJUST":
        if not t.ticker:
            state.issues.append(f"{t.date} ADJUST missing ticker")
            return
        if not t.bucket:
            state.issues.append(f"{t.date} ADJUST {t.ticker} missing bucket")
            return
        lots = state.open_lots.get(t.ticker, [])
        if not lots:
            state.issues.append(f"{t.date} ADJUST {t.ticker} has no open lots")
            return
        for lot in lots:
            lot.bucket = t.bucket
            if t.market:
                lot.market = t.market
            if t.currency:
                lot.currency = t.currency

    else:
        state.issues.append(f"{t.date} unknown transaction type: {t.type}")


def _target_label(t: Transaction) -> str:
    if t.target_event_id:
        return f"target_event_id {t.target_event_id}"
    if t.target_id is not None:
        return f"target_id {t.target_id}"
    if t.legacy_target_id is not None:
        return f"legacy_target_id {t.legacy_target_id}"
    return "target"


def _apply_reversal(
    t: Transaction,
    state: ReplayState,
    txns_by_id: Dict[int, Transaction],
    txns_by_event_id: Dict[str, Transaction],
) -> None:
    target: Optional[Transaction] = None
    if t.target_event_id:
        target = txns_by_event_id.get(t.target_event_id)
        if target is None:
            state.issues.append(f"{t.date} REVERSAL target_event_id {t.target_event_id} not found")
            return
    elif t.target_id is not None:
        target = txns_by_id.get(t.target_id)
        if target is None:
            state.issues.append(f"{t.date} REVERSAL target_id {t.target_id} not found")
            return
    elif t.legacy_target_id is not None:
        target = txns_by_id.get(t.legacy_target_id)
        if target is None:
            for candidate in txns_by_event_id.values():
                if candidate.legacy_db_id == t.legacy_target_id:
                    target = candidate
                    break
        if target is None:
            state.issues.append(f"{t.date} REVERSAL legacy_target_id {t.legacy_target_id} not found")
            return
    else:
        state.issues.append(f"{t.date} REVERSAL missing target_event_id/target_id")
        return

    label = _target_label(t)

    if target.type == "BUY":
        if target.ticker is None or target.qty is None or target.price is None:
            state.issues.append(f"{t.date} REVERSAL {label} incomplete BUY")
            return
        lots = state.open_lots.get(target.ticker, [])
        remaining = target.qty
        for lot in lots:
            if remaining <= 1e-9:
                break
            if lot.acq_date != target.date:
                continue
            if abs(lot.cost - target.price) > 1e-6:
                continue
            take = min(lot.qty, remaining)
            lot.qty -= take
            remaining -= take
        if remaining > 1e-6:
            state.issues.append(
                f"{t.date} REVERSAL {label} BUY short by {remaining:g}"
            )
        state.open_lots[target.ticker] = [
            lot for lot in state.open_lots.get(target.ticker, []) if lot.qty > 1e-9
        ]
        if not state.open_lots[target.ticker]:
            del state.open_lots[target.ticker]
        currency = target.currency or "USD"
        _bump_cash(
            state,
            target.cash_account or currency,
            target.qty * target.price + (target.fees or 0.0),
        )
        return

    if target.type == "SELL":
        if target.ticker is None or target.qty is None or target.price is None:
            state.issues.append(f"{t.date} REVERSAL {label} incomplete SELL")
            return
        if not target.lots_consumed:
            state.issues.append(f"{t.date} REVERSAL {label} SELL missing lot-consumption audit")
            return
        currency = target.currency or "USD"
        for acq_date, cost, qty in target.lots_consumed:
            state.open_lots.setdefault(target.ticker, []).append(OpenLot(
                ticker=target.ticker,
                qty=qty,
                cost=cost,
                acq_date=acq_date,
                bucket=target.bucket or "Mid Term",
                market=target.market or "US",
                currency=currency,
            ))
        _bump_cash(state, target.cash_account or currency, -(target.qty * target.price - (target.fees or 0.0)))
        return

    if target.type == "DEPOSIT" and target.amount is not None:
        _bump_cash(state, target.cash_account or target.currency or "USD", -target.amount)
        return
    if target.type == "WITHDRAW" and target.amount is not None:
        _bump_cash(state, target.cash_account or target.currency or "USD", target.amount)
        return
    if target.type == "DIVIDEND" and target.amount is not None:
        _bump_cash(state, target.cash_account or target.currency or "USD", -target.amount)
        return
    if target.type == "FEE" and target.amount is not None:
        _bump_cash(state, target.cash_account or target.currency or "USD", target.amount)
        return

    state.issues.append(f"{t.date} REVERSAL {label} unsupported target type {target.type}")


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
    series = history.get(ticker) or history.get(ticker.upper())
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


def _benchmark_config_from_prices(prices: Dict[str, Any]) -> Dict[str, Any]:
    payload = prices.get("_benchmarks")
    if isinstance(payload, dict):
        return payload
    return load_benchmark_config(None)


def _benchmark_spec_for(config: Dict[str, Any], market: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if market is None:
        spec = config.get("global")
    else:
        markets = config.get("markets") if isinstance(config.get("markets"), dict) else {}
        spec = markets.get(market)
    return spec if isinstance(spec, dict) and spec.get("ticker") else None


def _benchmark_return_pct(
    *,
    spec: Optional[Dict[str, Any]],
    period: str,
    boundary_iso: str,
    latest_prices: Dict[str, float],
    history: Dict[str, List[Dict[str, Any]]],
    audit: List[str],
    label: str,
) -> Optional[float]:
    if not spec:
        return None
    ticker = str(spec.get("ticker") or "").upper()
    if not ticker:
        return None
    end_price = latest_prices.get(ticker)
    if end_price is None:
        audit.append(f"{period}: benchmark {label} {ticker}: missing latest price")
        return None
    start_price = _historical_close(history, ticker, boundary_iso)
    if start_price is None:
        audit.append(f"{period}: benchmark {label} {ticker}: no historical close at {boundary_iso}")
        return None
    if abs(start_price) <= 1e-12:
        audit.append(f"{period}: benchmark {label} {ticker}: historical close at {boundary_iso} is zero")
        return None
    return round(((float(end_price) / float(start_price)) - 1.0) * 100.0, 4)


def _spread_pct(return_pct: Optional[float], benchmark_return_pct: Optional[float]) -> Optional[float]:
    if return_pct is None or benchmark_return_pct is None:
        return None
    return round(float(return_pct) - float(benchmark_return_pct), 4)


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
    benchmark_config = _benchmark_config_from_prices(prices)

    rows: List[Dict[str, Any]] = []
    for period in period_order:
        if period not in boundaries:
            rows.append({
                "period": period, "pnl": None, "return_pct": None,
                "realized": None, "unrealized_delta": None, "net_flows": None,
                "starting_value": None, "ending_value": end_value,
                "benchmark_ticker": None, "benchmark_return_pct": None, "spread_pct": None,
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
        ret_pct = round(ret * 100.0, 4) if ret is not None else None
        global_benchmark_spec = _benchmark_spec_for(benchmark_config, None)
        global_benchmark_return = _benchmark_return_pct(
            spec=global_benchmark_spec,
            period=period,
            boundary_iso=boundary_iso,
            latest_prices=latest_prices,
            history=history,
            audit=period_audit,
            label="global",
        )
        global_benchmark_ticker = (
            str(global_benchmark_spec.get("ticker")).upper()
            if global_benchmark_spec is not None and global_benchmark_spec.get("ticker")
            else None
        )
        global_spread = _spread_pct(ret_pct, global_benchmark_return)

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
        for k in sorted(per_market_keys):
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
            market_benchmark_spec = _benchmark_spec_for(benchmark_config, k)
            market_benchmark_ticker = (
                str(market_benchmark_spec.get("ticker")).upper()
                if market_benchmark_spec is not None and market_benchmark_spec.get("ticker")
                else None
            )
            market_benchmark_return = _benchmark_return_pct(
                spec=market_benchmark_spec,
                period=period,
                boundary_iso=boundary_iso,
                latest_prices=latest_prices,
                history=history,
                audit=period_audit,
                label=k,
            )
            per_market_detail[k] = {
                "pnl": round(value, 2),
                "realized": round(r, 2),
                "unrealized_delta": round(ud, 2),
                "return_pct": ret_m,
                "benchmark_ticker": market_benchmark_ticker,
                "benchmark_return_pct": market_benchmark_return,
                "spread_pct": _spread_pct(ret_m, market_benchmark_return),
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
            "return_pct": ret_pct,
            "benchmark_ticker": global_benchmark_ticker,
            "benchmark_return_pct": global_benchmark_return,
            "spread_pct": global_spread,
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

    reversal_txns = [
        Transaction(
            seq=0,
            db_id=1,
            date="2026-04-10",
            type="BUY",
            ticker="MARRY",
            raw_heading="## 2026-04-10 BUY MARRY",
            qty=100,
            price=19.13,
            currency="USD",
            cash_account="USD",
            bucket="Mid Term",
            market="US",
        ),
        Transaction(
            seq=1,
            db_id=2,
            date="2026-04-11",
            type="REVERSAL",
            ticker=None,
            raw_heading="## 2026-04-11 REVERSAL",
            target_id=1,
        ),
        Transaction(
            seq=2,
            db_id=3,
            date="2026-04-11",
            type="BUY",
            ticker="MRAAY",
            raw_heading="## 2026-04-11 BUY MRAAY",
            qty=100,
            price=19.13,
            currency="USD",
            cash_account="USD",
            bucket="Mid Term",
            market="US",
        ),
    ]
    reversal_state = replay(reversal_txns)
    if "MARRY" in reversal_state.open_lots:
        failures.append("reversal: expected corrected-away MARRY lot to be removed")
    mraay_qty = sum(l.qty for l in reversal_state.open_lots.get("MRAAY", []))
    if abs(mraay_qty - 100) > 1e-6:
        failures.append(f"reversal: MRAAY open qty expected 100, got {mraay_qty}")
    if reversal_state.issues:
        failures.append(f"reversal: unexpected issues {reversal_state.issues}")

    adjust_txns = [
        Transaction(
            seq=0,
            date="2026-04-10",
            type="BUY",
            ticker="NVDA",
            raw_heading="## 2026-04-10 BUY NVDA",
            qty=10,
            price=200,
            currency="USD",
            cash_account="USD",
            bucket="Mid Term",
            market="US",
        ),
        Transaction(
            seq=1,
            date="2026-04-11",
            type="ADJUST",
            ticker="NVDA",
            raw_heading="## 2026-04-11 ADJUST NVDA",
            bucket="Long Term (Not Sell)",
            market="US",
            currency="USD",
        ),
    ]
    adjust_state = replay(adjust_txns)
    adjust_lots = adjust_state.open_lots.get("NVDA", [])
    if not adjust_lots or any(l.bucket != "Long Term (Not Sell)" for l in adjust_lots):
        failures.append("adjust: expected NVDA lot bucket to be relabeled")
    if abs(adjust_state.cash.get("USD", 0.0) + 2000) > 1e-6:
        failures.append(f"adjust: bucket relabel should not change cash, got {adjust_state.cash}")
    if adjust_state.issues:
        failures.append(f"adjust: unexpected issues {adjust_state.issues}")

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
        "VT": {"latest_price": 110.0, "currency": "USD"},
        "VTI": {"latest_price": 55.0, "currency": "USD"},
        "_fx": {"rates": {}},
        "_benchmarks": {
            "source": "self-check",
            "global": {"ticker": "VT", "market": "US"},
            "markets": {"us": {"ticker": "VTI", "market": "US"}},
        },
        "_history": {
            "NVDA": [
                {"date": "2026-04-29", "close": 215.50},
                {"date": "2026-04-28", "close": 213.00},
            ],
            "VT": [
                {"date": "2026-04-29", "close": 100.00},
                {"date": "2026-04-28", "close": 99.00},
            ],
            "VTI": [
                {"date": "2026-04-29", "close": 50.00},
                {"date": "2026-04-28", "close": 49.00},
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
    if r1.get("benchmark_ticker") != "VT":
        failures.append(f"profit_panel: global benchmark ticker expected VT, got {r1.get('benchmark_ticker')}")
    if abs(float(r1.get("benchmark_return_pct") or 0.0) - 10.0) > 1e-6:
        failures.append(f"profit_panel: global benchmark return expected 10, got {r1.get('benchmark_return_pct')}")
    expected_spread = round(float(r1.get("return_pct") or 0.0) - 10.0, 4)
    if abs(float(r1.get("spread_pct") or 0.0) - expected_spread) > 1e-6:
        failures.append(f"profit_panel: global spread expected {expected_spread}, got {r1.get('spread_pct')}")
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
            if usd.get("benchmark_ticker") != "VTI":
                failures.append(f"profit_panel: us benchmark ticker expected VTI, got {usd.get('benchmark_ticker')}")
            if abs(float(usd.get("benchmark_return_pct") or 0.0) - 10.0) > 1e-6:
                failures.append(f"profit_panel: us benchmark return expected 10, got {usd.get('benchmark_return_pct')}")
            if usd.get("return_pct") is not None:
                expected_us_spread = round(float(usd.get("return_pct")) - 10.0, 4)
                if abs(float(usd.get("spread_pct") or 0.0) - expected_us_spread) > 1e-6:
                    failures.append(f"profit_panel: us spread expected {expected_us_spread}, got {usd.get('spread_pct')}")

    missing_benchmark_prices = {
        "NVDA": {"latest_price": 220.0, "currency": "USD"},
        "VT": {"latest_price": 110.0, "currency": "USD"},
        "_fx": {"rates": {}},
        "_benchmarks": {"global": {"ticker": "VT", "market": "US"}, "markets": {}},
        "_history": {"NVDA": [{"date": "2026-04-29", "close": 215.50}]},
    }
    missing_panel = compute_profit_panel(txns, missing_benchmark_prices, base="USD", today=_dt.date(2026, 4, 30))
    missing_r1 = missing_panel["rows"][0]
    if missing_r1.get("benchmark_return_pct") is not None or missing_r1.get("spread_pct") is not None:
        failures.append("profit_panel: missing benchmark history should produce null benchmark/spread")
    if not any("benchmark global VT" in str(a) for a in (missing_r1.get("audit") or [])):
        failures.append("profit_panel: missing benchmark history should emit audit")

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

    # 12. Markdown append/import paths: imports append canonical event files and
    #     generated caches are rebuilt from event replay.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        md_path = td_path / "T.md"
        md_path.write_text(sample, encoding="utf-8")
        ledger_dir = td_path / "ledger"
        inserted, errs = ledger_import_md(md_path, ledger_dir)
        if errs or inserted != 4:
            failures.append(f"ledger_import_md: errs={errs}, inserted={inserted}")
        loaded = load_transactions_markdown(ledger_dir)
        if len(loaded) != 4:
            failures.append(f"load_transactions_markdown: expected 4 txns, got {len(loaded)}")
        else:
            md_state = replay(parse_transactions(md_path))
            ledger_state = replay(loaded)
            md_open = sum(l.qty for lots in md_state.open_lots.values() for l in lots)
            ledger_open = sum(l.qty for lots in ledger_state.open_lots.values() for l in lots)
            if abs(md_open - ledger_open) > 1e-6:
                failures.append(f"ledger parity: open qty md={md_open} ledger={ledger_open}")
            if abs(md_state.cash.get("USD", 0) - ledger_state.cash.get("USD", 0)) > 1e-2:
                failures.append(
                    f"ledger parity: USD cash md={md_state.cash.get('USD')} ledger={ledger_state.cash.get('USD')}"
                )

        csv_path = td_path / "bad.csv"
        csv_path.write_text(
            "date,type,ticker,qty,price,currency,cash_account\n"
            "2026-04-29,BUY,TSLA,5,$200,USD,USD\n"
            "2026-04-29,SELL,,,$300,USD,USD\n",
            encoding="utf-8",
        )
        inserted_c, errs_c = ledger_import_csv(csv_path, td_path / "csv-ledger")
        if inserted_c != 0 or not errs_c:
            failures.append(f"csv import: expected validation failure, got inserted={inserted_c}")

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
        json_ledger = td_path / "json-ledger"
        inserted_j, errs_j = ledger_import_json(json_path, json_ledger)
        if errs_j or inserted_j != 3:
            failures.append(f"json import: errs={errs_j}, inserted={inserted_j}")
        else:
            jstate = replay(load_transactions_markdown(json_ledger))
            j_realized = sum(ev.realized_native for ev in jstate.realized_events if ev.type == "SELL_LOT")
            if abs(j_realized - (220 - 200) * 10) > 1e-6:
                failures.append(f"json import: realized expected 200, got {j_realized}")

            preview_account = td_path / "preview-account"
            preview_ledger = preview_account / "ledger"
            inserted_p, errs_p = ledger_import_json(json_path, preview_ledger)
            if errs_p or inserted_p != 3:
                failures.append(f"preview seed import: errs={errs_p}, inserted={inserted_p}")
            preview_path = td_path / "preview.json"
            preview_path.write_text(json.dumps([
                {"date": "2026-04-20", "type": "SELL", "ticker": "AAPL", "qty": 20,
                 "price": 210, "currency": "USD", "cash_account": "USD",
                 "bucket": "Mid Term", "market": "US",
                 "lots": [{"acq_date": "2026-04-11", "cost": 200, "qty": 20}]},
                {"date": "2026-04-20", "type": "BUY", "ticker": "MSFT", "qty": 2,
                 "price": 300, "currency": "USD", "cash_account": "USD",
                 "bucket": "Mid Term", "market": "US"},
            ]), encoding="utf-8")
            before_preview_events = len(load_event_dicts(preview_ledger))
            preview, preview_errs = db_preview_json(preview_path, preview_account / "transactions.db")
            after_preview_events = len(load_event_dicts(preview_ledger))
            if preview_errs or not preview.get("ok"):
                failures.append(f"preview-json: errs={preview_errs}, preview={preview}")
            elif preview.get("would_append_count") != 2:
                failures.append(f"preview-json: expected 2 appends, got {preview.get('would_append_count')}")
            elif preview["positions"]["AAPL"]["after"]["qty"] != 0:
                failures.append(f"preview-json: expected AAPL qty 0, got {preview['positions']['AAPL']}")
            elif abs(preview["realized_pnl"]["totals"].get("AAPL/USD", 0) - 200) > 1e-6:
                failures.append(f"preview-json: realized total mismatch {preview['realized_pnl']}")
            elif before_preview_events != after_preview_events:
                failures.append("preview-json: live ledger mutated during preview")

        inserted_m, errs_m = ledger_add(json.dumps({
            "date": "2026-04-30", "type": "DIVIDEND", "ticker": "GOOG",
            "amount": 80, "currency": "USD", "cash_account": "USD",
            "rationale": "Q1 GOOG", "tags": "dividend",
        }), ledger_dir)
        if errs_m or inserted_m != 1:
            failures.append(f"ledger_add: errs={errs_m}, inserted={inserted_m}")

        loaded_lots = load_holdings_lots_markdown(ledger_dir)
        nvda_lots = [l for l in loaded_lots if l.ticker == "NVDA"]
        if not nvda_lots or abs(sum(l.quantity for l in nvda_lots) - 25) > 1e-6:
            failures.append(
                f"load_holdings_lots_markdown: NVDA qty expected 25, "
                f"got {sum(l.quantity for l in nvda_lots) if nvda_lots else 0}"
            )
        cash_lots = [l for l in loaded_lots if l.bucket == "Cash Holdings" and l.ticker == "USD"]
        if not cash_lots:
            failures.append("load_holdings_lots_markdown: USD cash row missing")
        before = ledger_rebuild_cache(ledger_dir)
        again = ledger_rebuild_cache(ledger_dir)
        if before.get("source_tree_hash") != again.get("source_tree_hash"):
            failures.append(f"ledger rebuild: not idempotent ({before} vs {again})")

        md_reversal = [
            Transaction(
                seq=0,
                event_id="txn-20260501-000001-buy-test",
                date="2026-05-01",
                type="BUY",
                ticker="TEST",
                raw_heading="## 2026-05-01 BUY TEST",
                qty=2,
                price=10,
                currency="USD",
                cash_account="USD",
                bucket="Mid Term",
                market="US",
            ),
            Transaction(
                seq=1,
                event_id="txn-20260502-000002-reversal-cash",
                target_event_id="txn-20260501-000001-buy-test",
                date="2026-05-02",
                type="REVERSAL",
                ticker=None,
                raw_heading="## 2026-05-02 REVERSAL",
            ),
        ]
        md_reversal_state = replay(md_reversal)
        if md_reversal_state.open_lots:
            failures.append(f"md reversal: expected no open lots, got {md_reversal_state.open_lots}")
        if md_reversal_state.issues:
            failures.append(f"md reversal: unexpected issues {md_reversal_state.issues}")

        ok_cache, cache_issues = ledger_verify_cache(ledger_dir)
        if not ok_cache:
            failures.append(f"ledger cache verify failed: {cache_issues}")
        open_lots_cache_path = generated_dir(ledger_dir) / "open_lots.json"
        if not open_lots_cache_path.exists():
            failures.append("ledger cache: open_lots.json not generated")
        else:
            original_open_lots_cache = read_json(open_lots_cache_path)
            tampered_open_lots_cache = json.loads(json.dumps(original_open_lots_cache))
            tampered_open_lots_cache["_meta"]["source_tree_hash"] = "tampered"
            write_json(open_lots_cache_path, tampered_open_lots_cache)
            tampered_ok, _tampered_issues = ledger_verify_cache(ledger_dir)
            if tampered_ok:
                failures.append("ledger cache verify accepted tampered metadata")
            write_json(open_lots_cache_path, original_open_lots_cache)
        try:
            _sanitize_migration_id("../evil")
            failures.append("migration id validator accepted path traversal")
        except ValueError:
            pass
        multiline_event = {
            "schema": LEDGER_SCHEMA,
            "id": "txn-20260503-000003-deposit-cash",
            "date": "2026-05-03",
            "type": "DEPOSIT",
            "amount": 10,
            "currency": "USD",
            "cash_account": "USD",
            "rationale": "line one\nline two",
        }
        multiline_path = ledger_dir / "events" / "2026" / "05" / "txn-20260503-000003-deposit-cash.md"
        write_event_file(multiline_event, multiline_path)
        parsed_multiline = load_event_dicts(ledger_dir)
        match = [e for e in parsed_multiline if e.get("id") == multiline_event["id"]]
        if not match or match[0].get("rationale") != multiline_event["rationale"]:
            failures.append("ledger event parser/writer failed multiline field round-trip")
        if load_transactions(ledger=ledger_dir, store="markdown")[0].event_id is None:
            failures.append("load_transactions: explicit markdown store should load Markdown events")
        bad_event = {
            "schema": LEDGER_SCHEMA,
            "id": "txn-20260504-000004-buy-bad",
            "date": "2026-05-04",
            "type": "BUY",
        }
        bad_path = td_path / "bad-ledger" / "events" / "2026" / "05" / "txn-20260504-000004-buy-bad.md"
        bad_path.parent.mkdir(parents=True)
        bad_path.write_text("- schema: investment-ledger-event/v1\n- id: txn-20260504-000004-buy-bad\n- date: 2026-05-04\n- type: BUY\n", encoding="utf-8")
        try:
            load_transactions_markdown(td_path / "bad-ledger")
            failures.append("ledger validator accepted BUY missing ticker/qty/price")
        except ValueError:
            pass
        bad_rev_dir = td_path / "bad-reversal-ledger"
        bad_rev_path = bad_rev_dir / "events" / "2026" / "05" / "txn-20260505-000005-reversal-cash.md"
        bad_rev_path.parent.mkdir(parents=True)
        bad_rev_path.write_text(
            "- schema: investment-ledger-event/v1\n"
            "- id: txn-20260505-000005-reversal-cash\n"
            "- date: 2026-05-05\n"
            "- type: REVERSAL\n"
            "- legacy_target_id: 1\n",
            encoding="utf-8",
        )
        try:
            load_transactions_markdown(bad_rev_dir)
            failures.append("ledger validator accepted REVERSAL with legacy_target_id but no target_event_id")
        except ValueError:
            pass

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("OK: transactions self-check passed.")
    return 0


# --------------------------------------------------------------------------- #
# Markdown compatibility store (legacy-named db CLI)
# --------------------------------------------------------------------------- #

DEFAULT_DB_PATH = Path("transactions" + ".db")  # legacy migration input path only


def _legacy_ledger_dir_for_path(path: Path) -> Path:
    return path.parent / "ledger"


def db_init(path: Path) -> str:
    """Compatibility shim: initialize the Markdown ledger skeleton."""
    ensure_ledger_skeleton(_legacy_ledger_dir_for_path(path))
    return "markdown-ledger-ready"


def db_rebuild_balances(db_path: Path) -> Dict[str, int]:
    """Compatibility shim: rebuild generated Markdown ledger caches."""
    result = ledger_rebuild_cache(_legacy_ledger_dir_for_path(db_path))
    return {"generated": len(result.get("generated", []))}



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
    if txn_type == "REVERSAL" and all(
        d.get(k) in (None, "") for k in ("target_event_id", "target_id", "legacy_target_id")
    ):
        errs.append("REVERSAL missing target_event_id/target_id")
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
    t.target_id = int(d["target_id"]) if d.get("target_id") not in (None, "") else None
    t.event_id = str(d.get("id") or d.get("event_id") or "").strip() or None
    t.target_event_id = str(d.get("target_event_id") or "").strip() or None
    t.legacy_db_id = int(d["legacy_db_id"]) if d.get("legacy_db_id") not in (None, "") else None
    t.legacy_target_id = int(d["legacy_target_id"]) if d.get("legacy_target_id") not in (None, "") else None
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



def _transaction_to_event_dict(
    txn: Transaction,
    *,
    event_id: str,
    source: str,
    source_ref: Optional[str],
) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        "schema": LEDGER_SCHEMA,
        "id": event_id,
        "date": txn.date,
        "type": txn.type,
        "created_at": now_utc(),
        "source": source,
    }
    if source_ref:
        event["source_ref"] = source_ref
    for key in (
        "ticker", "qty", "price", "amount", "fees", "currency", "cash_account", "bucket", "market",
        "from_amount", "from_currency", "from_cash_account", "to_amount", "to_currency", "to_cash_account",
        "rate", "target_event_id", "rationale",
    ):
        value = getattr(txn, key, None)
        if value not in (None, ""):
            event[key] = value
    if txn.tags:
        event["tags"] = ", ".join(txn.tags)
    if txn.lots_consumed:
        event["lots"] = [
            {"acq_date": acq_date, "cost": cost, "qty": qty}
            for acq_date, cost, qty in txn.lots_consumed
        ]
    return event


def _next_event_ordinal(ledger_dir: Path) -> int:
    try:
        events = load_event_dicts(ledger_dir)
    except Exception:
        events = []
    ordinals = [ordinal_from_event_id(str(event.get("id") or "")) or 0 for event in events]
    return (max(ordinals) if ordinals else 0) + 1


def ledger_import_records(
    ledger_dir: Path,
    records: List[Dict[str, Any]],
    *,
    source: str,
    source_ref: Optional[str],
) -> Tuple[int, List[str]]:
    """Validate and append canonical transaction dicts as Markdown events."""
    errors: List[str] = []
    parsed: List[Transaction] = []
    for i, rec in enumerate(records):
        rec_errs = _validate_canonical_dict(rec)
        if rec_errs:
            errors.extend(f"row {i + 1}: {e}" for e in rec_errs)
            continue
        parsed.append(_dict_to_transaction(rec, seq=i))
    if errors:
        return 0, errors
    ensure_ledger_skeleton(ledger_dir)
    ordinal = _next_event_ordinal(ledger_dir)
    for offset, txn in enumerate(parsed):
        event_id = event_id_for(txn.date, txn.type, txn.ticker, ordinal + offset)
        event = _transaction_to_event_dict(txn, event_id=event_id, source=source, source_ref=source_ref)
        write_event_file(event, event_path_for(ledger_dir, event))
    ledger_rebuild_cache(ledger_dir)
    return len(parsed), []


def ledger_import_md(md_path: Path, ledger_dir: Path) -> Tuple[int, List[str]]:
    txns = parse_transactions(md_path)
    records: List[Dict[str, Any]] = []
    for txn in txns:
        rec = dict(txn.fields)
        rec.setdefault("date", txn.date)
        rec.setdefault("type", txn.type)
        if txn.ticker:
            rec.setdefault("ticker", txn.ticker)
        if txn.lots_consumed:
            rec["lots"] = [
                {"acq_date": acq_date, "cost": cost, "qty": qty}
                for acq_date, cost, qty in txn.lots_consumed
            ]
        records.append(rec)
    return ledger_import_records(ledger_dir, records, source="md", source_ref=str(md_path))

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



def ledger_import_csv(
    csv_path: Path,
    ledger_dir: Path,
    *,
    mapping: Optional[Dict[str, str]] = None,
) -> Tuple[int, List[str]]:
    mapping = mapping or {}
    records: List[Dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapped = _apply_csv_mapping(row, mapping)
            if mapped:
                records.append(mapped)
    return ledger_import_records(ledger_dir, records, source="csv", source_ref=str(csv_path))


def ledger_import_json(json_path: Path, ledger_dir: Path) -> Tuple[int, List[str]]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return 0, ["JSON root must be a list of transaction objects (or a single object)"]
    return ledger_import_records(ledger_dir, payload, source="json", source_ref=str(json_path))


def ledger_add(json_blob: str, ledger_dir: Path) -> Tuple[int, List[str]]:
    try:
        payload = json.loads(json_blob)
    except json.JSONDecodeError as exc:
        return 0, [f"invalid JSON: {exc}"]
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return 0, ["JSON must be an object or array of objects"]
    return ledger_import_records(ledger_dir, payload, source="message", source_ref=None)


def _state_cash_delta(before: ReplayState, after: ReplayState) -> Dict[str, float]:
    currencies = sorted(set(before.cash) | set(after.cash))
    return {
        currency: round(after.cash.get(currency, 0.0) - before.cash.get(currency, 0.0), 10)
        for currency in currencies
        if abs(after.cash.get(currency, 0.0) - before.cash.get(currency, 0.0)) > 1e-9
    }


def _position_preview_row(state: ReplayState, ticker: str) -> Dict[str, Any]:
    lots = state.open_lots.get(ticker, [])
    qty = sum(lot.qty for lot in lots)
    cost_total = sum(lot.qty * lot.cost for lot in lots)
    currencies = sorted({lot.currency for lot in lots})
    markets = sorted({lot.market for lot in lots})
    buckets = []
    for lot in lots:
        if lot.bucket not in buckets:
            buckets.append(lot.bucket)
    return {
        "qty": round(qty, 10),
        "avg_cost": round(cost_total / qty, 10) if qty else None,
        "cost_total": round(cost_total, 10),
        "lot_count": len(lots),
        "currencies": currencies,
        "markets": markets,
        "buckets": buckets,
    }


def _realized_event_preview(event: RealizedEvent) -> Dict[str, Any]:
    return {
        "date": event.date,
        "ticker": event.ticker,
        "type": event.type,
        "qty": round(event.qty, 10),
        "sell_price": event.sell_price,
        "cost": event.cost,
        "realized_native": round(event.realized_native, 10),
        "currency": event.currency,
        "acq_date": event.acq_date,
    }


def db_preview_json(json_path: Path, db_path: Path) -> Tuple[Dict[str, Any], List[str]]:
    """Dry-run a canonical JSON import against a temporary ledger copy.

    This is the fast confirmation helper for natural-language transaction
    intake: it exercises the same import/replay/cache path as a real
    `db import-json`, but never writes to the live account ledger.
    """
    import tempfile

    if not json_path.exists():
        return {}, [f"{json_path} not found"]
    live_ledger = _legacy_ledger_dir_for_path(db_path)
    if not live_ledger.exists():
        return {}, [f"Markdown ledger not found: {live_ledger}"]
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"invalid JSON: {exc}"]
    records = [payload] if isinstance(payload, dict) else payload
    if not isinstance(records, list) or any(not isinstance(rec, dict) for rec in records):
        return {}, ["JSON root must be a list of transaction objects (or a single object)"]

    touched_tickers = sorted({
        _normalize_ticker(str(record["ticker"]))
        for record in records
        if record.get("ticker")
    })
    before_events = load_event_dicts(live_ledger)
    before_txns = load_transactions_markdown(live_ledger)
    before_state = replay(before_txns)

    with tempfile.TemporaryDirectory(prefix="investments_trade_preview_") as td:
        dry_root = Path(td)
        dry_ledger = dry_root / "ledger"
        shutil.copytree(live_ledger, dry_ledger)
        inserted, errors = ledger_import_json(json_path, dry_ledger)
        if errors:
            return {
                "schema": "transaction-import-preview/v1",
                "ok": False,
                "input": str(json_path),
                "account_db": str(db_path),
                "record_count": len(records),
                "would_append_count": 0,
                "errors": errors,
            }, []
        cache_ok, cache_issues = ledger_verify_cache(dry_ledger)
        after_events = load_event_dicts(dry_ledger)
        after_txns = load_transactions_markdown(dry_ledger)
        after_state = replay(after_txns)

    before_positions = {ticker: _position_preview_row(before_state, ticker) for ticker in touched_tickers}
    after_positions = {ticker: _position_preview_row(after_state, ticker) for ticker in touched_tickers}
    position_changes = {}
    for ticker in touched_tickers:
        before_row = before_positions[ticker]
        after_row = after_positions[ticker]
        position_changes[ticker] = {
            "before": before_row,
            "after": after_row,
            "delta_qty": round(after_row["qty"] - before_row["qty"], 10),
            "delta_cost_total": round(after_row["cost_total"] - before_row["cost_total"], 10),
        }

    new_realized = after_state.realized_events[len(before_state.realized_events):]
    realized_totals: Dict[str, float] = {}
    for event in new_realized:
        key = f"{event.ticker or event.type}/{event.currency}"
        realized_totals[key] = round(realized_totals.get(key, 0.0) + event.realized_native, 10)

    issues = list(after_state.issues)
    if not cache_ok:
        issues.extend(f"cache: {issue}" for issue in cache_issues)

    preview = {
        "schema": "transaction-import-preview/v1",
        "ok": not issues,
        "input": str(json_path),
        "account_db": str(db_path),
        "record_count": len(records),
        "would_append_count": inserted,
        "transaction_count": {
            "before": len(before_events),
            "after": len(after_events),
            "delta": len(after_events) - len(before_events),
        },
        "open_lot_count": {
            "before": sum(len(lots) for lots in before_state.open_lots.values()),
            "after": sum(len(lots) for lots in after_state.open_lots.values()),
        },
        "cash": {
            "before": dict(sorted((ccy, round(amount, 10)) for ccy, amount in before_state.cash.items())),
            "after": dict(sorted((ccy, round(amount, 10)) for ccy, amount in after_state.cash.items())),
            "delta": _state_cash_delta(before_state, after_state),
        },
        "positions": position_changes,
        "realized_pnl": {
            "events": [_realized_event_preview(event) for event in new_realized],
            "totals": dict(sorted(realized_totals.items())),
        },
        "issues": issues,
    }
    return preview, []


# Compatibility names retained for older internal callers; they now target Markdown.
def db_import_records(db_path: Path, records: List[Dict[str, Any]], *, source: str, source_ref: Optional[str]) -> Tuple[int, List[str]]:
    return ledger_import_records(_legacy_ledger_dir_for_path(db_path), records, source=source, source_ref=source_ref)


def db_import_md(md_path: Path, db_path: Path) -> Tuple[int, List[str]]:
    return ledger_import_md(md_path, _legacy_ledger_dir_for_path(db_path))


def db_import_csv(csv_path: Path, db_path: Path, *, mapping: Optional[Dict[str, str]] = None) -> Tuple[int, List[str]]:
    return ledger_import_csv(csv_path, _legacy_ledger_dir_for_path(db_path), mapping=mapping)


def db_import_json(json_path: Path, db_path: Path) -> Tuple[int, List[str]]:
    return ledger_import_json(json_path, _legacy_ledger_dir_for_path(db_path))


def db_add(json_blob: str, db_path: Path) -> Tuple[int, List[str]]:
    return ledger_add(json_blob, _legacy_ledger_dir_for_path(db_path))


def load_transactions_db(db_path: Path) -> List[Transaction]:
    return load_transactions_markdown(_legacy_ledger_dir_for_path(db_path))


def db_dump(db_path: Path) -> List[Dict[str, Any]]:
    return load_event_dicts(_legacy_ledger_dir_for_path(db_path))


def db_stats(db_path: Path) -> Dict[str, Any]:
    events = load_event_dicts(_legacy_ledger_dir_for_path(db_path))
    by_type: Dict[str, int] = {}
    tickers: set[str] = set()
    dates: List[str] = []
    for event in events:
        typ = str(event.get("type") or "")
        if typ:
            by_type[typ] = by_type.get(typ, 0) + 1
        if event.get("ticker"):
            tickers.add(str(event["ticker"]))
        if event.get("date"):
            dates.append(str(event["date"]))
    return {
        "store": "markdown",
        "total_transactions": len(events),
        "by_type": dict(sorted(by_type.items())),
        "tickers": sorted(tickers),
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
    }


# --------------------------------------------------------------------------- #
# Ledger store / Markdown migration helpers
# --------------------------------------------------------------------------- #

def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_DB_EVENT_FIELD_MAP: Sequence[Tuple[str, str, str]] = (
    ("date", "date", "str"),
    ("type", "type", "str"),
    ("ticker", "ticker", "ticker"),
    ("qty", "qty", "float"),
    ("price", "price", "float"),
    ("gross", "gross", "float"),
    ("fees", "fees", "float"),
    ("net", "net", "float"),
    ("amount", "amount", "float"),
    ("currency", "currency", "upper"),
    ("cash_account", "cash_account", "upper"),
    ("bucket", "bucket", "str"),
    ("market", "market", "str"),
    ("rationale", "rationale", "str"),
    ("tags", "tags", "str"),
    ("from_amount", "from_amount", "float"),
    ("from_currency", "from_currency", "upper"),
    ("from_cash_account", "from_cash_account", "upper"),
    ("to_amount", "to_amount", "float"),
    ("to_currency", "to_currency", "upper"),
    ("to_cash_account", "to_cash_account", "upper"),
    ("rate", "rate", "float"),
    ("source_ref", "source_ref", "str"),
)


def _norm_for_parity(value: Any, kind: str) -> Any:
    if value in (None, ""):
        return None
    if kind == "float":
        parsed = parse_number(value)
        return None if parsed is None else round(parsed, 10)
    if kind == "upper":
        return str(value).upper()
    if kind == "ticker":
        return _normalize_ticker(str(value))
    return str(value)


def _event_from_db_row(
    row: Dict[str, Any],
    *,
    id_map: Dict[int, str],
) -> Dict[str, Any]:
    legacy_id = int(row["id"])
    legacy_target = _int_or_none(row.get("target_id"))
    event: Dict[str, Any] = {
        "schema": LEDGER_SCHEMA,
        "id": id_map[legacy_id],
        "date": row["date"],
        "type": row["type"],
        "legacy_db_id": legacy_id,
        "source": row.get("source") or ("transactions" + ".db"),
        "created_at": row.get("created_at") or now_utc(),
    }
    if row.get("ticker"):
        event["ticker"] = _normalize_ticker(str(row["ticker"]))
    for key in (
        "qty",
        "price",
        "gross",
        "fees",
        "net",
        "amount",
        "from_amount",
        "to_amount",
        "rate",
    ):
        if row.get(key) is not None:
            event[key] = float(row[key])
    for key in (
        "currency",
        "cash_account",
        "bucket",
        "market",
        "rationale",
        "from_currency",
        "from_cash_account",
        "to_currency",
        "to_cash_account",
        "source_ref",
    ):
        if row.get(key) not in (None, ""):
            value = str(row[key])
            event[key] = value.upper() if key.endswith("currency") else value
    if row.get("tags"):
        event["tags"] = row["tags"]
    if legacy_target is not None:
        event["legacy_target_id"] = legacy_target
        if legacy_target in id_map:
            event["target_event_id"] = id_map[legacy_target]
    if row.get("lots"):
        event["lots"] = [
            {
                "acq_date": str(lot["acq_date"]),
                "cost": float(lot["cost"]),
                "qty": float(lot["qty"]),
            }
            for lot in row["lots"]
        ]
    return event


def _db_rows_to_events(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    id_map: Dict[int, str] = {}
    for idx, row in enumerate(rows):
        id_map[int(row["id"])] = event_id_for(
            str(row["date"]),
            str(row["type"]),
            str(row["ticker"]) if row.get("ticker") else None,
            idx + 1,
        )
    return [
        _event_from_db_row(row, id_map=id_map)
        for row in rows
    ]


def _event_dict_to_transaction(event: Dict[str, Any], *, seq: int) -> Transaction:
    data = {k: v for k, v in event.items() if not str(k).startswith("_")}
    data.setdefault("event_id", data.get("id"))
    t = _dict_to_transaction(data, seq=seq)
    t.event_id = str(data.get("id") or data.get("event_id") or "").strip() or None
    t.target_event_id = str(data.get("target_event_id") or "").strip() or None
    t.legacy_db_id = _int_or_none(data.get("legacy_db_id"))
    t.legacy_target_id = _int_or_none(data.get("legacy_target_id"))
    return t


def load_transactions_markdown(ledger_dir: Path) -> List[Transaction]:
    """Load account-local Markdown event files in deterministic replay order."""
    events = load_event_dicts(ledger_dir)
    errors = validate_event_set(events)
    if errors:
        raise ValueError("invalid Markdown ledger:\n" + "\n".join(f"- {e}" for e in errors))
    out = [_event_dict_to_transaction(event, seq=i) for i, event in enumerate(events)]
    event_ids = {t.event_id for t in out if t.event_id}
    unresolved = [
        f"{t.event_id}: target_event_id {t.target_event_id}"
        for t in out
        if t.target_event_id and t.target_event_id not in event_ids
    ]
    if unresolved:
        raise ValueError("unknown Markdown target references:\n" + "\n".join(unresolved))
    return out


def _open_lots_cache(state: ReplayState) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for ticker, lots in sorted(state.open_lots.items()):
        for lot in sorted(lots, key=lambda l: (l.bucket, l.ticker, l.acq_date, l.cost)):
            rows.append({
                "ticker": ticker,
                "qty": lot.qty,
                "cost": lot.cost,
                "acq_date": lot.acq_date,
                "bucket": lot.bucket,
                "market": lot.market,
                "currency": lot.currency,
                "is_share": lot.market not in {"CRYPTO", "FX", "CASH"},
            })
    return rows


def _cash_balances_cache(state: ReplayState) -> List[Dict[str, Any]]:
    return [
        {"currency": currency, "amount": amount}
        for currency, amount in sorted(state.cash.items())
        if abs(amount) > 1e-9
    ]


def _transaction_index_cache(txns: Sequence[Transaction]) -> Dict[str, Any]:
    by_type: Dict[str, int] = {}
    target_refs: List[Dict[str, Any]] = []
    tickers = set()
    for t in txns:
        by_type[t.type] = by_type.get(t.type, 0) + 1
        if t.ticker:
            tickers.add(t.ticker)
        if t.target_event_id or t.target_id or t.legacy_target_id:
            target_refs.append({
                "id": t.event_id,
                "target_event_id": t.target_event_id,
                "target_id": t.target_id,
                "legacy_target_id": t.legacy_target_id,
            })
    dates = [t.date for t in txns]
    return {
        "count": len(txns),
        "by_type": dict(sorted(by_type.items())),
        "tickers": sorted(tickers),
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
        "ids": [t.event_id for t in txns if t.event_id],
        "target_refs": target_refs,
    }


def _fetch_universe_cache(txns: Sequence[Transaction], state: ReplayState) -> List[Dict[str, Any]]:
    held = set(state.open_lots.keys())
    latest_meta: Dict[str, Dict[str, Any]] = {}
    for t in sorted(txns, key=_txn_sort_key):
        if t.type not in {"BUY", "SELL"} or not t.ticker:
            continue
        latest_meta[t.ticker] = {
            "ticker": t.ticker,
            "market": t.market or "US",
            "currency": t.currency or "USD",
            "bucket": t.bucket or "Mid Term (1y+)",
            "last_date": t.date,
            "held": t.ticker in held,
        }
    for ticker in held:
        latest_meta.setdefault(ticker, {
            "ticker": ticker,
            "market": "US",
            "currency": "USD",
            "bucket": "Mid Term (1y+)",
            "last_date": None,
            "held": True,
        })
        latest_meta[ticker]["held"] = True
    return [latest_meta[ticker] for ticker in sorted(latest_meta)]


def build_markdown_cache_payloads(ledger_dir: Path, *, generated_at: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    txns = load_transactions_markdown(ledger_dir)
    state = replay(txns)
    if state.issues:
        raise ValueError("cannot build Markdown generated caches with replay issues:\n" + "\n".join(state.issues))
    return {
        "transaction_index.json": generated_payload(
            "transaction_index",
            ledger_dir,
            _transaction_index_cache(txns),
            generated_at=generated_at,
        ),
        "open_lots.json": generated_payload(
            "open_lots",
            ledger_dir,
            _open_lots_cache(state),
            generated_at=generated_at,
        ),
        "cash_balances.json": generated_payload(
            "cash_balances",
            ledger_dir,
            _cash_balances_cache(state),
            generated_at=generated_at,
        ),
        "fetch_universe.json": generated_payload(
            "fetch_universe",
            ledger_dir,
            _fetch_universe_cache(txns, state),
            generated_at=generated_at,
        ),
    }


def ledger_rebuild_cache(ledger_dir: Path) -> Dict[str, Any]:
    ensure_ledger_skeleton(ledger_dir)
    generated_at = now_utc()
    payloads = build_markdown_cache_payloads(ledger_dir, generated_at=generated_at)
    for name, payload in payloads.items():
        write_json(generated_dir(ledger_dir) / name, payload)
    return {
        "ledger": str(ledger_dir),
        "generated": sorted(payloads),
        "source_tree_hash": hash_tree(events_dir(ledger_dir)),
    }


def _normalize_cache_payload(payload: Dict[str, Any]) -> Any:
    return payload.get("data")


def ledger_verify_cache(ledger_dir: Path) -> Tuple[bool, List[str]]:
    expected = build_markdown_cache_payloads(ledger_dir, generated_at="NORMALIZED")
    issues: List[str] = []
    for name, payload in expected.items():
        path = generated_dir(ledger_dir) / name
        if not path.exists():
            issues.append(f"{name}: missing")
            continue
        try:
            actual = read_json(path)
        except Exception as exc:
            issues.append(f"{name}: cannot parse JSON ({exc})")
            continue
        meta = actual.get("_meta") if isinstance(actual, dict) else None
        expected_meta = payload.get("_meta") if isinstance(payload, dict) else {}
        if not isinstance(meta, dict):
            issues.append(f"{name}: missing generated metadata")
        else:
            for key in ("schema", "name", "source_tree_hash", "notice"):
                if meta.get(key) != expected_meta.get(key):
                    issues.append(f"{name}: metadata {key} mismatch; rebuild cache")
            if not isinstance(meta.get("generated_at"), str) or not meta.get("generated_at"):
                issues.append(f"{name}: missing generated_at metadata")
        if _normalize_cache_payload(actual) != _normalize_cache_payload(payload):
            issues.append(f"{name}: data mismatch; rebuild cache")
    return not issues, issues


def _state_summary(state: ReplayState) -> Dict[str, Any]:
    lots: Dict[str, float] = {
        ticker: round(sum(l.qty for l in lots), 10)
        for ticker, lots in state.open_lots.items()
    }
    cash = {currency: round(amount, 10) for currency, amount in state.cash.items() if abs(amount) > 1e-9}
    realized = round(sum(ev.realized_native for ev in state.realized_events), 10)
    return {
        "open_qty": dict(sorted(lots.items())),
        "cash": dict(sorted(cash.items())),
        "realized_native_total": realized,
        "issues": list(state.issues),
    }


def _compare_summaries(db_summary: Dict[str, Any], md_summary: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for ticker in sorted(set(db_summary["open_qty"]) | set(md_summary["open_qty"])):
        if abs(db_summary["open_qty"].get(ticker, 0.0) - md_summary["open_qty"].get(ticker, 0.0)) > 1e-6:
            issues.append(
                f"open qty {ticker}: db={db_summary['open_qty'].get(ticker, 0.0):g} "
                f"md={md_summary['open_qty'].get(ticker, 0.0):g}"
            )
    for currency in sorted(set(db_summary["cash"]) | set(md_summary["cash"])):
        if abs(db_summary["cash"].get(currency, 0.0) - md_summary["cash"].get(currency, 0.0)) > 1e-2:
            issues.append(
                f"cash {currency}: db={db_summary['cash'].get(currency, 0.0):g} "
                f"md={md_summary['cash'].get(currency, 0.0):g}"
            )
    if abs(db_summary["realized_native_total"] - md_summary["realized_native_total"]) > 1e-2:
        issues.append(
            "realized_native_total: "
            f"db={db_summary['realized_native_total']:g} md={md_summary['realized_native_total']:g}"
        )
    for issue in db_summary.get("issues") or []:
        issues.append(f"db replay issue: {issue}")
    for issue in md_summary.get("issues") or []:
        issues.append(f"markdown replay issue: {issue}")
    return issues


def _compare_db_rows_to_events(db_path: Path, events: Sequence[Dict[str, Any]]) -> List[str]:
    rows = _dump_legacy_rows(db_path)
    issues: List[str] = []
    by_legacy: Dict[int, Dict[str, Any]] = {}
    for event in events:
        legacy = _int_or_none(event.get("legacy_db_id"))
        if legacy is not None:
            by_legacy[legacy] = event
    for row in rows:
        row_id = int(row["id"])
        event = by_legacy.get(row_id)
        if event is None:
            issues.append(f"field parity: DB row {row_id} missing Markdown event")
            continue
        for db_key, event_key, kind in _DB_EVENT_FIELD_MAP:
            db_val = _norm_for_parity(row.get(db_key), kind)
            event_val = _norm_for_parity(event.get(event_key), kind)
            if db_val != event_val:
                issues.append(
                    f"field parity row {row_id} {db_key}: db={db_val!r} md={event_val!r}"
                )
        db_target = _int_or_none(row.get("target_id"))
        md_legacy_target = _int_or_none(event.get("legacy_target_id"))
        if db_target != md_legacy_target:
            issues.append(
                f"field parity row {row_id} target_id: db={db_target!r} md_legacy={md_legacy_target!r}"
            )
        db_lots = [
            (
                str(lot.get("acq_date")),
                round(float(lot.get("cost")), 10),
                round(float(lot.get("qty")), 10),
            )
            for lot in (row.get("lots") or [])
        ]
        md_lots = [
            (
                str(lot.get("acq_date")),
                round(float(lot.get("cost")), 10),
                round(float(lot.get("qty")), 10),
            )
            for lot in (event.get("lots") or [])
        ]
        if db_lots != md_lots:
            issues.append(f"lot parity row {row_id}: db={db_lots!r} md={md_lots!r}")
    return issues


def ledger_verify_parity(db_path: Path, ledger_dir: Path) -> Tuple[bool, Dict[str, Any]]:
    legacy_rows = _dump_legacy_rows(db_path)
    db_txns: List[Transaction] = []
    for i, event in enumerate(_db_rows_to_events(legacy_rows)):
        txn = _event_dict_to_transaction(event, seq=i)
        txn.db_id = txn.legacy_db_id
        txn.target_id = txn.legacy_target_id
        db_txns.append(txn)
    md_txns = load_transactions_markdown(ledger_dir)
    md_events = load_event_dicts(ledger_dir)
    db_state = replay(db_txns)
    md_state = replay(md_txns)
    issues = []
    if len(db_txns) != len(md_txns):
        issues.append(f"transaction count: db={len(db_txns)} md={len(md_txns)}")
    md_legacy_ids = {t.legacy_db_id for t in md_txns if t.legacy_db_id is not None}
    db_ids = {t.db_id for t in db_txns if t.db_id is not None}
    if db_ids != md_legacy_ids:
        issues.append("legacy_db_id mapping does not match DB ids")
    issues.extend(_compare_db_rows_to_events(db_path, md_events))
    issues.extend(_compare_summaries(_state_summary(db_state), _state_summary(md_state)))
    cache_ok, cache_issues = ledger_verify_cache(ledger_dir)
    if not cache_ok:
        issues.extend(f"cache: {issue}" for issue in cache_issues)
    report = {
        "ok": not issues,
        "state": CUTOVER_PROPOSAL_READY if not issues else DUAL_READ_PARITY,
        "db_transaction_count": len(db_txns),
        "markdown_event_count": len(md_txns),
        "source_tree_hash": hash_tree(events_dir(ledger_dir)),
        "issues": issues,
        "db_summary": _state_summary(db_state),
        "markdown_summary": _state_summary(md_state),
    }
    return not issues, report


def ledger_export_db(db_path: Path, ledger_dir: Path, *, write: bool) -> Dict[str, Any]:
    rows = _dump_legacy_rows(db_path)
    events = _db_rows_to_events(rows)
    planned_paths = [event_path_for(ledger_dir, event) for event in events]
    result = {
        "source_db": str(db_path),
        "ledger": str(ledger_dir),
        "write": write,
        "event_count": len(events),
        "planned_event_files": [str(path) for path in planned_paths],
        "state": DB_CANONICAL if not write else DUAL_READ_PARITY,
    }
    if not write:
        return result

    ensure_ledger_skeleton(ledger_dir)
    for event, path in zip(events, planned_paths):
        write_event_file(event, path)

    cache_result = ledger_rebuild_cache(ledger_dir)
    ok, parity_report = ledger_verify_parity(db_path, ledger_dir)
    stamp = now_utc().replace("-", "").replace(":", "")
    bundle = migrations_dir(ledger_dir) / f"{stamp}-db-to-md"
    bundle.mkdir(parents=True, exist_ok=True)
    id_map = {
        str(row["id"]): {
            "event_id": event["id"],
            "target_event_id": event.get("target_event_id"),
            "legacy_target_id": event.get("legacy_target_id"),
        }
        for row, event in zip(rows, events)
    }
    write_json(bundle / "db-id-map.json", id_map)
    write_json(bundle / "parity-report.json", parity_report)
    if db_path.exists():
        (bundle / "source-db.sha256").write_text(sha256_file(db_path) + "\n", encoding="utf-8")
    manifest = [
        "# Legacy SQLite to Markdown ledger migration manifest",
        "",
        f"- source_db: {db_path}",
        f"- ledger: {ledger_dir}",
        f"- exported_events: {len(events)}",
        f"- parity_ok: {str(ok).lower()}",
        f"- transition_state: {parity_report['state']}",
        "",
        "The source legacy SQLite evidence was not modified. Passing parity prepares a migration proposal only; archive/retirement has a separate gate.",
    ]
    (bundle / "manifest.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    result.update({
        "migration_bundle": str(bundle),
        "cache": cache_result,
        "parity": parity_report,
        "state": parity_report["state"],
    })
    return result


LEDGER_STATE_FILE = "LEDGER_STATE.json"
LEDGER_STATE_SCHEMA = "investment-ledger-state/v1"
MIGRATION_SCHEMA = "investment-ledger-migration/v1"
MIGRATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _dump_legacy_rows(db_path: Path) -> List[Dict[str, Any]]:
    """Read legacy SQLite rows through the quarantined read-only importer."""
    from legacy_sqlite_import import dump_legacy_transactions  # type: ignore[import-not-found]  # noqa: WPS433

    return dump_legacy_transactions(db_path)


def _migration_id() -> str:
    return now_utc().replace("-", "").replace(":", "").replace("T", "T").replace("Z", "Z")


def _sanitize_migration_id(value: Any) -> str:
    """Return a path-segment-safe migration id or fail before file writes."""
    if not isinstance(value, str):
        raise ValueError("invalid migration id; expected a string")
    if (
        value in {".", ".."}
        or "/" in value
        or "\\" in value
        or not MIGRATION_ID_RE.fullmatch(value)
    ):
        raise ValueError(
            "invalid migration id; use 1-80 ASCII letters, numbers, dots, underscores, or hyphens, "
            "with no path separators"
        )
    return value


def _migration_id_arg(value: Optional[str]) -> str:
    return _sanitize_migration_id(value or _migration_id())


def _required_migration_id_arg(value: Optional[str]) -> str:
    if not value:
        raise ValueError("rollback requires --migration-id")
    return _sanitize_migration_id(value)


def _ledger_state_path(ledger_dir: Path) -> Path:
    return ledger_dir / LEDGER_STATE_FILE


def _read_ledger_state(ledger_dir: Path) -> Dict[str, Any]:
    path = _ledger_state_path(ledger_dir)
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def _write_ledger_state(ledger_dir: Path, payload: Dict[str, Any]) -> None:
    ensure_ledger_skeleton(ledger_dir)
    write_json(_ledger_state_path(ledger_dir), payload)


def _legacy_db_journal_paths(db_path: Path) -> List[Path]:
    return [Path(str(db_path) + suffix) for suffix in ("-wal", "-shm")]


def _latest_migration_bundle(ledger_dir: Path) -> Optional[Path]:
    root = migrations_dir(ledger_dir)
    if not root.exists():
        return None
    bundles = sorted([path for path in root.iterdir() if path.is_dir()])
    return bundles[-1] if bundles else None


def _copy_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def _snapshot_ledger_state(ledger_dir: Path, backup_root: Path) -> Dict[str, Any]:
    """Copy pre-apply ledger state into a migration backup bundle."""
    backup_root.mkdir(parents=True, exist_ok=False)
    snapshots = {
        "events": events_dir(ledger_dir).exists(),
        "generated": generated_dir(ledger_dir).exists(),
        LEDGER_STATE_FILE: _ledger_state_path(ledger_dir).exists(),
    }
    _copy_if_exists(events_dir(ledger_dir), backup_root / "events")
    _copy_if_exists(generated_dir(ledger_dir), backup_root / "generated")
    _copy_if_exists(_ledger_state_path(ledger_dir), backup_root / LEDGER_STATE_FILE)
    manifest = {
        "schema": MIGRATION_SCHEMA,
        "snapshot_at": now_utc(),
        "ledger": str(ledger_dir),
        "pre_apply_event_tree_hash": hash_tree(events_dir(ledger_dir)),
        "pre_apply_generated_tree_hash": hash_tree(generated_dir(ledger_dir)),
        "snapshots": snapshots,
    }
    write_json(backup_root / "snapshot-manifest.json", manifest)
    return manifest


def _restore_ledger_state_from_backup(ledger_dir: Path, backup_root: Path) -> None:
    manifest_path = backup_root / "snapshot-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"rollback backup manifest not found: {manifest_path}")
    manifest = read_json(manifest_path)
    snapshots = manifest.get("snapshots") or {}
    for label, target in (
        ("events", events_dir(ledger_dir)),
        ("generated", generated_dir(ledger_dir)),
    ):
        source = backup_root / label
        if target.exists():
            shutil.rmtree(target)
        if snapshots.get(label):
            shutil.copytree(source, target)
    state_path = _ledger_state_path(ledger_dir)
    if state_path.exists():
        state_path.unlink()
    if snapshots.get(LEDGER_STATE_FILE):
        shutil.copy2(backup_root / LEDGER_STATE_FILE, state_path)


def _migration_layout_state() -> str:
    return detect_legacy_layout()


def _require_migration_layout_safe() -> str:
    state = _migration_layout_state()
    if state == "partial":
        raise RuntimeError("account layout detector returned partial; reconcile account layout before legacy-to-Markdown migration")
    if state == "migrate":
        raise RuntimeError("legacy root account layout requires account-management migration before legacy-to-Markdown migration")
    return state


def migration_detect(args: argparse.Namespace) -> Dict[str, Any]:
    layout_state = _migration_layout_state()
    if layout_state in {"partial", "migrate"}:
        root_db = DEFAULT_DB_PATH
        return {
            "schema": MIGRATION_SCHEMA,
            "command": "detect",
            "account": None,
            "layout_state": layout_state,
            "db": {
                "path": str(root_db),
                "exists": root_db.exists(),
                "sha256": sha256_file(root_db) if root_db.exists() else None,
            },
            "ledger": None,
            "side_effect": "read-only",
            "blocked": (
                "account layout must be reconciled before legacy-to-Markdown migration"
                if layout_state == "partial"
                else "run the account-management legacy-layout migration gate before legacy-to-Markdown migration"
            ),
        }
    paths = resolve_account(args)
    ledger_path = Path(getattr(args, "ledger", None) or paths.ledger)
    state: Dict[str, Any] = {}
    try:
        state = _read_ledger_state(ledger_path)
    except Exception as exc:  # noqa: BLE001 - report state parse blocker
        state = {"error": str(exc)}
    events: List[Dict[str, Any]] = []
    event_error: Optional[str] = None
    try:
        events = load_event_dicts(ledger_path)
    except Exception as exc:  # noqa: BLE001 - detect is diagnostic
        event_error = str(exc)
    cache_ok = False
    cache_issues: List[str] = []
    try:
        cache_ok, cache_issues = ledger_verify_cache(ledger_path)
    except Exception as exc:  # noqa: BLE001 - detect should not crash on incomplete ledgers
        cache_issues = [str(exc)]
    latest_bundle = _latest_migration_bundle(ledger_path)
    archive_root = ledger_path / "archive" / "legacy-sqlite"
    archived = sorted(path.name for path in archive_root.iterdir()) if archive_root.exists() else []
    return {
        "schema": MIGRATION_SCHEMA,
        "command": "detect",
        "account": paths.name,
        "layout_state": layout_state,
        "db": {
            "path": str(paths.db),
            "exists": paths.db.exists(),
            "sha256": sha256_file(paths.db) if paths.db.exists() else None,
        },
        "ledger": {
            "path": str(ledger_path),
            "exists": ledger_path.exists(),
            "event_count": len(events),
            "event_tree_hash": hash_tree(events_dir(ledger_path)),
            "event_error": event_error,
            "generated_cache_ok": cache_ok,
            "generated_cache_issues": cache_issues,
            "state": state or None,
            "latest_migration_bundle": str(latest_bundle) if latest_bundle else None,
            "archived_legacy_sqlite_migrations": archived,
        },
        "side_effect": "read-only",
        "next_step": "prepare" if paths.db.exists() else "verify",
    }


def migration_prepare(args: argparse.Namespace) -> Dict[str, Any]:
    _require_migration_layout_safe()
    paths = resolve_account(args)
    ledger_path = Path(getattr(args, "ledger", None) or paths.ledger)
    db_path = Path(getattr(args, "db", None) or paths.db)
    if not db_path.exists():
        raise FileNotFoundError(f"legacy source DB not found: {db_path}")
    rows = _dump_legacy_rows(db_path)
    events = _db_rows_to_events(rows)
    event_errors = validate_event_set(events)
    mid = _migration_id_arg(getattr(args, "migration_id", None))
    proposal = {
        "schema": MIGRATION_SCHEMA,
        "command": "prepare",
        "migration_id": mid,
        "account": paths.name,
        "source_db": str(db_path),
        "source_db_sha256": sha256_file(db_path),
        "ledger": str(ledger_path),
        "event_count": len(events),
        "event_tree_hash": hash_tree(events_dir(ledger_path)),
        "planned_event_files": [str(event_path_for(ledger_path, event)) for event in events],
        "legacy_row_mapping": {
            "transactions_rows": len(rows),
            "canonical_events": len(events),
            "one_transaction_row_to_one_event": len(rows) == len(events),
        },
        "archive_target": str(ledger_path / "archive" / "legacy-sqlite" / mid),
        "apply_does_not_move_db": True,
        "archive_db_requires_separate_confirmation": True,
        "blockers": event_errors,
        "side_effect": "read-only" if not getattr(args, "write_proposal", False) else "writes-proposal-only",
    }
    if getattr(args, "write_proposal", False):
        bundle = migrations_dir(ledger_path) / f"{mid}-prepare"
        bundle.mkdir(parents=True, exist_ok=True)
        write_json(bundle / "proposal.json", proposal)
        proposal["proposal_path"] = str(bundle / "proposal.json")
    return proposal


def migration_apply(args: argparse.Namespace) -> Dict[str, Any]:
    if not getattr(args, "yes", False):
        raise PermissionError("migration apply requires the skill/user confirmation gate and --yes")
    _require_migration_layout_safe()
    paths = resolve_account(args)
    ledger_path = Path(getattr(args, "ledger", None) or paths.ledger)
    db_path = Path(getattr(args, "db", None) or paths.db)
    if not db_path.exists():
        raise FileNotFoundError(f"legacy source DB not found: {db_path}")
    mid = _migration_id_arg(getattr(args, "migration_id", None))
    before_hash = hash_tree(events_dir(ledger_path))
    apply_bundle = migrations_dir(ledger_path) / f"{mid}-apply"
    if apply_bundle.exists():
        raise FileExistsError(f"migration apply bundle already exists: {apply_bundle}")
    backup_root = apply_bundle / "backup"
    pre_apply_manifest = _snapshot_ledger_state(ledger_path, backup_root)
    try:
        result = ledger_export_db(db_path, ledger_path, write=True)
    except Exception:
        _restore_ledger_state_from_backup(ledger_path, backup_root)
        raise
    parity = result.get("parity") or {}
    if parity.get("ok") is False:
        _restore_ledger_state_from_backup(ledger_path, backup_root)
        write_json(apply_bundle / "blocked-apply-result.json", {
            "schema": MIGRATION_SCHEMA,
            "migration_id": mid,
            "blocked": "parity failed; restored pre-apply Markdown/generated state",
            "parity": parity,
            "result": result,
        })
        return {
            "schema": MIGRATION_SCHEMA,
            "command": "apply",
            "migration_id": mid,
            "account": paths.name,
            "ledger": str(ledger_path),
            "source_db": str(db_path),
            "source_db_still_exists": db_path.exists(),
            "ledger_state": None,
            "parity": parity,
            "result": result,
            "blocked": "parity failed; restored pre-apply Markdown/generated state and did not promote LEDGER_STATE.json",
        }
    state = {
        "schema": LEDGER_STATE_SCHEMA,
        "state": MARKDOWN_CANONICAL,
        "account": paths.name,
        "migration_id": mid,
        "source_db": str(db_path),
        "source_db_sha256": sha256_file(db_path),
        "source_db_archived": False,
        "applied_at": now_utc(),
        "pre_apply_event_tree_hash": before_hash,
        "event_tree_hash": hash_tree(events_dir(ledger_path)),
        "generated_tree_hash": hash_tree(generated_dir(ledger_path)),
        "migration_bundle": result.get("migration_bundle"),
        "apply_bundle": str(apply_bundle),
        "pre_apply_manifest": pre_apply_manifest,
        "apply_did_not_move_db": db_path.exists(),
        "archive_db_requires_separate_confirmation": True,
    }
    _write_ledger_state(ledger_path, state)
    write_json(apply_bundle / "apply-result.json", {
        "schema": MIGRATION_SCHEMA,
        "migration_id": mid,
        "ledger_state": state,
        "parity": parity,
        "result": result,
    })
    return {
        "schema": MIGRATION_SCHEMA,
        "command": "apply",
        "migration_id": mid,
        "account": paths.name,
        "ledger": str(ledger_path),
        "source_db": str(db_path),
        "source_db_still_exists": db_path.exists(),
        "ledger_state": state,
        "parity": parity,
        "result": result,
    }


def migration_verify(args: argparse.Namespace) -> Dict[str, Any]:
    _require_migration_layout_safe()
    paths = resolve_account(args)
    ledger_path = Path(getattr(args, "ledger", None) or paths.ledger)
    db_path = Path(getattr(args, "db", None) or paths.db)
    issues: List[str] = []
    state: Dict[str, Any] = {}
    try:
        state = _read_ledger_state(ledger_path)
    except Exception as exc:  # noqa: BLE001
        issues.append(f"ledger state: {exc}")
    try:
        events = load_event_dicts(ledger_path)
        event_errors = validate_event_set(events)
        issues.extend(f"events: {err}" for err in event_errors)
    except Exception as exc:  # noqa: BLE001
        events = []
        issues.append(f"events: {exc}")
    markdown_runtime: Dict[str, Any] = {"ok": False}
    try:
        md_txns = load_transactions_markdown(ledger_path)
        md_state = replay(md_txns)
        markdown_runtime = {
            "ok": not md_state.issues,
            "transaction_count": len(md_txns),
            "replay_issues": md_state.issues,
            "summary": _state_summary(md_state),
        }
        issues.extend(f"markdown-runtime: {issue}" for issue in md_state.issues)
    except Exception as exc:  # noqa: BLE001
        markdown_runtime = {"ok": False, "error": str(exc)}
        issues.append(f"markdown-runtime: {exc}")
    try:
        cache_ok, cache_issues = ledger_verify_cache(ledger_path)
    except Exception as exc:  # noqa: BLE001
        cache_ok = False
        cache_issues = [str(exc)]
    issues.extend(f"cache: {issue}" for issue in cache_issues)

    parity_report: Optional[Dict[str, Any]] = None
    if db_path.exists():
        try:
            parity_ok, parity_report = ledger_verify_parity(db_path, ledger_path)
            if not parity_ok:
                issues.extend(f"parity: {issue}" for issue in parity_report.get("issues", []))
            expected = state.get("source_db_sha256") if isinstance(state, dict) else None
            if expected and sha256_file(db_path) != expected:
                issues.append("source DB checksum differs from applied ledger state")
        except Exception as exc:  # noqa: BLE001
            issues.append(f"parity: {exc}")
    elif state.get("source_db_archived") is not True:
        issues.append("source DB missing but ledger state does not mark it archived")

    no_sqlite_mode = getattr(args, "no_sqlite_mode", "transition")
    no_sqlite_result: Dict[str, Any]
    try:
        ns_args = argparse.Namespace(root=Path.cwd(), mode=no_sqlite_mode)
        no_sqlite_result = migration_verify_no_sqlite(ns_args)
        if not no_sqlite_result.get("ok"):
            issues.append(
                f"no-sqlite-{no_sqlite_mode}: {no_sqlite_result.get('violation_count', 'unknown')} violation(s)"
            )
    except Exception as exc:  # noqa: BLE001
        no_sqlite_result = {"ok": False, "mode": no_sqlite_mode, "error": str(exc)}
        issues.append(f"no-sqlite-{no_sqlite_mode}: {exc}")

    default_runtime: Dict[str, Any]
    try:
        selected_store = select_ledger_store(db_path, ledger_path, "auto")
        default_txns = load_transactions(db=db_path, ledger=ledger_path, store="auto")
        default_fetch_lots = load_fetch_universe_lots(db_path)
        default_runtime = {
            "ok": True,
            "selected_store": selected_store,
            "transaction_count": len(default_txns),
            "fetch_universe_count": len(default_fetch_lots),
            "db_exists": db_path.exists(),
        }
        if state.get("state") == MARKDOWN_CANONICAL and selected_store != "markdown":
            default_runtime["ok"] = False
            issues.append("default-runtime: Markdown canonical ledger did not select Markdown store")
        if state.get("source_db_archived") is True and db_path.exists():
            default_runtime["ok"] = False
            issues.append("default-runtime: source DB still exists after archive state")
        if len(events) != len(default_txns) and selected_store == "markdown":
            default_runtime["ok"] = False
            issues.append(
                f"default-runtime: transaction count mismatch events={len(events)} default={len(default_txns)}"
            )
        if state.get("state") == MARKDOWN_CANONICAL:
            try:
                from report_archive import read_archive  # type: ignore[import-not-found]  # noqa: WPS433
                before_exists = db_path.exists()
                archive_index_path = generated_dir(ledger_path) / "report_archive_index.json"
                before_index_hash = sha256_file(archive_index_path) if archive_index_path.exists() else None
                read_archive("__migration_verify_readonly_probe__", db_path=db_path)
                after_exists = db_path.exists()
                after_index_hash = sha256_file(archive_index_path) if archive_index_path.exists() else None
                default_runtime["report_archive_auto_read_did_not_create_db"] = (before_exists == after_exists)
                default_runtime["report_archive_auto_read_did_not_rebuild_index"] = (
                    before_index_hash == after_index_hash
                )
                if not before_exists and after_exists:
                    default_runtime["ok"] = False
                    issues.append("default-runtime: report_archive auto recreated legacy store")
                if before_index_hash != after_index_hash:
                    default_runtime["ok"] = False
                    issues.append("default-runtime: report_archive auto read rebuilt generated index")
            except Exception as exc:  # noqa: BLE001
                default_runtime["ok"] = False
                issues.append(f"default-runtime report_archive: {exc}")
    except Exception as exc:  # noqa: BLE001
        default_runtime = {"ok": False, "error": str(exc)}
        issues.append(f"default-runtime: {exc}")

    return {
        "schema": MIGRATION_SCHEMA,
        "command": "verify",
        "ok": not issues,
        "account": paths.name,
        "ledger": str(ledger_path),
        "event_count": len(events),
        "event_tree_hash": hash_tree(events_dir(ledger_path)),
        "markdown_runtime": markdown_runtime,
        "default_runtime": default_runtime,
        "generated_cache_ok": cache_ok,
        "ledger_state": state or None,
        "source_db": str(db_path),
        "source_db_exists": db_path.exists(),
        "parity": parity_report,
        "no_sqlite": no_sqlite_result,
        "issues": issues,
    }


def migration_archive_db(args: argparse.Namespace) -> Dict[str, Any]:
    if not getattr(args, "yes", False):
        raise PermissionError("archive-db moves protected legacy store evidence and requires a separate --yes gate")
    _require_migration_layout_safe()
    paths = resolve_account(args)
    ledger_path = Path(getattr(args, "ledger", None) or paths.ledger)
    db_path = Path(getattr(args, "db", None) or paths.db)
    state = _read_ledger_state(ledger_path)
    if state.get("schema") != LEDGER_STATE_SCHEMA or state.get("state") != MARKDOWN_CANONICAL:
        raise RuntimeError("refusing to archive DB before migration apply writes a Markdown canonical ledger state")
    if state.get("source_db_archived") is True:
        raise RuntimeError("source DB is already marked archived in LEDGER_STATE.json")
    expected_hash = state.get("source_db_sha256")
    if not expected_hash:
        raise RuntimeError("LEDGER_STATE.json is missing source_db_sha256; cannot archive safely")
    if not db_path.exists():
        raise FileNotFoundError(f"source DB not found: {db_path}")
    actual_hash = sha256_file(db_path)
    if actual_hash != expected_hash:
        raise RuntimeError("refusing to archive DB because source checksum differs from LEDGER_STATE.json")
    requested_mid = getattr(args, "migration_id", None)
    if requested_mid:
        requested_mid = _sanitize_migration_id(str(requested_mid))
    if requested_mid and requested_mid != state.get("migration_id"):
        raise RuntimeError("requested --migration-id does not match LEDGER_STATE.json")
    verify = migration_verify(args)
    if not verify.get("ok"):
        raise RuntimeError("refusing to archive DB before migration verify passes: " + "; ".join(verify.get("issues", [])))
    mid = _migration_id_arg(requested_mid or state.get("migration_id"))
    archive_dir = ledger_path / "archive" / "legacy-sqlite" / str(mid)
    archive_dir.mkdir(parents=True, exist_ok=False)
    source_hash = actual_hash
    moved: List[Dict[str, str]] = []
    target = archive_dir / db_path.name
    shutil.move(str(db_path), str(target))
    moved.append({"from": str(db_path), "to": str(target), "sha256": source_hash})
    for journal in _legacy_db_journal_paths(db_path):
        if journal.exists():
            jt = archive_dir / journal.name
            shutil.move(str(journal), str(jt))
            moved.append({"from": str(journal), "to": str(jt), "sha256": sha256_file(jt)})
    (archive_dir / (("transactions" + ".db") + ".sha256")).write_text(source_hash + "\n", encoding="utf-8")
    manifest = {
        "schema": MIGRATION_SCHEMA,
        "command": "archive-db",
        "migration_id": mid,
        "account": paths.name,
        "archived_at": now_utc(),
        "ledger": str(ledger_path),
        "moved": moved,
        "restore_is_recovery_only": True,
        "normal_runtime_store": "markdown",
    }
    write_json(archive_dir / "manifest.json", manifest)
    (archive_dir / "restore-instructions.md").write_text(
        "# Legacy SQLite archive restore instructions\n\n"
        "This archive is recovery evidence / legacy import input only. Restoring it must not "
        "re-enable legacy-store normal runtime. Use migration rollback or a new migration prepare/apply "
        "attempt if this evidence is needed.\n",
        encoding="utf-8",
    )
    state.update({
        "source_db_archived": True,
        "source_db_archive": str(archive_dir),
        "source_db_sha256": source_hash,
        "archived_at": manifest["archived_at"],
    })
    _write_ledger_state(ledger_path, state)
    return manifest


def migration_rollback(args: argparse.Namespace) -> Dict[str, Any]:
    if not getattr(args, "yes", False):
        raise PermissionError("migration rollback changes ledger/archive state and requires --yes")
    _require_migration_layout_safe()
    paths = resolve_account(args)
    ledger_path = Path(getattr(args, "ledger", None) or paths.ledger)
    mid = _required_migration_id_arg(getattr(args, "migration_id", None))
    state = _read_ledger_state(ledger_path)
    apply_bundle = migrations_dir(ledger_path) / f"{mid}-apply"
    backup_root = apply_bundle / "backup"
    if not backup_root.exists():
        raise FileNotFoundError(f"rollback backup not found for migration {mid}: {backup_root}")
    rollback_dir = migrations_dir(ledger_path) / f"{mid}-rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    _restore_ledger_state_from_backup(ledger_path, backup_root)
    archive_dir = ledger_path / "archive" / "legacy-sqlite" / str(mid)
    restored_db: Optional[str] = None
    if getattr(args, "restore_db_evidence", False):
        archived_db = archive_dir / ("transactions" + ".db")
        if not archived_db.exists():
            raise FileNotFoundError(f"archived DB evidence not found: {archived_db}")
        target = rollback_dir / "legacy-import-input" / ("transactions" + ".db")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archived_db, target)
        restored_db = str(target)
    note = {
        "schema": MIGRATION_SCHEMA,
        "command": "rollback",
        "migration_id": mid,
        "account": paths.name,
        "rolled_back_at": now_utc(),
        "restored_db_evidence": restored_db,
        "normal_runtime_store": "markdown",
        "pre_rollback_state": state or None,
        "note": "Rollback restored pre-apply Markdown/generated files. DB evidence, when requested, is copied under the rollback bundle only and does not re-enable legacy-store normal runtime.",
    }
    write_json(rollback_dir / "rollback-note.json", note)
    return note


def migration_verify_no_sqlite(args: argparse.Namespace) -> Dict[str, Any]:
    try:
        from validate_no_sqlite import run_validation  # type: ignore[import-not-found]  # noqa: WPS433
    except ImportError as exc:
        raise RuntimeError(f"cannot import validate_no_sqlite.py: {exc}") from exc
    root = Path(getattr(args, "root", None) or Path.cwd())
    mode = getattr(args, "mode", "final")
    return run_validation(root=root, mode=mode)


class LedgerStore:
    """Backend-neutral store boundary for staged migration."""

    state: str = DB_CANONICAL

    def load_transactions(self) -> List[Transaction]:
        raise NotImplementedError

    def rebuild_caches(self) -> Dict[str, Any]:
        raise NotImplementedError

    def verify(self) -> Tuple[bool, Dict[str, Any]]:
        raise NotImplementedError


class SQLiteLedgerStore(LedgerStore):
    state = DB_CANONICAL

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def load_transactions(self) -> List[Transaction]:
        return load_transactions_db(self.db_path)

    def rebuild_caches(self) -> Dict[str, Any]:
        return db_rebuild_balances(self.db_path)

    def verify(self) -> Tuple[bool, Dict[str, Any]]:
        args = argparse.Namespace(db=self.db_path)
        ok, issues = _verify_balance_tables(args)
        return ok, {"ok": ok, "issues": issues, "state": self.state}


class MarkdownLedgerStore(LedgerStore):
    def __init__(self, ledger_dir: Path, *, state: str = DUAL_READ_PARITY) -> None:
        if state not in STORE_STATES:
            raise ValueError(f"unknown ledger state: {state}")
        self.ledger_dir = ledger_dir
        self.state = state

    def load_transactions(self) -> List[Transaction]:
        return load_transactions_markdown(self.ledger_dir)

    def rebuild_caches(self) -> Dict[str, Any]:
        return ledger_rebuild_cache(self.ledger_dir)

    def verify(self) -> Tuple[bool, Dict[str, Any]]:
        ok, issues = ledger_verify_cache(self.ledger_dir)
        return ok, {"ok": ok, "issues": issues, "state": self.state}

    def assert_live_write_allowed(self) -> None:
        if self.state != MARKDOWN_CANONICAL:
            raise RuntimeError(
                "live Markdown writes require a separately confirmed cutover; "
                f"current state is {self.state}"
            )


def ledger_state_is_markdown_canonical(ledger_dir: Path) -> bool:
    try:
        state = _read_ledger_state(ledger_dir)
    except Exception:
        return False
    return state.get("schema") == LEDGER_STATE_SCHEMA and state.get("state") == MARKDOWN_CANONICAL


def select_ledger_store(db_path: Optional[Path], ledger_dir: Optional[Path], requested: str = "auto") -> str:
    """Resolve every normal runtime read to the Markdown ledger."""
    _ = (db_path, ledger_dir)
    if requested not in {"auto", "markdown", "db"}:
        raise ValueError(f"unknown ledger store: {requested}")
    return "markdown"



def load_holdings_lots(db_path: Path) -> List[Lot]:
    """Compatibility entry point: load projected holdings from Markdown replay."""
    ledger_dir = _legacy_ledger_dir_for_path(db_path)
    if not ledger_dir.exists():
        return []
    return load_holdings_lots_markdown(ledger_dir)

def _lot_to_fetch_lot(lot: OpenLot) -> Lot:
    try:
        market_enum = MarketType(lot.market) if lot.market else MarketType.UNKNOWN
    except ValueError:
        market_enum = MarketType.UNKNOWN
    is_share = market_enum not in (MarketType.CRYPTO, MarketType.FX, MarketType.CASH)
    ccy_prefix = {
        "USD": "$", "TWD": "NT$", "JPY": "¥",
        "EUR": "€", "GBP": "£", "HKD": "HK$",
    }.get(lot.currency, "")
    unit = "shares " if is_share else ""
    raw_line = (
        f"- {lot.ticker}: {lot.qty:g} {unit}@ {ccy_prefix}{lot.cost:g} on {lot.acq_date} [{lot.market}]"
        if is_share else
        f"- {lot.ticker} {lot.qty:g} @ {ccy_prefix}{lot.cost:g} on {lot.acq_date} [{lot.market}]"
    )
    return Lot(
        raw_line=raw_line,
        bucket=lot.bucket,
        ticker=lot.ticker,
        quantity=lot.qty,
        cost=lot.cost,
        date=lot.acq_date,
        market=market_enum,
        is_share=is_share,
    )


def load_holdings_lots_markdown(ledger_dir: Path) -> List[Lot]:
    """Return projected open lots + cash from Markdown replay."""
    txns = load_transactions_markdown(ledger_dir)
    state = replay(txns)
    out: List[Lot] = []
    for ticker in sorted(state.open_lots):
        for lot in sorted(state.open_lots[ticker], key=lambda l: (l.bucket, l.ticker, l.acq_date, l.cost)):
            out.append(_lot_to_fetch_lot(lot))
    for currency, amount in sorted(state.cash.items()):
        if abs(amount) <= 1e-9:
            continue
        out.append(Lot(
            raw_line=f"- {currency}: {amount:g} [cash]",
            bucket="Cash Holdings",
            ticker=currency,
            quantity=amount,
            cost=None,
            date=None,
            market=MarketType.CASH,
            is_share=False,
        ))
    return out



def load_fetch_universe_lots(db_path: Path) -> List[Lot]:
    """Compatibility entry point: load the price-fetch universe from Markdown replay."""
    ledger_dir = _legacy_ledger_dir_for_path(db_path)
    if not ledger_dir.exists():
        return []
    return load_fetch_universe_lots_markdown(ledger_dir)

def load_fetch_universe_lots_markdown(ledger_dir: Path) -> List[Lot]:
    """Markdown equivalent of ``load_fetch_universe_lots`` for dual-run tests."""
    current = load_holdings_lots_markdown(ledger_dir)
    held: set[str] = {l.ticker for l in current if l.market != MarketType.CASH}
    txns = load_transactions_markdown(ledger_dir)
    reversed_event_ids: set[str] = set()
    reversed_db_ids: set[int] = set()
    reversed_legacy_db_ids: set[int] = set()
    for t in txns:
        if t.type != "REVERSAL":
            continue
        if t.target_event_id:
            reversed_event_ids.add(t.target_event_id)
        if t.target_id is not None:
            reversed_db_ids.add(t.target_id)
        if t.legacy_target_id is not None:
            reversed_legacy_db_ids.add(t.legacy_target_id)
    by_ticker: Dict[str, Dict[str, str]] = {}
    for t in sorted(txns, key=_txn_sort_key):
        if t.type not in {"BUY", "SELL"} or not t.ticker:
            continue
        if (
            (t.event_id and t.event_id in reversed_event_ids)
            or (t.db_id is not None and t.db_id in reversed_db_ids)
            or (t.legacy_db_id is not None and t.legacy_db_id in reversed_legacy_db_ids)
        ):
            continue
        if t.ticker in held:
            continue
        by_ticker[t.ticker] = {
            "market": t.market or "US",
            "currency": t.currency or "USD",
            "bucket": t.bucket or "Mid Term (1y+)",
            "last_date": t.date,
        }
    stubs: List[Lot] = []
    for ticker, meta in sorted(by_ticker.items()):
        try:
            market_enum = MarketType(meta["market"]) if meta["market"] else MarketType.UNKNOWN
        except ValueError:
            market_enum = MarketType.UNKNOWN
        is_share = market_enum not in (MarketType.CRYPTO, MarketType.FX, MarketType.CASH)
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
    ledger: Optional[Path] = None,
    store: str = "auto",
) -> List[Transaction]:
    """Load transactions through the staged store adapters."""
    selected = select_ledger_store(db, ledger, store)
    if selected == "markdown":
        if ledger and ledger.exists():
            return load_transactions_markdown(ledger)
        return []
    if selected == "db" and db and db.exists():
        return load_transactions_db(db)
    if md and md.exists():
        return parse_transactions(md)
    return []


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _add_source_args_no_account(sp: argparse.ArgumentParser) -> None:
    """Add --db and --settings only.  Used by the snapshot subparser, which
    needs to attach `add_account_args(..., support_all_accounts=True)`
    explicitly so the mutex group does NOT bleed onto the four other
    consumers of `_add_source_args` (pnl / profit-panel / analytics /
    replay)."""
    sp.add_argument("--db", default=None, type=Path,
                    help="Legacy path override; normal runtime uses the account Markdown ledger")
    sp.add_argument("--ledger", default=None, type=Path,
                    help="Markdown ledger directory for dual-read/parity runs")
    sp.add_argument("--ledger-store", choices=("auto", "markdown"), default="auto",
                    help="Read source; final runtime uses Markdown")


def _add_source_args(sp: argparse.ArgumentParser) -> None:
    """Common --db and --account flags. Default for --db is None (sentinel)
    so resolve_account() can detect "not explicitly set" and fall back to
    the active account Markdown ledger."""
    _add_source_args_no_account(sp)
    add_account_args(sp)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    # ---- verify (Markdown replay vs generated projections) ------------------- #
    v = sub.add_parser("verify", help="Replay Markdown ledger and reconcile against generated projections")
    v.add_argument("--db", default=None, type=Path)
    add_account_args(v)

    # ---- pnl --------------------------------------------------------------- #
    pn = sub.add_parser("pnl", help="Print realized + unrealized snapshot")
    pn.add_argument("--prices", default="prices.json", type=Path)
    pn.add_argument("--settings", default=None, type=Path)
    _add_source_args(pn)

    # ---- profit-panel ------------------------------------------------------ #
    pp = sub.add_parser("profit-panel", help="Compute profit-panel rows")
    pp.add_argument("--prices", default="prices.json", type=Path)
    pp.add_argument("--settings", default=None, type=Path)
    pp.add_argument("--output", default=None, type=Path,
                    help="Write JSON output here (suitable for merging into report_context.json)")
    pp.add_argument("--today", default=None, help="Override today (YYYY-MM-DD); default: local date")
    _add_source_args(pp)

    # ---- analytics --------------------------------------------------------- #
    an = sub.add_parser("analytics", help="Compute transaction-driven report analytics")
    an.add_argument("--prices", default="prices.json", type=Path)
    an.add_argument("--settings", default=None, type=Path)
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
    sn.add_argument("--settings", default=None, type=Path)
    sn.add_argument("--output", default=Path("report_snapshot.json"), type=Path,
                    help="Snapshot path; default: ./report_snapshot.json")
    sn.add_argument("--today", default=None, help="Override today (YYYY-MM-DD); default: local date")
    sn.add_argument("--base-currency", default=None, type=str,
                    help="Override the snapshot base currency.  Required (or "
                         "defaulted to USD) when --all-accounts; ignored otherwise "
                         "(single-account mode reads SETTINGS.md).")
    # MUTEX-1 opt-in: only the snapshot subparser exposes --all-accounts;
    # pnl / profit-panel / analytics / replay keep single-account behavior.
    _add_source_args_no_account(sn)
    add_account_args(sn, support_all_accounts=True)

    # ---- replay ------------------------------------------------------------ #
    rp = sub.add_parser("replay", help="Print replay state at cutoff")
    rp.add_argument("--cutoff", default=None, help="ISO date; default: today")
    _add_source_args(rp)

    sub.add_parser("self-check", help="Run unit tests")

    # ---- db <subcommand> --------------------------------------------------- #
    db = sub.add_parser("db", help="Markdown ledger compatibility aliases: init, import, add, dump, stats")
    db_sub = db.add_subparsers(dest="db_cmd", required=True)

    di = db_sub.add_parser("init", help="Initialize Markdown ledger skeleton (idempotent)")
    di.add_argument("--db", default=None, type=Path)
    add_account_args(di)

    dic = db_sub.add_parser("import-csv", help="Import a CSV file (canonical or broker-mapped columns)")
    dic.add_argument("--input", required=True, type=Path)
    dic.add_argument("--db", default=None, type=Path)
    dic.add_argument("--mapping", default=None, type=Path,
                     help="Optional JSON: {broker_column: canonical_field}")
    add_account_args(dic)

    dij = db_sub.add_parser("import-json", help="Import a JSON array / object of canonical transactions")
    dij.add_argument("--input", required=True, type=Path)
    dij.add_argument("--db", default=None, type=Path)
    add_account_args(dij)

    dpj = db_sub.add_parser(
        "preview-json",
        help="Dry-run a JSON import against a temporary ledger copy and print before/after summary",
    )
    dpj.add_argument("--input", required=True, type=Path)
    dpj.add_argument("--output", default=None, type=Path,
                     help="Optional path for the preview JSON summary")
    dpj.add_argument("--db", default=None, type=Path)
    add_account_args(dpj)

    da = db_sub.add_parser("add", help="Append one transaction from an inline JSON blob")
    da.add_argument("--json", required=True, help="Canonical JSON object (or list)")
    da.add_argument("--db", default=None, type=Path)
    add_account_args(da)

    dd = db_sub.add_parser("dump", help="Dump all transactions as JSON")
    dd.add_argument("--db", default=None, type=Path)
    add_account_args(dd)

    ds = db_sub.add_parser("stats", help="Print summary stats (counts by type, distinct tickers, date range)")
    ds.add_argument("--db", default=None, type=Path)
    add_account_args(ds)

    drb = db_sub.add_parser("rebuild", help="Force-rebuild generated projections from the Markdown transactions log")
    drb.add_argument("--db", default=None, type=Path)
    add_account_args(drb)

    # ---- ledger <subcommand> --------------------------------------------- #
    ledger = sub.add_parser(
        "ledger",
        help="Markdown ledger tools: lint, legacy export, rebuild/verify caches, verify parity",
    )
    ledger_sub = ledger.add_subparsers(dest="ledger_cmd", required=True)

    ll = ledger_sub.add_parser("lint", help="Validate Markdown ledger event files")
    ll.add_argument("--ledger", default=None, type=Path)
    add_account_args(ll)

    le = ledger_sub.add_parser("export-db", help="Non-destructively export legacy rows to Markdown event files")
    le.add_argument("--db", default=None, type=Path)
    le.add_argument("--out", "--ledger", dest="ledger", default=None, type=Path,
                    help="Target ledger directory; defaults to the resolved account ledger")
    mode = le.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan export without writing files")
    mode.add_argument("--write", action="store_true", help="Write event files and migration audit artifacts")
    add_account_args(le)

    lrc = ledger_sub.add_parser("rebuild-cache", help="Rebuild generated Markdown ledger cache files")
    lrc.add_argument("--ledger", default=None, type=Path)
    add_account_args(lrc)

    lvc = ledger_sub.add_parser("verify-cache", help="Verify generated cache files match Markdown replay")
    lvc.add_argument("--ledger", default=None, type=Path)
    add_account_args(lvc)

    lvp = ledger_sub.add_parser("verify-parity", help="Compare legacy replay/materialization to Markdown replay/cache")
    lvp.add_argument("--db", default=None, type=Path)
    lvp.add_argument("--ledger", default=None, type=Path)
    add_account_args(lvp)

    # ---- migration <subcommand> ------------------------------------------ #
    migration = sub.add_parser(
        "migration",
        help="Legacy-to-Markdown migration flow: detect, prepare, apply, verify, archive, rollback",
    )
    migration_sub = migration.add_subparsers(dest="migration_cmd", required=True)

    md = migration_sub.add_parser("detect", help="Read-only migration/account state classification")
    md.add_argument("--ledger", default=None, type=Path)
    add_account_args(md)

    mp = migration_sub.add_parser("prepare", help="Read legacy SQLite evidence and build a Markdown migration proposal")
    mp.add_argument("--db", default=None, type=Path)
    mp.add_argument("--ledger", default=None, type=Path)
    mp.add_argument("--migration-id", default=None)
    mp.add_argument("--write-proposal", action="store_true",
                    help="Write proposal JSON under ledger/migrations; otherwise print only")
    add_account_args(mp)

    ma = migration_sub.add_parser("apply", help="Gated: write Markdown events/caches; does not move legacy store evidence")
    ma.add_argument("--db", default=None, type=Path)
    ma.add_argument("--ledger", default=None, type=Path)
    ma.add_argument("--migration-id", default=None)
    ma.add_argument("--yes", action="store_true",
                    help="Required after the natural-language migration confirmation gate")
    add_account_args(ma)

    mv = migration_sub.add_parser("verify", help="Verify Markdown ledger/cache/parity after prepare/apply")
    mv.add_argument("--db", default=None, type=Path)
    mv.add_argument("--ledger", default=None, type=Path)
    mv.add_argument("--no-sqlite-mode", choices=("transition", "final"), default="transition")
    add_account_args(mv)

    mar = migration_sub.add_parser("archive-db", help="Separately gated move of legacy store evidence into ledger archive")
    mar.add_argument("--db", default=None, type=Path)
    mar.add_argument("--ledger", default=None, type=Path)
    mar.add_argument("--migration-id", default=None)
    mar.add_argument("--yes", action="store_true",
                     help="Required after the separate archive-db protected-file confirmation gate")
    add_account_args(mar)

    mr = migration_sub.add_parser("rollback", help="Gated recovery action for a recorded migration id")
    mr.add_argument("--ledger", default=None, type=Path)
    mr.add_argument("--migration-id", required=True)
    mr.add_argument("--restore-db-evidence", action="store_true",
                    help="Copy archived DB evidence back as legacy import input only; never runtime fallback")
    mr.add_argument("--yes", action="store_true",
                    help="Required after rollback confirmation gate")
    add_account_args(mr)

    vns = migration_sub.add_parser("verify-no-sqlite", help="Static SQLite quarantine validator")
    vns.add_argument("--root", default=Path.cwd(), type=Path)
    vns.add_argument("--mode", choices=("transition", "final"), default="final")

    # ---- account <subcommand> --------------------------------------------- #
    acct = sub.add_parser("account", help="Manage accounts (multi-account support)")
    acct_sub = acct.add_subparsers(dest="account_cmd", required=True)

    acct_use = acct_sub.add_parser("use", help="Set active account (writes accounts/.active)")
    acct_use.add_argument("name", help="Account name (must already exist under accounts/)")

    acct_create = acct_sub.add_parser("create", help="Scaffold a new account")
    acct_create.add_argument("name", help="Account name (lowercase, [a-z0-9_-]{1,32}, not 'demo')")

    acct_sub.add_parser("list", help="List all accounts; mark active")
    acct_sub.add_parser("detect", help="Print account layout state (clean, migrate, partial, demo_only_at_root)")

    acct_migrate = acct_sub.add_parser("migrate", help="Migrate root layout into accounts/default/")
    acct_migrate.add_argument("--yes", action="store_true",
                              help="Skip the [y/N] prompt (required for non-interactive contexts)")

    return p


def _base_currency_from_settings(path: Path) -> str:
    if not path.exists():
        return "USD"
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*-\s*Base currency\s*:\s*(?P<c>[A-Z]{3})", raw)
        if m:
            return m.group("c").upper()
    return "USD"


def _resolve_paths(args: argparse.Namespace) -> Tuple[Path, Optional[Path]]:
    """Resolve (db_path, settings_path) for the active account, honouring
    explicit ``--db`` / ``--settings`` overrides and ``--account NAME``.
    Emits a warning to stderr when --db and --settings come from different
    accounts (cross-account pairing). Returns (db_path, settings_path);
    settings_path is None for subcommands that do not consume settings."""
    paths = resolve_account(args)
    db_path = (
        Path(getattr(args, "db"))
        if getattr(args, "db", None) is not None
        else paths.db
    )
    settings_attr = getattr(args, "settings", None)
    if hasattr(args, "settings"):
        settings_path = Path(settings_attr) if settings_attr is not None else paths.settings
    else:
        settings_path = None
    warn = check_pairing(db_path, settings_path)
    if warn:
        print(f"WARNING: {warn}", file=sys.stderr)
    ledger_attr = getattr(args, "ledger", None)
    ledger_path = Path(ledger_attr) if ledger_attr is not None else paths.ledger
    ledger_warn = check_ledger_pairing(db_path, settings_path, ledger_path)
    if ledger_warn:
        print(f"WARNING: {ledger_warn}", file=sys.stderr)
    return db_path, settings_path


def _resolve_ledger_path(args: argparse.Namespace) -> Path:
    paths = resolve_account(args)
    ledger_attr = getattr(args, "ledger", None)
    ledger_path = Path(ledger_attr) if ledger_attr is not None else paths.ledger
    db_attr = getattr(args, "db", None)
    db_path = Path(db_attr) if db_attr is not None else paths.db
    settings_attr = getattr(args, "settings", None)
    settings_path = Path(settings_attr) if settings_attr is not None else paths.settings
    warn = check_ledger_pairing(db_path, settings_path, ledger_path)
    if warn:
        print(f"WARNING: {warn}", file=sys.stderr)
    return ledger_path


def _resolve_txns(args: argparse.Namespace) -> List[Transaction]:
    """Resolve transactions from the selected store."""
    ledger_store = getattr(args, "ledger_store", "auto")
    db = Path(getattr(args, "db")) if getattr(args, "db", None) is not None else _resolve_paths(args)[0]
    ledger_path = _resolve_ledger_path(args)
    selected = select_ledger_store(db, ledger_path, ledger_store)
    if selected == "markdown":
        return load_transactions_markdown(ledger_path)
    if selected == "db" and db.exists():
        db_init(db)
        return load_transactions_db(db)
    return []


def main(argv: Optional[List[str]] = None) -> int:
    # First: special-case the 'account' subcommand path so 'account migrate'
    # works without triggering the auto-detect hook (since 'account migrate'
    # IS the migration entry). Detect by sniffing argv[0] before parsing.
    raw = list(argv) if argv is not None else sys.argv[1:]
    is_account_cmd = len(raw) > 0 and raw[0] == "account"
    is_migration_cmd = len(raw) > 0 and raw[0] == "migration"
    if not is_account_cmd and not is_migration_cmd:
        autodetect_and_migrate_or_exit()

    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.cmd == "account":
        return _handle_account_cmd(args)

    if args.cmd == "self-check":
        return _selfcheck()


    if args.cmd == "verify":
        db_path, _ = _resolve_paths(args)
        args.db = db_path
        ledger_path = _resolve_ledger_path(args)
        if select_ledger_store(db_path, ledger_path, "auto") == "markdown":
            try:
                ok, issues = ledger_verify_cache(ledger_path)
            except Exception as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            if ok:
                print("OK: Markdown ledger generated caches match replay.")
                return 0
            print("MISMATCH (Markdown generated caches drifted from event replay; run `ledger rebuild-cache`):")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        ok, mismatches = _verify_balance_tables(args)
        if ok:
            print("OK: replay matches open_lots + cash_balances.")
            return 0
        print("MISMATCH (generated caches drifted from Markdown replay; rebuild ledger caches):")
        for m in mismatches:
            print(f"  - {m}")
        return 1

    if args.cmd == "replay":
        db_path, _ = _resolve_paths(args)
        args.db = db_path
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
        db_path, settings_path = _resolve_paths(args)
        args.db = db_path
        args.settings = settings_path
        txns = _resolve_txns(args)
        prices = json.loads(args.prices.read_text(encoding="utf-8")) if args.prices.exists() else {}
        base = _base_currency_from_settings(args.settings)
        snap = compute_realized_unrealized(txns, prices, base=base)
        print(json.dumps(snap, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "profit-panel":
        db_path, settings_path = _resolve_paths(args)
        args.db = db_path
        args.settings = settings_path
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
                DISPLAY_NAME_BY_LOCALE,
                Lot,
                SettingsProfile,
                _compute_snapshot_core,
                compute_snapshot,
                parse_settings_profile,
                write_snapshot,
            )
        except ImportError as exc:
            print(f"ERROR: cannot import portfolio_snapshot ({exc}). "
                  "Make sure scripts/portfolio_snapshot.py exists alongside transactions.py.",
                  file=sys.stderr)
            return 5

        if not args.prices.exists():
            print(f"ERROR: --prices file {args.prices} not found "
                  "(run scripts/fetch_prices.py first).", file=sys.stderr)
            return 3
        prices = json.loads(args.prices.read_text(encoding="utf-8"))
        today = _dt.date.fromisoformat(args.today) if args.today else _dt.date.today()

        if getattr(args, "all_accounts", False):
            if args.db is not None or args.settings is not None:
                print("ERROR: --all-accounts is incompatible with --db / --settings",
                      file=sys.stderr)
                return 2
            from account import resolve_all_accounts        # noqa: WPS433
            all_paths = resolve_all_accounts()
            base_ccy = (args.base_currency or "USD").upper()
            # DISPLAY-CONFLICT (iteration 4): SettingsProfile.display_name
            # carries the LANGUAGE display label (e.g., "English"), which
            # the renderer prints next to the eyebrow.  The "Total (All
            # Accounts)" identification belongs in context["subtitle"]
            # (Step 5d:6 in generate_report.py), not here.
            locale = "en"
            settings = SettingsProfile(
                raw_language="english",
                locale=locale,
                display_name=DISPLAY_NAME_BY_LOCALE[locale],
                config_overrides={},
                base_currency=base_ccy,
                missing=False,
            )

            # Concatenate lots; tag txns with originating account name for
            # deterministic ordering.  Tuple-ordering avoids any Transaction
            # attribute pollution beyond `seq`.
            all_lots: List[Lot] = []
            tagged: List[Tuple[str, Transaction]] = []
            for ap in all_paths:
                selected_store = select_ledger_store(ap.db, ap.ledger, getattr(args, "ledger_store", "auto"))
                if selected_store == "markdown":
                    all_lots.extend(load_holdings_lots_markdown(ap.ledger))
                    account_txns = load_transactions_markdown(ap.ledger)
                else:
                    all_lots.extend(load_holdings_lots(ap.db))
                    account_txns = load_transactions_db(ap.db)
                for t in account_txns:
                    tagged.append((ap.name, t))

            # CB-2: deterministic global order = (date, account_name, original_seq).
            tagged.sort(key=lambda pair: (pair[1].date, pair[0], pair[1].seq))

            # Re-sequence: rewrite seq to be globally unique + ordered.  No
            # monkeypatch.  Transaction is a regular @dataclass (not frozen),
            # so direct attribute mutation is safe; if a future change adds
            # frozen=True, swap to dataclasses.replace(t, seq=new_seq).
            all_txns: List[Transaction] = []
            for new_seq, (_acct, t) in enumerate(tagged):
                t.seq = new_seq
                all_txns.append(t)

            snap = _compute_snapshot_core(
                lots=all_lots,
                txns=all_txns,
                prices=prices,
                settings=settings,
                today=today,
                total_mode=True,
            )
        else:
            db_path, settings_path = _resolve_paths(args)
            args.db = db_path
            args.settings = settings_path
            # Defense-in-depth: the snapshot bakes settings_locale /
            # display_name / raw_language / base_currency into the JSON; the
            # renderer reads them from the snapshot and ignores its own
            # --settings flag for those fields. So a demo --db with the root
            # --settings default silently renders the report in the root
            # profile's language. Mirror the generate_report.py guard but
            # trigger off --db instead of --output.
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
            settings = parse_settings_profile(args.settings)
            ledger_path = _resolve_ledger_path(args)
            if select_ledger_store(args.db, ledger_path, getattr(args, "ledger_store", "auto")) == "markdown":
                snap = _compute_snapshot_core(
                    lots=load_holdings_lots_markdown(ledger_path),
                    txns=load_transactions_markdown(ledger_path),
                    prices=prices,
                    settings=settings,
                    today=today,
                    total_mode=False,
                )
            else:
                snap = compute_snapshot(
                    db_path=args.db,
                    prices=prices,
                    settings=settings,
                    today=today,
                )
        if not snap.aggregates:
            print(f"ERROR: Markdown ledger for {args.db} has no positions. "
                  "Import or append ledger events first.",
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
        db_path, settings_path = _resolve_paths(args)
        args.db = db_path
        args.settings = settings_path
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
        db_path, _ = _resolve_paths(args)
        args.db = db_path
        return _dispatch_db(args)

    if args.cmd == "ledger":
        return _dispatch_ledger(args)

    if args.cmd == "migration":
        return _dispatch_migration(args)

    return 2


def _handle_account_cmd(args: argparse.Namespace) -> int:
    """Dispatch the 'account' subcommand group: use / create / list / migrate."""
    sub = args.account_cmd
    if sub == "use":
        try:
            write_active_pointer(args.name)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(f"Active account set to: {args.name}")
        return 0
    if sub == "create":
        try:
            validate_account_name(args.name, for_create=True)
            paths = create_account_scaffold(args.name)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(f"Created account: {paths.name}")
        print(f"  settings: {paths.settings}")
        print(f"  legacy:   {paths.db}")
        print(f"  ledger:   {paths.ledger}")
        print(f"  reports:  {paths.reports_dir}")
        print("Set as active with: python scripts/transactions.py account use", paths.name)
        return 0
    if sub == "list":
        accounts = list_accounts()
        active = read_active_pointer()
        if not accounts:
            print("No accounts. Run: python scripts/transactions.py account create <name>")
            return 0
        for name in accounts:
            marker = "*" if name == active else " "
            description = read_account_description(name)
            suffix = f" — {description}" if description else ""
            print(f" {marker} {name}{suffix}")
        return 0
    if sub == "detect":
        print(detect_legacy_layout())
        return 0
    if sub == "migrate":
        prompt_and_migrate(assume_yes=args.yes)
        return 0
    print(f"Unknown account subcommand: {sub}", file=sys.stderr)
    return 1


# --------------------------------------------------------------------------- #
# CLI helpers — DB dispatch
# --------------------------------------------------------------------------- #

def _dispatch_ledger(args: argparse.Namespace) -> int:
    ledger_path = _resolve_ledger_path(args)

    if args.ledger_cmd == "lint":
        try:
            events = load_event_dicts(ledger_path)
            errors = validate_event_set(events)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if errors:
            print("Markdown ledger lint failed:")
            for err in errors:
                print(f"  - {err}")
            return 1
        print(f"OK: {len(events)} Markdown ledger event(s) valid at {ledger_path}")
        return 0

    if args.ledger_cmd == "export-db":
        db_path, _ = _resolve_paths(args)
        result = ledger_export_db(db_path, ledger_path, write=bool(args.write))
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        if args.write and result.get("parity", {}).get("ok") is False:
            return 1
        return 0

    if args.ledger_cmd == "rebuild-cache":
        try:
            result = ledger_rebuild_cache(ledger_path)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.ledger_cmd == "verify-cache":
        try:
            ok, issues = ledger_verify_cache(ledger_path)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if ok:
            print(f"OK: generated caches match Markdown replay at {ledger_path}")
            return 0
        print("Markdown generated cache mismatch:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    if args.ledger_cmd == "verify-parity":
        db_path, _ = _resolve_paths(args)
        try:
            ok, report = ledger_verify_parity(db_path, ledger_path)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if ok else 1

    print(f"Unknown ledger subcommand: {args.ledger_cmd}", file=sys.stderr)
    return 1


# --------------------------------------------------------------------------- #
# CLI helpers — migration-flow dispatch
# --------------------------------------------------------------------------- #

def _dispatch_migration(args: argparse.Namespace) -> int:
    try:
        if args.migration_cmd == "detect":
            result = migration_detect(args)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0
        if args.migration_cmd == "prepare":
            result = migration_prepare(args)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0 if not result.get("blockers") else 1
        if args.migration_cmd == "apply":
            result = migration_apply(args)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            parity = result.get("parity") or {}
            return 0 if parity.get("ok", True) else 1
        if args.migration_cmd == "verify":
            result = migration_verify(args)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0 if result.get("ok") else 1
        if args.migration_cmd == "archive-db":
            result = migration_archive_db(args)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0
        if args.migration_cmd == "rollback":
            result = migration_rollback(args)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0
        if args.migration_cmd == "verify-no-sqlite":
            result = migration_verify_no_sqlite(args)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0 if result.get("ok") else 1
    except PermissionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI should surface concise diagnostics
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Unknown migration subcommand: {args.migration_cmd}", file=sys.stderr)
    return 1


# --------------------------------------------------------------------------- #
# CLI helpers — DB dispatch
# --------------------------------------------------------------------------- #


def _verify_balance_tables(args: argparse.Namespace) -> Tuple[bool, List[str]]:
    """Compatibility verifier: check Markdown generated caches against replay."""
    db_path = Path(args.db) if hasattr(args, "db") else DEFAULT_DB_PATH
    ledger_dir = _legacy_ledger_dir_for_path(db_path)
    if not ledger_dir.exists():
        return False, [f"Markdown ledger not found: {ledger_dir}"]
    return ledger_verify_cache(ledger_dir)


def _dispatch_db(args: argparse.Namespace) -> int:
    db = args.db

    if args.db_cmd == "init":
        status = db_init(db)
        print(f"Markdown ledger {status} for {db}.")
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

    if args.db_cmd == "preview-json":
        preview, errs = db_preview_json(args.input, db)
        if errs:
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 4
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote JSON import preview to {args.output}.")
        else:
            print(json.dumps(preview, indent=2, ensure_ascii=False))
        return 0 if preview.get("ok") else 4

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
        result = db_rebuild_balances(db)
        print(json.dumps({"rebuilt": result}, indent=2, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
