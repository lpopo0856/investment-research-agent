from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_archive import (  # noqa: E402
    _backfill,
    archive_report,
    backfill_from_db,
    list_archive,
    read_archive,
    rebuild_archive_index,
)


def test_backfill_sees_daily_and_portfolio_and_legacy_without_duplicates(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "2026-05-03_2130_single_account_daily_report.html").write_text("daily", encoding="utf-8")
    (reports / "2026-05-03_2130_single_account_portfolio_report.html").write_text("portfolio", encoding="utf-8")
    (reports / "2026-05-02_0900_portfolio_report.html").write_text("legacy", encoding="utf-8")
    (reports / "ignore.html").write_text("ignore", encoding="utf-8")
    ledger = tmp_path / "accounts" / "default" / "ledger"

    assert _backfill(reports, ledger) == 3
    assert _backfill(reports, ledger) == 0
    ids = {row["report_id"] for row in list_archive(ledger, limit=10)}
    assert ids == {
        "2026-05-03_2130_single_account_daily_report",
        "2026-05-03_2130_single_account_portfolio_report",
        "2026-05-02_0900",
    }


def test_file_store_writes_durable_records_and_rebuildable_index(tmp_path: Path):
    snapshot = tmp_path / "snapshot.json"
    context = tmp_path / "context.json"
    html = tmp_path / "reports" / "2026-05-03_2130_single_account_daily_report.html"
    html.parent.mkdir()
    html.write_text("html", encoding="utf-8")
    snapshot.write_text(
        json.dumps({
            "generated_at": "2026-05-03T21:30:00Z",
            "today": "2026-05-03",
            "base_currency": "USD",
            "aggregates": [{"ticker": "AAPL"}, {"ticker": "MSFT"}],
        }),
        encoding="utf-8",
    )
    context.write_text(
        json.dumps({
            "news": [{"title": "n"}],
            "events": [{"name": "e"}],
            "alerts": [{"name": "a"}],
            "recommendations": [{"name": "r"}],
        }),
        encoding="utf-8",
    )
    ledger = tmp_path / "accounts" / "default" / "ledger"
    legacy_path = tmp_path / "accounts" / "default" / ("transactions" + ".db")

    row = archive_report(
        "2026-05-03_2130_single_account_daily_report",
        snapshot,
        context,
        html,
        ledger,
        store="markdown",
    )

    record = ledger / "archive" / "reports" / "2026-05-03_2130_single_account_daily_report.json"
    index = ledger / "generated" / "report_archive_index.json"
    assert record.exists()
    assert index.exists()
    assert "DO_NOT_EDIT" in index.read_text(encoding="utf-8")
    assert not legacy_path.exists(), "file-backed archive must not create or mutate legacy DB evidence"
    assert row["holdings_count"] == 2
    assert row["news_count"] == 1
    assert read_archive(row["report_id"], ledger, store="markdown")["context_json"] is not None

    index.unlink()
    listed = list_archive(ledger, limit=10, store="markdown")
    assert [r["report_id"] for r in listed] == ["2026-05-03_2130_single_account_daily_report"]
    assert index.exists()
    rebuilt = rebuild_archive_index(ledger)
    assert rebuilt["reports"] == listed


def test_legacy_row_backfill_stub_is_non_destructive(tmp_path: Path):
    ledger = tmp_path / "accounts" / "default" / "ledger"
    assert backfill_from_db(ledger, dry_run=True, store="markdown") == 0
    assert not (ledger / "archive" / "reports").exists()
    assert backfill_from_db(ledger, store="markdown") == 0
    assert not (ledger / "archive" / "reports").exists()
