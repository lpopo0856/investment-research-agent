"""Persist each rendered report's snapshot + editorial context to transactions.db.

Without this layer, the per-run editorial knowledge (news researched via
WebSearch, 30-day events, alerts, recommendations, trading psychology, snapshot
totals) lives only inside the rendered HTML and is unrecoverable for diffing,
dedup, or accuracy scoring. This module adds a single `report_archive` table
inside the existing transactions.db so the pipeline ends with a queryable
artifact rather than a write-only HTML file.

Public API:
    ensure_schema(db_path)         -> creates / verifies the table
    archive_report(...)            -> upserts one row from snapshot+context paths
    read_archive(report_id, db)    -> dict | None
    list_archive(db, limit)        -> list[dict] (recent first)

CLI:
    python scripts/report_archive.py archive \\
        --report-id 2026-05-01_2052 \\
        --snapshot /tmp/report_snapshot.json \\
        --context /tmp/report_context.json \\
        --html reports/2026-05-01_2052_portfolio_report.html

    python scripts/report_archive.py list [--limit N]
    python scripts/report_archive.py show <report_id>
    python scripts/report_archive.py backfill        # registers HTML files in reports/
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ARCHIVE_SCHEMA_VERSION = 1
DEFAULT_DB_PATH = Path("transactions.db")
REPORT_ID_RE = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{4})")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS report_archive (
  report_id              TEXT PRIMARY KEY,
  generated_at           TEXT NOT NULL,
  today                  TEXT,
  base_currency          TEXT,
  holdings_count         INTEGER,
  news_count             INTEGER,
  events_count           INTEGER,
  alerts_count           INTEGER,
  recommendations_count  INTEGER,
  html_path              TEXT,
  snapshot_json          TEXT,
  context_json           TEXT,
  archived_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_report_archive_today ON report_archive(today);
"""


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the report_archive table + version row. Idempotent."""
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
            ("report_archive_version", str(ARCHIVE_SCHEMA_VERSION)),
        )
        conn.commit()
    finally:
        conn.close()


def _read_json(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logging.warning("report_archive: cannot parse %s: %s", path, exc)
        return None


def _safe_len(value: Any) -> Optional[int]:
    if isinstance(value, list):
        return len(value)
    return None


def _derive_counts(snapshot: Optional[Dict[str, Any]],
                   context: Optional[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    holdings = None
    if snapshot:
        holdings = _safe_len(snapshot.get("aggregates"))
    counts = {"holdings_count": holdings,
              "news_count": None,
              "events_count": None,
              "alerts_count": None,
              "recommendations_count": None}
    if not context:
        return counts
    counts["news_count"] = _safe_len(context.get("news"))
    counts["events_count"] = _safe_len(context.get("events"))
    counts["alerts_count"] = _safe_len(context.get("alerts"))
    counts["recommendations_count"] = _safe_len(context.get("recommendations"))
    return counts


def archive_report(report_id: str,
                   snapshot_path: Optional[Path],
                   context_path: Optional[Path],
                   html_path: Optional[Path],
                   db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Upsert one report into report_archive. Returns the stored row as dict.

    Missing inputs are tolerated — the row is still written with whatever is
    available (useful for backfilling old reports where the JSONs are gone).
    """
    ensure_schema(db_path)
    snapshot = _read_json(snapshot_path)
    context = _read_json(context_path)

    counts = _derive_counts(snapshot, context)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, default=str) if snapshot else None
    context_json = json.dumps(context, ensure_ascii=False, default=str) if context else None
    generated_at = (snapshot or {}).get("generated_at") or _now_iso()
    today = (snapshot or {}).get("today")
    base_ccy = (snapshot or {}).get("base_currency")
    html_str = str(html_path) if html_path else None

    row = {
        "report_id": report_id,
        "generated_at": generated_at,
        "today": today,
        "base_currency": base_ccy,
        **counts,
        "html_path": html_str,
        "snapshot_json": snapshot_json,
        "context_json": context_json,
        "archived_at": _now_iso(),
    }
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT INTO report_archive
                 (report_id, generated_at, today, base_currency,
                  holdings_count, news_count, events_count,
                  alerts_count, recommendations_count,
                  html_path, snapshot_json, context_json, archived_at)
               VALUES
                 (:report_id, :generated_at, :today, :base_currency,
                  :holdings_count, :news_count, :events_count,
                  :alerts_count, :recommendations_count,
                  :html_path, :snapshot_json, :context_json, :archived_at)
               ON CONFLICT(report_id) DO UPDATE SET
                  generated_at          = excluded.generated_at,
                  today                 = excluded.today,
                  base_currency         = excluded.base_currency,
                  holdings_count        = excluded.holdings_count,
                  news_count            = excluded.news_count,
                  events_count          = excluded.events_count,
                  alerts_count          = excluded.alerts_count,
                  recommendations_count = excluded.recommendations_count,
                  html_path             = excluded.html_path,
                  snapshot_json         = COALESCE(excluded.snapshot_json, report_archive.snapshot_json),
                  context_json          = COALESCE(excluded.context_json,  report_archive.context_json),
                  archived_at           = excluded.archived_at
            """,
            row,
        )
        conn.commit()
    finally:
        conn.close()
    return row


def read_archive(report_id: str,
                 db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "SELECT * FROM report_archive WHERE report_id = ?", (report_id,)
        )
        r = cur.fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def list_archive(db_path: Path = DEFAULT_DB_PATH,
                 limit: int = 20) -> List[Dict[str, Any]]:
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """SELECT report_id, generated_at, today, base_currency,
                      holdings_count, news_count, events_count,
                      alerts_count, recommendations_count, html_path
               FROM report_archive
               ORDER BY report_id DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _report_id_from_path(p: Path) -> Optional[str]:
    m = REPORT_ID_RE.search(p.name)
    return m.group(1) if m else None


def _backfill(reports_dir: Path, db_path: Path) -> int:
    """Register every reports/*.html that has no row yet. JSON blobs stay NULL
    when the source files are gone — only html_path + report_id get persisted.
    """
    n = 0
    for html in sorted(reports_dir.glob("*_portfolio_report.html")):
        rid = _report_id_from_path(html)
        if not rid:
            continue
        if read_archive(rid, db_path):
            continue
        archive_report(rid, snapshot_path=None, context_path=None,
                       html_path=html, db_path=db_path)
        n += 1
    return n


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("archive", help="Insert/update one report row")
    pa.add_argument("--report-id", required=True)
    pa.add_argument("--snapshot", type=Path)
    pa.add_argument("--context", type=Path)
    pa.add_argument("--html", type=Path)

    pl = sub.add_parser("list", help="Recent reports")
    pl.add_argument("--limit", type=int, default=20)

    ps = sub.add_parser("show", help="Print the stored row")
    ps.add_argument("report_id")

    pb = sub.add_parser("backfill", help="Register HTML files under reports/")
    pb.add_argument("--reports-dir", type=Path, default=Path("reports"))

    args = p.parse_args(argv)
    if args.cmd == "archive":
        row = archive_report(args.report_id, args.snapshot, args.context,
                             args.html, args.db)
        print(f"archived {row['report_id']} "
              f"(holdings={row['holdings_count']}, news={row['news_count']}, "
              f"events={row['events_count']})")
        return 0
    if args.cmd == "list":
        rows = list_archive(args.db, limit=args.limit)
        if not rows:
            print("(empty)")
            return 0
        cols = ["report_id", "today", "holdings_count", "news_count",
                "events_count", "alerts_count", "recommendations_count"]
        print("\t".join(cols))
        for r in rows:
            print("\t".join(str(r.get(c) if r.get(c) is not None else "-")
                            for c in cols))
        return 0
    if args.cmd == "show":
        row = read_archive(args.report_id, args.db)
        if not row:
            print(f"no row for {args.report_id}", file=sys.stderr)
            return 1
        print(json.dumps(row, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.cmd == "backfill":
        n = _backfill(args.reports_dir, args.db)
        print(f"backfilled {n} report(s) from {args.reports_dir}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
