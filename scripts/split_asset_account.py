#!/usr/bin/env python3
"""Split a market or ticker set into a separate account ledger.

Default mode is a dry run. It writes canonical JSON plans plus temporary
SQLite ledgers, verifies both ledgers, and checks combined cash/open-lot
balances against the original source DB.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from account import (  # noqa: E402
    AccountPaths,
    create_account_scaffold,
    resolve_account,
    validate_account_name,
)
from transactions import (  # noqa: E402
    _verify_balance_tables,
    db_connect,
    db_import_records,
    db_init,
)


CANONICAL_FIELDS = {
    "date",
    "type",
    "ticker",
    "qty",
    "price",
    "gross",
    "fees",
    "net",
    "amount",
    "currency",
    "cash_account",
    "bucket",
    "market",
    "rationale",
    "tags",
    "from_amount",
    "from_currency",
    "from_cash_account",
    "to_amount",
    "to_currency",
    "to_cash_account",
    "rate",
    "target_id",
}


@dataclass(frozen=True)
class SplitPlan:
    source_records: list[dict[str, Any]]
    target_records: list[dict[str, Any]]
    selected: list[dict[str, Any]]
    funding_bridges: list[dict[str, Any]]


def _clean_record(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in CANONICAL_FIELDS if row.get(k) is not None}


def _load_records(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path} not found")
    conn = db_connect(db_path)
    try:
        lots_by_tx: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for lot in conn.execute(
            "SELECT transaction_id, acq_date, cost, qty "
            "FROM sell_lot_consumption ORDER BY id"
        ):
            lots_by_tx[int(lot["transaction_id"])].append(
                {
                    "acq_date": lot["acq_date"],
                    "cost": lot["cost"],
                    "qty": lot["qty"],
                }
            )

        out: list[dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM transactions ORDER BY id"):
            d = dict(row)
            d["lots"] = lots_by_tx.get(int(row["id"]), [])
            out.append(d)
        return out
    finally:
        conn.close()


def _parse_tickers(values: Iterable[str] | None) -> set[str]:
    tickers: set[str] = set()
    for value in values or []:
        for part in value.split(","):
            clean = part.strip().upper()
            if clean:
                tickers.add(clean)
    return tickers


def _selected(row: dict[str, Any], *, market: str | None, tickers: set[str]) -> bool:
    row_ticker = str(row.get("ticker") or "").upper()
    row_market = str(row.get("market") or "").lower()
    if tickers and row_ticker in tickers:
        return True
    if market and row_market == market.lower():
        return True
    return False


def _buy_funding_bridge(row: dict[str, Any], *, direction: str) -> dict[str, Any]:
    qty = float(row.get("qty") or 0)
    price = float(row.get("price") or 0)
    fees = float(row.get("fees") or 0)
    amount = round(qty * price + fees, 10)
    currency = str(row.get("currency") or "USD").upper()
    cash_account = str(row.get("cash_account") or currency).upper()
    source_id = row.get("id")
    ticker = row.get("ticker")
    if direction == "out":
        txn_type = "WITHDRAW"
        rationale = (
            f"Account split: transfer funding for {ticker} to target account"
            + (f" (source txn #{source_id})" if source_id is not None else "")
        )
    else:
        txn_type = "DEPOSIT"
        rationale = (
            f"Account split: funding received for {ticker} from source account"
            + (f" (source txn #{source_id})" if source_id is not None else "")
        )
    return {
        "date": row["date"],
        "type": txn_type,
        "amount": amount,
        "currency": currency,
        "cash_account": cash_account,
        "rationale": rationale,
        "tags": ["account-split", "asset-transfer"],
    }


def build_split_plan(
    records: list[dict[str, Any]], *, market: str | None, tickers: set[str]
) -> SplitPlan:
    if not market and not tickers:
        raise ValueError("provide --market and/or --ticker")

    source_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    funding_bridges: list[dict[str, Any]] = []

    for row in records:
        clean = _clean_record(row)
        if row.get("lots"):
            clean["lots"] = row["lots"]

        if not _selected(row, market=market, tickers=tickers):
            source_records.append(clean)
            continue

        selected_rows.append(row)
        if str(row.get("type") or "").upper() == "BUY":
            source_records.append(_buy_funding_bridge(row, direction="out"))
            deposit = _buy_funding_bridge(row, direction="in")
            target_records.append(deposit)
            funding_bridges.append(deposit)
        target_records.append(clean)

    if not selected_rows:
        raise ValueError("selector matched no transactions")
    return SplitPlan(
        source_records=source_records,
        target_records=target_records,
        selected=selected_rows,
        funding_bridges=funding_bridges,
    )


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _verify_db(db_path: Path) -> list[str]:
    ok, mismatches = _verify_balance_tables(argparse.Namespace(db=db_path))
    return [] if ok else mismatches


def _materialize(db_path: Path, records: list[dict[str, Any]], source_ref: Path) -> None:
    status = db_init(db_path)
    if status not in {"created", "verified"}:
        raise RuntimeError(f"unexpected db_init status for {db_path}: {status}")
    inserted, errors = db_import_records(
        db_path,
        records,
        source="json",
        source_ref=str(source_ref),
    )
    if errors:
        raise RuntimeError("; ".join(errors))
    if inserted != len(records):
        raise RuntimeError(f"inserted {inserted} records, expected {len(records)}")


def _cash(db_path: Path) -> dict[str, float]:
    conn = db_connect(db_path)
    try:
        return {
            row["currency"]: float(row["amount"])
            for row in conn.execute("SELECT currency, amount FROM cash_balances")
        }
    finally:
        conn.close()


def _lots(db_path: Path) -> dict[tuple[str, str, str], float]:
    conn = db_connect(db_path)
    try:
        out: dict[tuple[str, str, str], float] = defaultdict(float)
        for row in conn.execute("SELECT ticker, market, currency, qty FROM open_lots"):
            key = (row["ticker"], row["market"], row["currency"])
            out[key] += float(row["qty"])
        return dict(out)
    finally:
        conn.close()


def _sum_float_dicts(*items: dict[Any, float]) -> dict[Any, float]:
    out: dict[Any, float] = defaultdict(float)
    for item in items:
        for key, value in item.items():
            out[key] += value
    return {key: value for key, value in out.items() if abs(value) > 1e-8}


def _compare_balances(
    original_db: Path, source_db: Path, target_db: Path
) -> list[str]:
    issues: list[str] = []
    original_cash = _cash(original_db)
    combined_cash = _sum_float_dicts(_cash(source_db), _cash(target_db))
    for ccy in sorted(set(original_cash) | set(combined_cash)):
        if abs(original_cash.get(ccy, 0.0) - combined_cash.get(ccy, 0.0)) > 1e-3:
            issues.append(
                f"cash {ccy}: original={original_cash.get(ccy, 0.0):g} "
                f"combined={combined_cash.get(ccy, 0.0):g}"
            )

    original_lots = _lots(original_db)
    combined_lots = _sum_float_dicts(_lots(source_db), _lots(target_db))
    for key in sorted(set(original_lots) | set(combined_lots)):
        if abs(original_lots.get(key, 0.0) - combined_lots.get(key, 0.0)) > 1e-6:
            issues.append(
                f"lot {key}: original={original_lots.get(key, 0.0):g} "
                f"combined={combined_lots.get(key, 0.0):g}"
            )
    return issues


def _resolve_source(args: argparse.Namespace) -> AccountPaths:
    if args.source_db:
        db = Path(args.source_db)
        settings = Path(args.source_settings) if args.source_settings else REPO_ROOT / "SETTINGS.example.md"
        return AccountPaths(
            name=args.source_account or "<custom>",
            settings=settings,
            db=db,
            reports_dir=db.parent / "reports",
            cache=REPO_ROOT / "market_data_cache.db",
        )
    return resolve_account(
        argparse.Namespace(
            account=args.source_account,
            db=None,
            settings=None,
        )
    )


def _target_paths(name: str) -> AccountPaths:
    validate_account_name(name, for_create=True)
    base = REPO_ROOT / "accounts" / name
    return AccountPaths(
        name=name,
        settings=base / "SETTINGS.md",
        db=base / "transactions.db",
        reports_dir=base / "reports",
        cache=REPO_ROOT / "market_data_cache.db",
    )


def run(args: argparse.Namespace) -> int:
    source = _resolve_source(args)
    target = _target_paths(args.target_account)
    run_dir = Path(args.run_dir) if args.run_dir else Path(
        tempfile.mkdtemp(prefix="asset_account_split_")
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    tickers = _parse_tickers(args.ticker)
    records = _load_records(source.db)
    plan = build_split_plan(records, market=args.market, tickers=tickers)

    source_json = run_dir / "source_rebuilt.json"
    target_json = run_dir / "target_import.json"
    summary_json = run_dir / "summary.json"
    _write_json(source_json, plan.source_records)
    _write_json(target_json, plan.target_records)

    source_tmp_db = run_dir / "source_rebuilt.db"
    target_tmp_db = run_dir / "target_import.db"
    for temp_db in (source_tmp_db, target_tmp_db):
        if temp_db.exists():
            temp_db.unlink()
    _materialize(source_tmp_db, plan.source_records, source_json)
    _materialize(target_tmp_db, plan.target_records, target_json)

    verify_issues = {
        "source": _verify_db(source_tmp_db),
        "target": _verify_db(target_tmp_db),
        "combined": _compare_balances(source.db, source_tmp_db, target_tmp_db),
    }
    selected_by_type: dict[str, int] = defaultdict(int)
    selected_tickers: set[str] = set()
    for row in plan.selected:
        selected_by_type[str(row.get("type") or "")] += 1
        if row.get("ticker"):
            selected_tickers.add(str(row["ticker"]))
    summary = {
        "run_dir": str(run_dir),
        "source_account": source.name,
        "source_db": str(source.db),
        "target_account": target.name,
        "target_db": str(target.db),
        "selector": {
            "market": args.market,
            "tickers": sorted(tickers),
        },
        "selected_transactions": len(plan.selected),
        "selected_by_type": dict(sorted(selected_by_type.items())),
        "selected_tickers": sorted(selected_tickers),
        "source_records": len(plan.source_records),
        "target_records": len(plan.target_records),
        "funding_bridges": len(plan.funding_bridges),
        "verify_issues": verify_issues,
        "applied": False,
    }

    if any(verify_issues.values()):
        _write_json(summary_json, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 4

    if args.apply:
        if args.source_db:
            raise RuntimeError("--apply is refused with --source-db; use --source-account")

        if target.db.exists():
            target_records = _load_records(target.db)
            if target_records and not args.replace_target:
                raise RuntimeError(
                    f"{target.db} already has {len(target_records)} transaction(s); "
                    "pass --replace-target only after reviewing the target account"
                )

        create_account_scaffold(target.name)
        if args.copy_settings and source.settings.exists():
            shutil.copy2(source.settings, target.settings)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = source.db.with_name(source.db.name + ".bak")
        timestamp_backup = source.db.with_name(source.db.name + f".bak.{timestamp}")
        shutil.copy2(source.db, backup)
        shutil.copy2(source.db, timestamp_backup)

        if target.db.exists():
            target_backup = target.db.with_name(target.db.name + f".bak.{timestamp}")
            shutil.copy2(target.db, target_backup)
            target.db.unlink()
        _materialize(target.db, plan.target_records, target_json)

        shutil.copy2(source_tmp_db, source.db)
        live_verify = {
            "source": _verify_db(source.db),
            "target": _verify_db(target.db),
            "combined": _compare_balances(backup, source.db, target.db),
        }
        summary["applied"] = True
        summary["backup"] = str(backup)
        summary["timestamp_backup"] = str(timestamp_backup)
        summary["live_verify_issues"] = live_verify
        if any(live_verify.values()):
            _write_json(summary_json, summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 5

    _write_json(summary_json, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Split transactions selected by market and/or ticker into a target "
            "account while preserving combined cash/open-lot balances."
        )
    )
    p.add_argument("--source-account", help="Source account name; defaults to active account")
    p.add_argument("--source-db", help="Source DB path for dry-run audits")
    p.add_argument("--source-settings", help="Settings path used with --source-db")
    p.add_argument("--target-account", required=True, help="Target account to create or replace")
    p.add_argument("--market", help="Select transactions whose market equals this value")
    p.add_argument(
        "--ticker",
        action="append",
        help="Ticker or comma-separated tickers to move; can be repeated",
    )
    p.add_argument("--run-dir", help="Directory for JSON plans and temporary DBs")
    p.add_argument("--apply", action="store_true", help="Write live account DBs after dry-run checks pass")
    p.add_argument(
        "--replace-target",
        action="store_true",
        help="Allow --apply to replace a target account DB that already has transactions",
    )
    p.add_argument(
        "--no-copy-settings",
        dest="copy_settings",
        action="store_false",
        help="Do not copy source SETTINGS.md into the target account on --apply",
    )
    p.set_defaults(copy_settings=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
