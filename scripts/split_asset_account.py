#!/usr/bin/env python3
"""Split a market or ticker set into a separate Markdown account ledger.

Default mode is a dry run. It writes canonical JSON plans plus temporary
Markdown ledgers, verifies generated caches, and checks combined cash/open-lot
balances against the original source ledger replay.
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
from ledger_markdown import (  # noqa: E402
    ensure_ledger_skeleton,
    events_dir,
    load_event_dicts,
)
import transactions as tx_runtime  # noqa: E402


CANONICAL_FIELDS = {
    "id",
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
    "target_event_id",
    "legacy_db_id",
    "legacy_target_id",
    "source",
    "source_ref",
    "created_at",
}


@dataclass(frozen=True)
class SplitPlan:
    source_records: list[dict[str, Any]]
    target_records: list[dict[str, Any]]
    selected: list[dict[str, Any]]
    funding_bridges: list[dict[str, Any]]


def _clean_record(row: dict[str, Any]) -> dict[str, Any]:
    clean = {k: row[k] for k in CANONICAL_FIELDS if row.get(k) is not None}
    lots = row.get("lots")
    if lots:
        clean["lots"] = lots
    return clean


def _ledger_dir_for_source_path(path: Path) -> Path:
    """Map the legacy path flag to its sibling Markdown ledger directory."""

    return path.parent / "ledger"


def _load_records(ledger_dir: Path) -> list[dict[str, Any]]:
    records = load_event_dicts(ledger_dir)
    if not records:
        raise FileNotFoundError(f"no Markdown events found under {ledger_dir}")
    return records


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
            + (f" (source event {source_id})" if source_id is not None else "")
        )
    else:
        txn_type = "DEPOSIT"
        rationale = (
            f"Account split: funding received for {ticker} from source account"
            + (f" (source event {source_id})" if source_id is not None else "")
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


def _materialize_ledger(ledger_dir: Path, records: list[dict[str, Any]], source_ref: Path) -> None:
    if ledger_dir.exists():
        shutil.rmtree(ledger_dir)
    ensure_ledger_skeleton(ledger_dir)
    inserted, errors = tx_runtime.ledger_import_records(
        ledger_dir,
        records,
        source="asset-split-json",
        source_ref=str(source_ref),
    )
    if errors:
        raise RuntimeError("; ".join(errors))
    if inserted != len(records):
        raise RuntimeError(f"inserted {inserted} records, expected {len(records)}")


def _verify_ledger(ledger_dir: Path) -> list[str]:
    ok, issues = tx_runtime.ledger_verify_cache(ledger_dir)
    return [] if ok else issues


def _state_from_ledger(ledger_dir: Path) -> Any:
    events = load_event_dicts(ledger_dir)
    txns = [tx_runtime._dict_to_transaction(event, seq=i) for i, event in enumerate(events)]
    return tx_runtime.replay(txns)


def _cash(ledger_dir: Path) -> dict[str, float]:
    state = _state_from_ledger(ledger_dir)
    return {ccy: float(amount) for ccy, amount in state.cash.items() if abs(amount) > 1e-9}


def _lots(ledger_dir: Path) -> dict[tuple[str, str, str], float]:
    state = _state_from_ledger(ledger_dir)
    out: dict[tuple[str, str, str], float] = defaultdict(float)
    for ticker, lots in state.open_lots.items():
        for lot in lots:
            key = (ticker, lot.market, lot.currency)
            out[key] += float(lot.qty)
    return {key: value for key, value in out.items() if abs(value) > 1e-9}


def _sum_float_dicts(*items: dict[Any, float]) -> dict[Any, float]:
    out: dict[Any, float] = defaultdict(float)
    for item in items:
        for key, value in item.items():
            out[key] += value
    return {key: value for key, value in out.items() if abs(value) > 1e-8}


def _compare_balances(
    original_ledger: Path, source_ledger: Path, target_ledger: Path
) -> list[str]:
    issues: list[str] = []
    original_cash = _cash(original_ledger)
    combined_cash = _sum_float_dicts(_cash(source_ledger), _cash(target_ledger))
    for ccy in sorted(set(original_cash) | set(combined_cash)):
        if abs(original_cash.get(ccy, 0.0) - combined_cash.get(ccy, 0.0)) > 1e-3:
            issues.append(
                f"cash {ccy}: original={original_cash.get(ccy, 0.0):g} "
                f"combined={combined_cash.get(ccy, 0.0):g}"
            )

    original_lots = _lots(original_ledger)
    combined_lots = _sum_float_dicts(_lots(source_ledger), _lots(target_ledger))
    for key in sorted(set(original_lots) | set(combined_lots)):
        if abs(original_lots.get(key, 0.0) - combined_lots.get(key, 0.0)) > 1e-6:
            issues.append(
                f"lot {key}: original={original_lots.get(key, 0.0):g} "
                f"combined={combined_lots.get(key, 0.0):g}"
            )
    return issues


def _resolve_source(args: argparse.Namespace) -> AccountPaths:
    if args.source_db:
        legacy_path = Path(args.source_db)
        settings = Path(args.source_settings) if args.source_settings else REPO_ROOT / "SETTINGS.example.md"
        return AccountPaths(
            name=args.source_account or "<custom>",
            settings=settings,
            db=legacy_path,
            ledger=_ledger_dir_for_source_path(legacy_path),
            reports_dir=legacy_path.parent / "reports",
            cache=REPO_ROOT / "market_data_cache.json",
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
        db=base / ("transactions" + ".db"),
        ledger=base / "ledger",
        reports_dir=base / "reports",
        cache=REPO_ROOT / "market_data_cache.json",
    )


def _ledger_has_events(ledger_dir: Path) -> bool:
    return events_dir(ledger_dir).exists() and any(events_dir(ledger_dir).glob("**/*.md"))


def _replace_live_ledger(live: Path, staged: Path, *, timestamp: str) -> Path | None:
    backup: Path | None = None
    if live.exists():
        backup = live.with_name(live.name + f".bak.{timestamp}")
        if backup.exists():
            raise RuntimeError(f"backup path already exists: {backup}")
        shutil.copytree(live, backup)
        shutil.rmtree(live)
    shutil.copytree(staged, live)
    tx_runtime.ledger_rebuild_cache(live)
    return backup


def run(args: argparse.Namespace) -> int:
    source = _resolve_source(args)
    target = _target_paths(args.target_account)
    run_dir = Path(args.run_dir) if args.run_dir else Path(
        tempfile.mkdtemp(prefix="asset_account_split_")
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    tickers = _parse_tickers(args.ticker)
    records = _load_records(source.ledger)
    plan = build_split_plan(records, market=args.market, tickers=tickers)

    source_json = run_dir / "source_rebuilt.json"
    target_json = run_dir / "target_import.json"
    summary_json = run_dir / "summary.json"
    _write_json(source_json, plan.source_records)
    _write_json(target_json, plan.target_records)

    source_tmp_ledger = run_dir / "source_rebuilt_ledger"
    target_tmp_ledger = run_dir / "target_import_ledger"
    _materialize_ledger(source_tmp_ledger, plan.source_records, source_json)
    _materialize_ledger(target_tmp_ledger, plan.target_records, target_json)

    verify_issues = {
        "source": _verify_ledger(source_tmp_ledger),
        "target": _verify_ledger(target_tmp_ledger),
        "combined": _compare_balances(source.ledger, source_tmp_ledger, target_tmp_ledger),
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
        "source_ledger": str(source.ledger),
        "target_account": target.name,
        "target_ledger": str(target.ledger),
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

        if _ledger_has_events(target.ledger) and not args.replace_target:
            target_records = _load_records(target.ledger)
            raise RuntimeError(
                f"{target.ledger} already has {len(target_records)} event(s); "
                "pass --replace-target only after reviewing the target account"
            )

        create_account_scaffold(target.name)
        if args.copy_settings and source.settings.exists():
            shutil.copy2(source.settings, target.settings)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        source_backup = _replace_live_ledger(source.ledger, source_tmp_ledger, timestamp=timestamp)
        target_backup = _replace_live_ledger(target.ledger, target_tmp_ledger, timestamp=timestamp)

        live_verify = {
            "source": _verify_ledger(source.ledger),
            "target": _verify_ledger(target.ledger),
            "combined": _compare_balances(
                source_backup if source_backup is not None else source.ledger,
                source.ledger,
                target.ledger,
            ),
        }
        summary["applied"] = True
        summary["source_backup"] = str(source_backup) if source_backup else None
        summary["target_backup"] = str(target_backup) if target_backup else None
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
    p.add_argument("--source-db", help="Legacy path override used only to locate sibling ledger")
    p.add_argument("--source-settings", help="Settings path used with --source-db")
    p.add_argument("--target-account", required=True, help="Target account to create or replace")
    p.add_argument("--market", help="Select transactions whose market equals this value")
    p.add_argument(
        "--ticker",
        action="append",
        help="Ticker or comma-separated tickers to move; can be repeated",
    )
    p.add_argument("--run-dir", help="Directory for JSON plans and temporary Markdown ledgers")
    p.add_argument("--apply", action="store_true", help="Write live account ledgers after dry-run checks pass")
    p.add_argument(
        "--replace-target",
        action="store_true",
        help="Allow --apply to replace a target account ledger that already has events",
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
