"""Persist rendered report snapshots and editorial context as durable JSON files.

Final ledger architecture stores report archive records under
``ledger/archive/reports/<report_id>.json``.  The generated
``ledger/generated/report_archive_index.json`` is rebuildable and never
canonical.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from account import add_account_args, resolve_account, autodetect_and_migrate_or_exit  # noqa: E402

DEFAULT_DB_PATH = Path("ledger")
STORE_AUTO = "auto"
STORE_FILE = "file"
STORE_MARKDOWN = "markdown"
FILE_STORE_CHOICES = (STORE_AUTO, STORE_MARKDOWN, STORE_FILE)
FILE_STORE_ALIASES = {STORE_AUTO, STORE_MARKDOWN, STORE_FILE}
REPORT_ARCHIVE_INDEX_NAME = "report_archive_index.json"
DO_NOT_EDIT_NOTICE = "DO_NOT_EDIT: generated from durable report archive records; rebuild with tooling."
REPORT_ID_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}_\d{4}_(?:single_account|total_account)_(?:daily_report|portfolio_report))"
)
LEGACY_REPORT_ID_RE = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{4})")


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_store(_db_path: Path, _store: str) -> str:
    return STORE_MARKDOWN


def _ledger_dir_for_db(db_path: Path) -> Path:
    if db_path.name == "ledger":
        return db_path
    return db_path.parent / "ledger"


def _archive_records_dir(db_path: Path) -> Path:
    return _ledger_dir_for_db(db_path) / "archive" / "reports"


def _archive_index_path(db_path: Path) -> Path:
    return _ledger_dir_for_db(db_path) / "generated" / REPORT_ARCHIVE_INDEX_NAME


def _record_path(report_id: str, db_path: Path) -> Path:
    if "/" in report_id or "\\" in report_id or report_id in {"", ".", ".."}:
        raise ValueError(f"invalid report_id for file archive: {report_id!r}")
    return _archive_records_dir(db_path) / f"{report_id}.json"


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _archive_list_row(row: Dict[str, Any]) -> Dict[str, Any]:
    cols = [
        "report_id", "generated_at", "today", "base_currency",
        "holdings_count", "news_count", "events_count", "alerts_count",
        "recommendations_count", "html_path",
    ]
    return {c: row.get(c) for c in cols}


def ensure_schema(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Compatibility no-op: file archives need only their parent folders."""
    _archive_records_dir(db_path).mkdir(parents=True, exist_ok=True)
    _archive_index_path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _read_json(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logging.warning("report_archive: cannot parse %s: %s", path, exc)
        return None


def _safe_len(value: Any) -> Optional[int]:
    return len(value) if isinstance(value, list) else None


def _derive_counts(snapshot: Optional[Dict[str, Any]],
                   context: Optional[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    counts = {
        "holdings_count": _safe_len((snapshot or {}).get("aggregates")),
        "news_count": None,
        "events_count": None,
        "alerts_count": None,
        "recommendations_count": None,
    }
    if context:
        counts["news_count"] = _safe_len(context.get("news"))
        counts["events_count"] = _safe_len(context.get("events"))
        counts["alerts_count"] = _safe_len(context.get("alerts"))
        counts["recommendations_count"] = _safe_len(context.get("recommendations"))
    return counts


def archive_report(report_id: str,
                   snapshot_path: Optional[Path],
                   context_path: Optional[Path],
                   html_path: Optional[Path],
                   db_path: Path = DEFAULT_DB_PATH,
                   store: str = STORE_AUTO) -> Dict[str, Any]:
    """Upsert one report archive record into durable file storage."""
    _normalize_store(db_path, store)
    snapshot = _read_json(snapshot_path)
    context = _read_json(context_path)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, default=str) if snapshot else None
    context_json = json.dumps(context, ensure_ascii=False, default=str) if context else None
    existing = read_archive(report_id, db_path, store=store)
    row = {
        "report_id": report_id,
        "generated_at": (snapshot or {}).get("generated_at") or _now_iso(),
        "today": (snapshot or {}).get("today"),
        "base_currency": (snapshot or {}).get("base_currency"),
        **_derive_counts(snapshot, context),
        "html_path": str(html_path) if html_path else None,
        "snapshot_json": snapshot_json if snapshot_json is not None else (existing or {}).get("snapshot_json"),
        "context_json": context_json if context_json is not None else (existing or {}).get("context_json"),
        "archived_at": _now_iso(),
    }
    _atomic_write_json(_record_path(report_id, db_path), row)
    rebuild_archive_index(db_path)
    return row


def read_archive(report_id: str,
                 db_path: Path = DEFAULT_DB_PATH,
                 store: str = STORE_AUTO) -> Optional[Dict[str, Any]]:
    _normalize_store(db_path, store)
    path = _record_path(report_id, db_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logging.warning("report_archive: cannot parse %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def rebuild_archive_index(db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Rebuild the generated report archive index from durable JSON records."""
    rows: List[Dict[str, Any]] = []
    records_dir = _archive_records_dir(db_path)
    if records_dir.is_dir():
        for path in sorted(records_dir.glob("*.json")):
            data = _read_json(path)
            if isinstance(data, dict) and data.get("report_id"):
                rows.append(_archive_list_row(data))
    rows.sort(key=lambda row: str(row.get("report_id") or ""), reverse=True)
    generated_at = _now_iso()
    index = {
        "_meta": {
            "schema": "report-archive-index/v1",
            "notice": DO_NOT_EDIT_NOTICE,
            "source": "ledger/archive/reports",
            "generated_at": generated_at,
        },
        "generated_at": generated_at,
        "source": "ledger/archive/reports",
        "reports": rows,
    }
    _atomic_write_json(_archive_index_path(db_path), index)
    return index


def list_archive(db_path: Path = DEFAULT_DB_PATH,
                 limit: int = 20,
                 store: str = STORE_AUTO) -> List[Dict[str, Any]]:
    _normalize_store(db_path, store)
    return rebuild_archive_index(db_path)["reports"][:limit]


def _report_id_from_path(path: Path) -> Optional[str]:
    match = REPORT_ID_RE.search(path.name)
    if match:
        return match.group(1)
    legacy = LEGACY_REPORT_ID_RE.search(path.name)
    return legacy.group(1) if legacy else None


def backfill_from_db(db_path: Path = DEFAULT_DB_PATH, *, dry_run: bool = False, store: str = STORE_MARKDOWN) -> int:
    """Compatibility stub: legacy archive row import is handled by migration evidence."""
    _normalize_store(db_path, store)
    return 0


def _backfill(reports_dir: Path,
              db_path: Path,
              *,
              store: str = STORE_AUTO,
              dry_run: bool = False) -> int:
    _normalize_store(db_path, store)
    count = 0
    patterns = ("*_daily_report.html", "*_portfolio_report.html")
    for html in sorted({item for pattern in patterns for item in reports_dir.glob(pattern)}):
        report_id = _report_id_from_path(html)
        if not report_id or read_archive(report_id, db_path, store=store):
            continue
        count += 1
        if not dry_run:
            archive_report(report_id, None, None, html, db_path, store=store)
    return count


def _resolve_db_path(args: argparse.Namespace) -> Path:
    if getattr(args, "db", None) is not None:
        return Path(args.db)
    try:
        return resolve_account(args).db
    except Exception:
        return DEFAULT_DB_PATH


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, type=Path, help="legacy path override used only to locate account ledger")
    parser.add_argument("--store", choices=FILE_STORE_CHOICES, default=STORE_AUTO)
    add_account_args(parser)
    sub = parser.add_subparsers(dest="cmd", required=True)

    archive = sub.add_parser("archive", help="archive one rendered report")
    archive.add_argument("--report-id", required=True)
    archive.add_argument("--snapshot", type=Path)
    archive.add_argument("--context", type=Path)
    archive.add_argument("--html", type=Path)

    listing = sub.add_parser("list", help="list archived reports")
    listing.add_argument("--limit", type=int, default=20)

    show = sub.add_parser("show", help="show one archived report")
    show.add_argument("report_id")

    backfill = sub.add_parser("backfill", help="register existing rendered report files")
    backfill.add_argument("--reports-dir", type=Path, default=Path("reports"))
    backfill.add_argument("--dry-run", action="store_true")
    backfill.add_argument("--from-db", action="store_true", help="compatibility no-op")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    autodetect_and_migrate_or_exit()
    args = _build_parser().parse_args(argv)
    db_path = _resolve_db_path(args)
    if args.cmd == "archive":
        row = archive_report(args.report_id, args.snapshot, args.context, args.html, db_path, store=args.store)
        print(json.dumps(row, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.cmd == "list":
        print(json.dumps(list_archive(db_path, args.limit, store=args.store), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.cmd == "show":
        row = read_archive(args.report_id, db_path, store=args.store)
        if not row:
            print("not found", file=sys.stderr)
            return 1
        print(json.dumps(row, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.cmd == "backfill":
        count = backfill_from_db(db_path, dry_run=args.dry_run, store=args.store) if args.from_db else _backfill(
            args.reports_dir, db_path, store=args.store, dry_run=args.dry_run
        )
        print(json.dumps({"count": count, "dry_run": args.dry_run}, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
