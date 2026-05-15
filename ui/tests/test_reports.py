"""Tests for ui.reports — regex, listing, pagination, path safety."""

import pytest

from ui.reports import REPORT_RE, list_reports, paginate, resolve_report_path


# ---------------------------------------------------------------------------
# REPORT_RE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", [
    "2026-04-28_2046_portfolio_report.html",
    "2026-05-03_0900_single_account_daily_report.html",
])
def test_report_re_accepts(filename):
    assert REPORT_RE.match(filename) is not None


@pytest.mark.parametrize("filename", [
    "evil.html",
    "..html",
    "2026-04-28_2046_X.html",      # missing _report.html suffix
    "../passwd",
])
def test_report_re_rejects(filename):
    assert REPORT_RE.match(filename) is None


# ---------------------------------------------------------------------------
# list_reports
# ---------------------------------------------------------------------------

def test_list_reports_default_returns_entries():
    reports = list_reports("default")
    assert len(reports) >= 1
    # Each entry has the expected keys
    for r in reports:
        assert "filename" in r
        assert "date" in r
        assert "time" in r
        assert "kind" in r


def test_list_reports_default_descending_order():
    reports = list_reports("default")
    keys = [(r["date"], r["time"]) for r in reports]
    assert keys == sorted(keys, reverse=True), "reports must be sorted descending by (date, time)"


def test_list_reports_total_does_not_crash():
    reports = list_reports("_total")
    assert isinstance(reports, list)


# ---------------------------------------------------------------------------
# paginate
# ---------------------------------------------------------------------------

def test_paginate_empty():
    result = paginate([], 1, size=12)
    assert result == {"items": [], "page": 1, "total_pages": 1, "total": 0, "size": 12}


def test_paginate_clamped_last_page():
    items = list(range(25))
    result = paginate(items, 3, size=10)
    assert result["page"] == 3
    assert result["items"] == [20, 21, 22, 23, 24]
    assert result["total_pages"] == 3
    assert result["total"] == 25
    assert result["size"] == 10


def test_paginate_clamps_beyond_max():
    items = list(range(10))
    result = paginate(items, 99, size=10)
    assert result["page"] == 1
    assert result["total_pages"] == 1


def test_paginate_clamps_below_min():
    items = list(range(10))
    result = paginate(items, 0, size=10)
    assert result["page"] == 1


# ---------------------------------------------------------------------------
# resolve_report_path
# ---------------------------------------------------------------------------

def test_resolve_report_path_traversal_raises():
    with pytest.raises(ValueError):
        resolve_report_path("default", "../../../etc/passwd")


def test_resolve_report_path_invalid_name_raises():
    with pytest.raises(ValueError):
        resolve_report_path("default", "evil.html")


def test_resolve_report_path_valid_existing():
    # 2026-04-28_2046_portfolio_report.html is known to exist in accounts/default/reports/
    path = resolve_report_path("default", "2026-04-28_2046_portfolio_report.html")
    assert path.exists()
    assert path.name == "2026-04-28_2046_portfolio_report.html"


def test_clear_old_reports_deletes_only_matching_old_files(tmp_path, monkeypatch):
    import ui.accounts as ui_accounts
    import ui.reports as ui_reports
    from datetime import date

    account_dir = tmp_path / "accounts" / "fixture"
    reports_dir = account_dir / "reports"
    reports_dir.mkdir(parents=True)
    old = reports_dir / "2026-04-01_0900_daily_report.html"
    cutoff = reports_dir / "2026-04-15_0900_portfolio_report.html"
    new = reports_dir / "2026-04-16_0900_portfolio_report.html"
    ignored = reports_dir / "_sample_redesign.html"
    for path in (old, cutoff, new, ignored):
        path.write_text(path.name, encoding="utf-8")

    monkeypatch.setattr(ui_accounts, "ACCOUNTS_ROOT", (tmp_path / "accounts").resolve())
    result = ui_reports.clear_old_reports("fixture", days=30, today=date(2026, 5, 15))

    assert result["deleted_count"] == 2
    assert result["cutoff_date"] == "2026-04-15"
    assert set(result["deleted"]) == {old.name, cutoff.name}
    assert not old.exists()
    assert not cutoff.exists()
    assert new.exists()
    assert ignored.exists()


def test_clear_old_reports_rejects_invalid_days():
    from ui.reports import clear_old_reports

    with pytest.raises(ValueError):
        clear_old_reports("default", days=0)
