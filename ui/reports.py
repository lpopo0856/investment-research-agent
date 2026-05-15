"""Report discovery, parsing, and pagination for the local UI.

Every entry point that takes a user-supplied filename goes through
:func:`resolve_report_path`, which validates against :data:`REPORT_RE` and
asserts the resolved path is under the account's ``reports/`` directory.
"""

from __future__ import annotations

import math
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from ui.accounts import resolve_account_path

REPORT_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{4})_(?P<suffix>.+)_report\.html$"
)


def list_reports(account: str) -> list[dict]:
    """Enumerate HTML report files for *account*.

    Returns a list of dicts with keys ``{filename, date, time, kind}``.
    ``kind`` is ``"daily"`` when the regex ``suffix`` group contains the
    literal ``"daily"`` (case-insensitive); otherwise ``"portfolio"``.

    The list is sorted **descending** by ``(date, time)`` taken from the
    filename — not from file mtime.

    Returns ``[]`` when the ``reports/`` directory does not exist (e.g. the
    account has only a ``SETTINGS.md`` or a ledger).
    """
    account_dir = resolve_account_path(account)
    reports_dir = account_dir / "reports"
    if not reports_dir.is_dir():
        return []

    results: list[dict] = []
    for entry in reports_dir.iterdir():
        if not entry.is_file():
            continue
        m = REPORT_RE.match(entry.name)
        if m is None:
            continue
        suffix = m.group("suffix")
        kind = "daily" if "daily" in suffix.lower() else "portfolio"
        results.append(
            {
                "filename": entry.name,
                "date": m.group("date"),
                "time": m.group("time"),
                "kind": kind,
            }
        )

    results.sort(key=lambda r: (r["date"], r["time"]), reverse=True)
    return results


def paginate(items: list, page: int, size: int = 12) -> dict:
    """Return a pagination envelope for *items*.

    *page* is clamped to ``[1, total_pages]``.  When *items* is empty,
    ``total_pages`` is ``1`` and ``page`` is ``1``.
    """
    total = len(items)
    total_pages = max(1, math.ceil(total / size)) if total > 0 else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * size
    return {
        "items": items[start : start + size],
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "size": size,
    }


def clear_old_reports(account: str, *, days: int = 30, today: date | None = None) -> dict:
    """Delete report HTML files dated at least ``days`` old for *account*.

    Only files matching :data:`REPORT_RE` are eligible. The age is based on the
    report date embedded in the filename, not filesystem mtime, so cleanup is
    deterministic and matches the report list order.
    """
    if days < 1:
        raise ValueError("days must be >= 1")

    account_dir = resolve_account_path(account)
    reports_dir = account_dir / "reports"
    cutoff = (today or date.today()) - timedelta(days=days)
    deleted: list[str] = []

    if not reports_dir.is_dir():
        return {"deleted": deleted, "deleted_count": 0, "cutoff_date": cutoff.isoformat()}

    for entry in reports_dir.iterdir():
        if not entry.is_file():
            continue
        m = REPORT_RE.match(entry.name)
        if m is None:
            continue
        try:
            report_date = datetime.strptime(m.group("date"), "%Y-%m-%d").date()
        except ValueError:
            continue
        if report_date <= cutoff:
            entry.unlink()
            deleted.append(entry.name)

    deleted.sort(reverse=True)
    return {
        "deleted": deleted,
        "deleted_count": len(deleted),
        "cutoff_date": cutoff.isoformat(),
    }


def resolve_report_path(account: str, filename: str) -> Path:
    """Return the absolute path for *filename* inside *account*'s reports dir.

    Validation steps (in order):
    1. Validate *account* via :func:`ui.accounts.resolve_account_path`.
    2. Reject *filename* that does not match :data:`REPORT_RE` with
       :class:`ValueError`.
    3. Resolve ``<account_dir>/reports/<filename>`` and assert the resolved
       path is under ``reports_dir`` via ``os.path.commonpath``.
    4. Assert the file exists; raise :class:`FileNotFoundError` otherwise.
    """
    account_dir = resolve_account_path(account)
    reports_dir = (account_dir / "reports").resolve()

    if not REPORT_RE.match(filename):
        raise ValueError(f"invalid report filename: {filename!r}")

    resolved = (reports_dir / filename).resolve()

    try:
        common = os.path.commonpath([str(resolved), str(reports_dir)])
    except ValueError as exc:
        raise ValueError(f"report path escapes reports directory: {filename!r}") from exc
    if common != str(reports_dir):
        raise ValueError(f"report path escapes reports directory: {filename!r}")

    if not resolved.exists():
        raise FileNotFoundError(f"report not found: {resolved}")

    return resolved
