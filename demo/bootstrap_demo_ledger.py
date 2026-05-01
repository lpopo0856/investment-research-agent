#!/usr/bin/env python3
"""
Build / refresh the synthetic demo transaction seed and optionally materialize
`demo/transactions.db`. This script only prepares fake transaction data; report
generation is handled by the normal agent workflow (see demo/README.md).

Run from repo root:
  python demo/bootstrap_demo_ledger.py --write-json
  python demo/bootstrap_demo_ledger.py --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
DEMO = REPO / "demo"
JSON_PATH = DEMO / "transactions_history.json"
DB_PATH = DEMO / "transactions.db"


def _usd_dep(d: str, amount: float) -> dict:
    return {
        "date": d,
        "type": "DEPOSIT",
        "amount": amount,
        "currency": "USD",
        "cash_account": "USD",
        "market": "US",
    }


def _twd_dep(d: str, amount: float) -> dict:
    return {
        "date": d,
        "type": "DEPOSIT",
        "amount": amount,
        "currency": "TWD",
        "cash_account": "TWD",
        "market": "TW",
    }


def _buy(d: str, t: str, q: float, p: float, bucket: str, market: str, ccy: str, cash: str) -> dict:
    return {
        "date": d,
        "type": "BUY",
        "ticker": t,
        "qty": q,
        "price": p,
        "bucket": bucket,
        "market": market,
        "currency": ccy,
        "cash_account": cash,
    }


def _sell(d: str, t: str, q: float, p: float, market: str, ccy: str, cash: str) -> dict:
    return {
        "date": d,
        "type": "SELL",
        "ticker": t,
        "qty": q,
        "price": p,
        "market": market,
        "currency": ccy,
        "cash_account": cash,
    }


def _div(d: str, ticker: str, amount: float, ccy: str = "USD") -> dict:
    return {
        "date": d,
        "type": "DIVIDEND",
        "ticker": ticker,
        "amount": amount,
        "currency": ccy,
        "cash_account": ccy,
        "market": "US",
    }


def _fee(d: str, amount: float, ccy: str = "USD") -> dict:
    return {
        "date": d,
        "type": "FEE",
        "amount": amount,
        "currency": ccy,
        "cash_account": ccy,
        "market": "US",
    }


def _withdraw(d: str, amount: float, ccy: str = "USD") -> dict:
    return {
        "date": d,
        "type": "WITHDRAW",
        "amount": amount,
        "currency": ccy,
        "cash_account": ccy,
        "market": "US",
    }


def build_transactions() -> list[dict]:
    """Synthetic multi-year ledger (2024–2026) ending in a diversified book."""
    LT, MT, ST = "Long Term", "Mid Term", "Short Term"
    tx: list[dict] = []

    # --- 2024: seed + core positions ---
    tx.append(_usd_dep("2024-01-08", 820_000))
    tx.append(_twd_dep("2024-01-09", 3_200_000))
    tx.append(_buy("2024-01-12", "QQQ", 120, 428.0, LT, "US", "USD", "USD"))
    tx.append(_buy("2024-01-18", "MSFT", 80, 378.0, LT, "US", "USD", "USD"))
    tx.append(_buy("2024-01-25", "NVDA", 140, 56.5, MT, "US", "USD", "USD"))
    tx.append(_buy("2024-02-01", "AMD", 160, 148.0, MT, "US", "USD", "USD"))
    tx.append(_div("2024-02-06", "MSFT", 140.0))
    tx.append(_buy("2024-02-14", "2330.TW", 500, 718.0, LT, "TW", "TWD", "TWD"))
    tx.append(_buy("2024-02-22", "GOOGL", 70, 141.0, MT, "US", "USD", "USD"))
    tx.append(_sell("2024-03-05", "NVDA", 45, 88.5, "US", "USD", "USD"))
    tx.append(_fee("2024-03-06", 6.25))
    tx.append(_buy("2024-03-18", "BTC", 1.2, 67200.0, MT, "crypto", "USD", "USD"))
    tx.append(_buy("2024-04-02", "QQQ", 50, 436.0, LT, "US", "USD", "USD"))
    tx.append(_sell("2024-04-16", "QQQ", 30, 448.0, "US", "USD", "USD"))
    tx.append(_div("2024-04-22", "QQQ", 210.0))
    tx.append(_buy("2024-05-03", "MSFT", 50, 408.0, LT, "US", "USD", "USD"))
    tx.append(_buy("2024-05-20", "NVDA", 60, 95.2, MT, "US", "USD", "USD"))
    tx.append(_sell("2024-06-07", "AMD", 70, 152.0, "US", "USD", "USD"))
    tx.append(_buy("2024-06-18", "2330.TW", 350, 868.0, LT, "TW", "TWD", "TWD"))
    tx.append(_buy("2024-07-01", "GOOGL", 40, 168.0, MT, "US", "USD", "USD"))
    tx.append(_withdraw("2024-07-15", 55_000))
    tx.append(_usd_dep("2024-07-22", 180_000))
    tx.append(_buy("2024-08-01", "SMR", 600, 7.8, ST, "US", "USD", "USD"))
    tx.append(_buy("2024-08-20", "BTC", 0.9, 69800.0, MT, "crypto", "USD", "USD"))
    tx.append(_sell("2024-09-03", "GOOGL", 35, 162.0, "US", "USD", "USD"))
    tx.append(_buy("2024-09-16", "AMD", 100, 158.0, MT, "US", "USD", "USD"))
    tx.append(_div("2024-09-30", "MSFT", 95.0))
    tx.append(_buy("2024-10-10", "NVDA", 40, 132.0, MT, "US", "USD", "USD"))
    tx.append(_sell("2024-10-28", "SMR", 250, 9.4, "US", "USD", "USD"))
    tx.append(_buy("2024-11-05", "QQQ", 35, 488.0, LT, "US", "USD", "USD"))
    tx.append(_fee("2024-11-12", 4.99))
    tx.append(_buy("2024-12-02", "MSFT", 25, 418.0, LT, "US", "USD", "USD"))
    tx.append(_div("2024-12-15", "AMD", 18.0))

    # --- 2025: flows + rebalancing ---
    tx.append(_buy("2025-01-08", "GOOGL", 55, 188.0, MT, "US", "USD", "USD"))
    tx.append(_sell("2025-01-20", "MSFT", 40, 434.0, "US", "USD", "USD"))
    tx.append(_buy("2025-02-03", "SMR", 450, 14.2, ST, "US", "USD", "USD"))
    tx.append(_sell("2025-02-18", "NVDA", 55, 138.0, "US", "USD", "USD"))
    tx.append(_buy("2025-03-01", "BTC", 0.55, 84200.0, MT, "crypto", "USD", "USD"))
    tx.append(_buy("2025-03-14", "2330.TW", 220, 942.0, LT, "TW", "TWD", "TWD"))
    tx.append(_div("2025-03-28", "QQQ", 165.0))
    tx.append(_buy("2025-04-08", "AMD", 120, 144.0, MT, "US", "USD", "USD"))
    tx.append(_sell("2025-04-22", "BTC", 0.35, 71200.0, "crypto", "USD", "USD"))
    tx.append(_usd_dep("2025-05-01", 260_000))
    tx.append(_buy("2025-05-12", "NVDA", 35, 114.0, MT, "US", "USD", "USD"))
    tx.append(_sell("2025-06-01", "QQQ", 25, 502.0, "US", "USD", "USD"))
    tx.append(_buy("2025-06-20", "MSFT", 30, 440.0, LT, "US", "USD", "USD"))
    tx.append(_buy("2025-07-08", "SMR", 320, 17.6, ST, "US", "USD", "USD"))
    tx.append(_sell("2025-07-25", "AMD", 90, 168.0, "US", "USD", "USD"))
    tx.append(_div("2025-08-05", "MSFT", 125.0))
    tx.append(_buy("2025-08-18", "GOOGL", 30, 164.0, MT, "US", "USD", "USD"))
    tx.append(_buy("2025-09-02", "BTC", 0.4, 91500.0, MT, "crypto", "USD", "USD"))
    tx.append(_sell("2025-09-16", "SMR", 400, 16.8, "US", "USD", "USD"))
    tx.append(_buy("2025-10-01", "QQQ", 40, 512.0, LT, "US", "USD", "USD"))
    tx.append(_fee("2025-10-15", 8.0))
    tx.append(_buy("2025-11-04", "NVDA", 25, 192.0, MT, "US", "USD", "USD"))
    tx.append(_sell("2025-11-22", "GOOGL", 40, 178.0, "US", "USD", "USD"))
    tx.append(_buy("2025-12-08", "AMD", 80, 122.0, MT, "US", "USD", "USD"))

    # --- 2026 YTD: recent activity for pacing / analytics ---
    tx.append(_buy("2026-01-06", "MSFT", 18, 428.0, LT, "US", "USD", "USD"))
    tx.append(_sell("2026-01-24", "BTC", 0.5, 102000.0, "crypto", "USD", "USD"))
    tx.append(_buy("2026-02-03", "SMR", 280, 21.4, ST, "US", "USD", "USD"))
    tx.append(_div("2026-02-14", "MSFT", 88.0))
    tx.append(_buy("2026-03-03", "2330.TW", 150, 988.0, LT, "TW", "TWD", "TWD"))
    tx.append(_sell("2026-03-18", "NVDA", 30, 118.0, "US", "USD", "USD"))
    tx.append(_buy("2026-04-01", "GOOGL", 25, 154.0, MT, "US", "USD", "USD"))
    tx.append(_fee("2026-04-10", 5.5))

    return tx


def _validate_replay(txns: list[dict]) -> None:
    sys.path.insert(0, str(SCRIPTS))
    from transactions import _dict_to_transaction, replay  # noqa: WPS433

    parsed = [_dict_to_transaction(d, seq=i) for i, d in enumerate(txns)]
    st = replay(parsed)
    for iss in st.issues:
        raise SystemExit(f"replay issue: {iss}")
    for ccy, bal in st.cash.items():
        if bal < -1e-2:
            raise SystemExit(f"negative cash {ccy}: {bal}")


def _apply_db() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    subprocess.check_call(
        [sys.executable, str(SCRIPTS / "transactions.py"), "db", "init", "--db", str(DB_PATH)],
        cwd=str(REPO),
    )
    subprocess.check_call(
        [
            sys.executable,
            str(SCRIPTS / "transactions.py"),
            "db",
            "import-json",
            "--input",
            str(JSON_PATH),
            "--db",
            str(DB_PATH),
        ],
        cwd=str(REPO),
    )
    subprocess.check_call(
        [sys.executable, str(SCRIPTS / "transactions.py"), "verify", "--db", str(DB_PATH)],
        cwd=str(REPO),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-json", action="store_true", help=f"Write {JSON_PATH.name}")
    ap.add_argument("--apply", action="store_true", help="Recreate demo DB from JSON")
    args = ap.parse_args()
    txns = build_transactions()
    _validate_replay(txns)

    if args.write_json or not JSON_PATH.exists():
        DEMO.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json.dumps(txns, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {JSON_PATH} ({len(txns)} txns)")

    if args.apply:
        if not JSON_PATH.exists():
            print("ERROR: run with --write-json first", file=sys.stderr)
            return 2
        _apply_db()
        print(f"Materialized {DB_PATH}")

    if not args.write_json and not args.apply:
        ap.print_help()
        print("\nTip: use --write-json and/or --apply")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
