"""Cost-basis holdings view for the local UI.

This module reads holdings from the per-account Markdown ledger and returns
quantity + average cost + total cost per ticker. **No live price fetch.**
The UI is a viewer of the canonical ledger state; market prices are out of
scope for the local one-page UI and are produced by the existing report
pipeline when the user generates a report through the embedded agent.
"""

from __future__ import annotations

import concurrent.futures
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ui.accounts import REPO_ROOT, discover_accounts, resolve_account_path

_SCRIPTS_DIR = str((REPO_ROOT / "scripts").resolve())

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import portfolio_snapshot as ps  # noqa: E402
from transactions import load_transactions_markdown, replay  # noqa: E402


class HoldingsRecomputeError(RuntimeError):
    """Holdings read failed. The UI surfaces this; never substitute cached data."""


def _markdown_as_of(ledger_dir: Path) -> str | None:
    """Return latest source mtime for the ledger, as an ISO UTC timestamp."""
    mtimes = [
        path.stat().st_mtime
        for path in ledger_dir.rglob("*.md")
        if path.is_file() and "generated" not in path.parts
    ]
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes), tz=timezone.utc).isoformat()


def _do_recompute_markdown(account_dir: Path, account_name: str | None = None) -> dict[str, Any]:
    ledger_dir = account_dir / "ledger"
    if not ledger_dir.exists():
        raise HoldingsRecomputeError("no Markdown ledger for account")

    state = replay(load_transactions_markdown(ledger_dir))
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}

    for ticker, lots in state.open_lots.items():
        for lot in lots:
            qty = float(lot.qty or 0)
            if abs(qty) <= 1e-9:
                continue
            currency = lot.currency or ""
            key = ("position", ticker, currency)
            row = grouped.setdefault(
                key,
                {
                    "_kind": "position",
                    "ticker": ticker,
                    "qty": 0.0,
                    "total_cost": 0.0,
                    "trade_currency": currency,
                    **({"account": account_name} if account_name else {}),
                },
            )
            row["qty"] += qty
            row["total_cost"] += qty * float(lot.cost or 0)

    for currency, amount in state.cash.items():
        amount = float(amount or 0)
        if abs(amount) <= 1e-9:
            continue
        key = ("cash", currency, currency)
        row = grouped.setdefault(
            key,
            {
                "_kind": "cash",
                "ticker": currency,
                "qty": 0.0,
                "total_cost": 0.0,
                "trade_currency": currency,
                **({"account": account_name} if account_name else {}),
            },
        )
        row["qty"] += amount
        row["total_cost"] += amount

    rows = []
    for row in grouped.values():
        qty = row.get("qty") or 0
        is_cash = row.pop("_kind") == "cash"
        row["avg_cost"] = None if is_cash or abs(qty) <= 1e-9 else row["total_cost"] / qty
        rows.append(row)

    rows.sort(
        key=lambda row: (
            str(row.get("account") or ""),
            str(row.get("ticker") or ""),
            str(row.get("trade_currency") or ""),
        )
    )
    return {"as_of": _markdown_as_of(ledger_dir), "rows": rows}


def _do_recompute_db(account_dir: Path, account_name: str | None = None) -> dict[str, Any]:
    settings_path = account_dir / "SETTINGS.md"
    db_path = account_dir / "transactions.db.bak"

    if not db_path.exists():
        raise HoldingsRecomputeError("no transactions db for account")
    if not settings_path.exists():
        raise HoldingsRecomputeError("no SETTINGS.md for account")

    settings = ps.parse_settings_profile(settings_path)
    # Pure ledger view: pass empty prices so latest_price / market_value stay
    # None. Only cost-basis fields (qty, weighted_avg_cost, total_cost_known,
    # trade_currency) are surfaced to the UI.
    snapshot = ps.compute_snapshot(db_path=db_path, prices={}, settings=settings)
    payload = ps.serialize_snapshot(snapshot)

    rows = [
        {
            "ticker": agg.get("ticker"),
            "qty": agg.get("total_qty"),
            "avg_cost": agg.get("weighted_avg_cost"),
            "total_cost": agg.get("total_cost_known"),
            "trade_currency": agg.get("trade_currency"),
            **({"account": account_name} if account_name else {}),
        }
        for agg in (payload.get("aggregates") or [])
    ]

    return {"as_of": payload.get("generated_at"), "rows": rows}


def _do_recompute(account_dir: Path, account_name: str | None = None) -> dict[str, Any]:
    ledger_dir = account_dir / "ledger"
    if ledger_dir.exists():
        return _do_recompute_markdown(account_dir, account_name=account_name)
    return _do_recompute_db(account_dir, account_name=account_name)


def _do_recompute_total() -> dict[str, Any]:
    """Return a read-only holdings rollup across real accounts.

    ``_total`` is a special reports/overview account and intentionally has no
    ledger DB of its own. For the UI holdings view, list each underlying
    account's holdings with an ``account`` field so the frontend can hide
    transaction actions and still show where each position belongs.
    """
    rows: list[dict[str, Any]] = []
    as_of_values: list[str] = []
    skipped_missing_sources: list[str] = []

    for account_name in discover_accounts():
        if account_name == "_total":
            continue
        account_dir = resolve_account_path(account_name)
        has_ledger = (account_dir / "ledger").exists()
        has_db = (account_dir / "transactions.db.bak").exists()
        if not has_ledger and not has_db:
            skipped_missing_sources.append(account_name)
            continue
        payload = _do_recompute(account_dir, account_name=account_name)
        if payload.get("as_of"):
            as_of_values.append(payload["as_of"])
        rows.extend(payload.get("rows") or [])

    rows.sort(
        key=lambda row: (str(row.get("account") or ""), str(row.get("ticker") or ""))
    )
    return {
        "as_of": max(as_of_values) if as_of_values else None,
        "rows": rows,
        "is_total": True,
        "read_only": True,
        "skipped_accounts": skipped_missing_sources,
    }


def recompute_holdings(account: str, timeout_s: float = 10.0) -> dict[str, Any]:
    """Return cost-basis holdings for *account*.

    Reads the ledger DB and aggregates by ticker — no network calls, no price
    fetching. Each row contains: ``ticker``, ``qty``, ``avg_cost`` (in the
    lot's native trade currency), ``total_cost`` (native), ``trade_currency``.

    Raises :class:`HoldingsRecomputeError` on any failure (missing db,
    snapshot error, timeout). The UI surfaces the failure inline; it must
    not substitute cached data.
    """
    if account == "_total":
        resolve_account_path(account)
        work = _do_recompute_total
    else:
        account_dir = resolve_account_path(account)
        work = lambda: _do_recompute(account_dir)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(work)
    try:
        return future.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError:
        future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        raise HoldingsRecomputeError(f"holdings read timed out after {timeout_s}s")
    except HoldingsRecomputeError:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    except Exception as exc:  # noqa: BLE001
        pool.shutdown(wait=False, cancel_futures=True)
        raise HoldingsRecomputeError(repr(exc)) from exc
    else:
        pool.shutdown(wait=False)
