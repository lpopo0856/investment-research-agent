from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_archive import _backfill, list_archive  # noqa: E402


def test_backfill_sees_daily_and_portfolio_and_legacy_without_duplicates(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "2026-05-03_2130_single_account_daily_report.html").write_text("daily", encoding="utf-8")
    (reports / "2026-05-03_2130_single_account_portfolio_report.html").write_text("portfolio", encoding="utf-8")
    (reports / "2026-05-02_0900_portfolio_report.html").write_text("legacy", encoding="utf-8")
    (reports / "ignore.html").write_text("ignore", encoding="utf-8")
    db = tmp_path / "archive.db"

    assert _backfill(reports, db) == 3
    assert _backfill(reports, db) == 0
    ids = {row["report_id"] for row in list_archive(db, limit=10)}
    assert ids == {
        "2026-05-03_2130_single_account_daily_report",
        "2026-05-03_2130_single_account_portfolio_report",
        "2026-05-02_0900",
    }
