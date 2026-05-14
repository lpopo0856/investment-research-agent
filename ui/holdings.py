"""Cost-basis holdings view for the local UI.

This module reads holdings from the per-account ledger DB and returns
quantity + average cost + total cost per ticker. **No live price fetch.**
The UI is a viewer of the ledger state; market prices are out of scope for
the local one-page UI and are produced by the existing report pipeline
when the user generates a report through the embedded agent.
"""

from __future__ import annotations

import concurrent.futures
import sys
from pathlib import Path
from typing import Any

from ui.accounts import REPO_ROOT, resolve_account_path

_SCRIPTS_DIR = str((REPO_ROOT / "scripts").resolve())

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import portfolio_snapshot as ps  # noqa: E402


class HoldingsRecomputeError(RuntimeError):
    """Holdings read failed. The UI surfaces this; never substitute cached data."""


def _do_recompute(account_dir: Path) -> dict[str, Any]:
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
        }
        for agg in (payload.get("aggregates") or [])
    ]

    return {"as_of": payload.get("generated_at"), "rows": rows}


def recompute_holdings(account: str, timeout_s: float = 10.0) -> dict[str, Any]:
    """Return cost-basis holdings for *account*.

    Reads the ledger DB and aggregates by ticker — no network calls, no price
    fetching. Each row contains: ``ticker``, ``qty``, ``avg_cost`` (in the
    lot's native trade currency), ``total_cost`` (native), ``trade_currency``.

    Raises :class:`HoldingsRecomputeError` on any failure (missing db,
    snapshot error, timeout). The UI surfaces the failure inline; it must
    not substitute cached data.
    """
    account_dir = resolve_account_path(account)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_do_recompute, account_dir)
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
