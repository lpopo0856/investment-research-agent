"""Tests for ui.app FastAPI routes — no live server, asyncio.run shim."""

import asyncio
import sys
import time
from pathlib import Path

import httpx
from httpx import ASGITransport

from ui.app import app

SCRIPTS_DIR = str((Path(__file__).resolve().parents[2] / "scripts").resolve())
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from transactions import load_transactions_markdown, replay  # noqa: E402


def _run(coro):
    """Synchronous shim so tests need no pytest-asyncio dependency."""
    return asyncio.run(coro)


def _write_example_settings(root: Path):
    (root / "SETTINGS.example.md").write_text(
        "# Settings (Example)\n\n"
        "## Account description (optional)\n\n"
        "- Description: Example account\n\n"
        "## Language\n\n"
        "- traditional chinese\n",
        encoding="utf-8",
    )


def _patch_account_roots(monkeypatch, root: Path):
    import scripts.account as script_account
    import ui.accounts as ui_accounts

    monkeypatch.setattr(script_account, "REPO_ROOT", root)
    monkeypatch.setattr(script_account, "ACCOUNTS_DIR", root / "accounts")
    monkeypatch.setattr(script_account, "ACTIVE_POINTER", root / "accounts" / ".active")
    monkeypatch.setattr(ui_accounts, "REPO_ROOT", root)
    monkeypatch.setattr(ui_accounts, "ACCOUNTS_ROOT", (root / "accounts").resolve())


def _make_account(root: Path, name: str):
    base = root / "accounts" / name
    (base / "ledger" / "events").mkdir(parents=True, exist_ok=True)
    (base / "reports").mkdir(parents=True, exist_ok=True)
    (base / "SETTINGS.md").write_text(
        "# Settings\n\n## Account description (optional)\n\n"
        f"- Description: {name} account\n",
        encoding="utf-8",
    )
    return base


# ---------------------------------------------------------------------------
# Terminal cleanup must not block the event loop during agent switch
# ---------------------------------------------------------------------------

def test_close_terminal_session_times_out_without_blocking_event_loop():
    from ui.app import _close_terminal_session  # noqa: WPS433

    class SlowSession:
        def close(self):
            time.sleep(0.2)

    async def _test():
        start = time.monotonic()
        await _close_terminal_session(SlowSession(), timeout_s=0.01)
        assert time.monotonic() - start < 0.1

    _run(_test())


# ---------------------------------------------------------------------------
# GET /api/accounts
# ---------------------------------------------------------------------------

def test_get_accounts_200():
    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/accounts")
        assert resp.status_code == 200
        body = resp.json()
        assert "accounts" in body
        assert "default" in body["accounts"]

    _run(_test())


def test_post_account_creates_onboarding_scaffold_and_sets_active(tmp_path, monkeypatch):
    _patch_account_roots(monkeypatch, tmp_path)
    _write_example_settings(tmp_path)

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/accounts",
                json={"name": "newacct", "set_active": True},
            )
            listing = await client.get("/api/accounts")
        assert resp.status_code == 201
        body = resp.json()
        assert body["account"] == "newacct"
        assert body["onboarding"] == "settings_draft"
        assert (tmp_path / "accounts" / "newacct" / "SETTINGS.md").is_file()
        assert (tmp_path / "accounts" / "newacct" / "ledger" / "events").is_dir()
        assert (tmp_path / "accounts" / ".active").read_text(encoding="utf-8").strip() == "newacct"
        assert listing.json()["active"] == "newacct"

    _run(_test())


def test_post_account_rejects_total_aggregate(tmp_path, monkeypatch):
    _patch_account_roots(monkeypatch, tmp_path)
    _write_example_settings(tmp_path)

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/accounts", json={"name": "_total"})
        assert resp.status_code == 400
        assert "read-only aggregate" in resp.json()["error"]

    _run(_test())


def test_get_accounts_does_not_default_to_total_only(tmp_path, monkeypatch):
    _patch_account_roots(monkeypatch, tmp_path)
    (tmp_path / "accounts" / "_total" / "reports").mkdir(parents=True)

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/accounts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["accounts"] == ["_total"]
        assert body["default"] is None
        assert body["active"] is None

    _run(_test())


def test_patch_account_renames_directory_and_active_pointer(tmp_path, monkeypatch):
    _patch_account_roots(monkeypatch, tmp_path)
    _write_example_settings(tmp_path)
    _make_account(tmp_path, "oldacct")
    (tmp_path / "accounts" / ".active").write_text("oldacct\n", encoding="utf-8")

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch("/api/accounts/oldacct", json={"name": "newacct"})
        assert resp.status_code == 200
        assert resp.json()["active"] is True
        assert not (tmp_path / "accounts" / "oldacct").exists()
        assert (tmp_path / "accounts" / "newacct" / "SETTINGS.md").is_file()
        assert (tmp_path / "accounts" / ".active").read_text(encoding="utf-8").strip() == "newacct"

    _run(_test())


def test_delete_account_archives_without_deleting_payload(tmp_path, monkeypatch):
    _patch_account_roots(monkeypatch, tmp_path)
    _write_example_settings(tmp_path)
    _make_account(tmp_path, "keepacct")
    _make_account(tmp_path, "oldacct")
    (tmp_path / "accounts" / ".active").write_text("keepacct\n", encoding="utf-8")

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/accounts/oldacct")
            listing = await client.get("/api/accounts")
        assert resp.status_code == 200
        body = resp.json()
        archive_path = Path(body["archive_path"])
        assert body["archived"] is True
        assert not (tmp_path / "accounts" / "oldacct").exists()
        assert (archive_path / "SETTINGS.md").is_file()
        assert "oldacct" not in listing.json()["accounts"]
        assert listing.json()["active"] == "keepacct"

    _run(_test())


def test_delete_account_rejects_active_account(tmp_path, monkeypatch):
    _patch_account_roots(monkeypatch, tmp_path)
    _write_example_settings(tmp_path)
    _make_account(tmp_path, "keepacct")
    _make_account(tmp_path, "oldacct")
    (tmp_path / "accounts" / ".active").write_text("oldacct\n", encoding="utf-8")

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/accounts/oldacct")
        assert resp.status_code == 409
        assert (tmp_path / "accounts" / "oldacct" / "SETTINGS.md").is_file()

    _run(_test())


# ---------------------------------------------------------------------------
# Path traversal via URL-encoded slashes in report file param
# ---------------------------------------------------------------------------

def test_report_traversal_returns_400_or_404():
    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # URL-encoded traversal: ../../../etc/passwd
            resp = await client.get("/accounts/default/reports/..%2F..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404), f"expected 400 or 404, got {resp.status_code}"

    _run(_test())


# ---------------------------------------------------------------------------
# GET /api/accounts/_total/holdings → read-only rollup across real accounts
# ---------------------------------------------------------------------------

def test_get_holdings_total_returns_read_only_rollup():
    def _expected_rows(account):
        state = replay(load_transactions_markdown(Path("accounts") / account / "ledger"))
        expected = {}
        for ticker, lots in state.open_lots.items():
            for lot in lots:
                if abs(lot.qty) <= 1e-9:
                    continue
                key = (account, ticker, lot.currency)
                expected[key] = expected.get(key, 0.0) + lot.qty
        for currency, amount in state.cash.items():
            if abs(amount) > 1e-9:
                key = (account, currency, currency)
                expected[key] = expected.get(key, 0.0) + amount
        return expected

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/accounts/_total/holdings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_total"] is True
        assert body["read_only"] is True
        assert body["rows"]
        assert {row["account"] for row in body["rows"]} >= {"default", "crypto"}
        actual = {
            (row["account"], row["ticker"], row["trade_currency"]): row["qty"]
            for row in body["rows"]
        }
        for key, expected_qty in {
            **_expected_rows("default"),
            **_expected_rows("crypto"),
        }.items():
            assert key in actual
            assert abs(actual[key] - expected_qty) <= 1e-9

    _run(_test())


# ---------------------------------------------------------------------------
# Traversal in account name parameter
# ---------------------------------------------------------------------------

def test_account_traversal_returns_400_or_404():
    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/accounts/..%2Fevil/reports")
        assert resp.status_code in (400, 404), f"expected 400 or 404, got {resp.status_code}"

    _run(_test())


# ---------------------------------------------------------------------------
# DELETE /api/accounts/{name}/reports/old
# ---------------------------------------------------------------------------

def test_delete_old_reports_endpoint_deletes_old_reports(tmp_path, monkeypatch):
    import ui.accounts as ui_accounts
    import ui.reports as ui_reports
    from datetime import date

    _patch_account_roots(monkeypatch, tmp_path)
    reports_dir = _make_account(tmp_path, "default") / "reports"
    old = reports_dir / "2026-04-01_0900_daily_report.html"
    new = reports_dir / "2026-05-01_0900_portfolio_report.html"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    monkeypatch.setattr(ui_accounts, "ACCOUNTS_ROOT", (tmp_path / "accounts").resolve())
    monkeypatch.setattr(ui_reports, "date", type("FixedDate", (date,), {"today": classmethod(lambda cls: date(2026, 5, 15))}))

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/accounts/default/reports/old?days=30")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_count"] == 1
        assert body["deleted"] == [old.name]
        assert not old.exists()
        assert new.exists()

    _run(_test())


# ---------------------------------------------------------------------------
# POST /api/accounts/{name}/imports/upload
# ---------------------------------------------------------------------------

def test_upload_import_file_stages_file_for_terminal_prompt(tmp_path, monkeypatch):
    import ui.app as ui_app

    _patch_account_roots(monkeypatch, tmp_path)
    _make_account(tmp_path, "default")
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(ui_app, "_UPLOADS_ROOT", upload_root)

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/accounts/default/imports/upload?filename=..%2Fbroker.csv",
                content=b"date,ticker,qty\n2026-01-02,NVDA,1\n",
                headers={"content-type": "text/csv"},
            )
        assert resp.status_code == 201
        body = resp.json()
        staged = Path(body["path"])
        assert body["account"] == "default"
        assert body["filename"] == "broker.csv"
        assert staged.is_file()
        assert staged.read_bytes() == b"date,ticker,qty\n2026-01-02,NVDA,1\n"
        assert upload_root in staged.parents

    _run(_test())


def test_upload_import_file_rejects_total_account(tmp_path, monkeypatch):
    _patch_account_roots(monkeypatch, tmp_path)
    (tmp_path / "accounts" / "_total" / "reports").mkdir(parents=True)

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/accounts/_total/imports/upload?filename=broker.csv",
                content=b"x",
            )
        assert resp.status_code == 400
        assert "read-only aggregate" in resp.json()["error"]

    _run(_test())


# ---------------------------------------------------------------------------
# GET /api/agents — only includes agents whose binary is on PATH
# ---------------------------------------------------------------------------

def test_get_agents_lists_only_detected_binaries():
    import shutil
    from ui.app import _AGENT_SPECS  # noqa: WPS437

    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/agents")
        assert resp.status_code == 200
        body = resp.json()
        listed_ids = {a["id"] for a in body["agents"]}
        # Each listed id must correspond to a binary that's actually on PATH.
        for aid in listed_ids:
            binary = _AGENT_SPECS[aid]["binary"]
            assert shutil.which(binary), f"{aid} listed but {binary} not on PATH"
        # Conversely, any spec'd id whose binary is on PATH must be listed.
        for aid, spec in _AGENT_SPECS.items():
            if shutil.which(spec["binary"]):
                assert aid in listed_ids, f"{aid} ({spec['binary']}) on PATH but missing from /api/agents"
        # Each listed agent has both id and label fields.
        for a in body["agents"]:
            assert "id" in a and "label" in a

    _run(_test())


def test_terminal_agent_specs_enable_auto_execute_permissions():
    from ui.app import _AGENT_SPECS  # noqa: WPS437

    assert "--dangerously-skip-permissions" in _AGENT_SPECS["claude"]["argv"]
    assert (
        "--dangerously-bypass-approvals-and-sandbox"
        in _AGENT_SPECS["codex"]["argv"]
    )


def test_static_terminal_geometry_sync_contract():
    html = Path("ui/static/index.html").read_text(encoding="utf-8")

    assert "convertEol: false" in html
    assert "let activeFitAndResize = null" in html
    assert "let terminalLaunchSerial = 0" in html
    assert "const launchSerial = ++terminalLaunchSerial" in html
    assert "requestAnimationFrame(() => {" in html
    assert "if (launchSerial !== terminalLaunchSerial) return;" in html
    assert "function resetTerminalRuntime()" in html
    assert "hasStaleTerminalRuntime" in html
    assert "container.replaceChildren()" in html
    assert "void container.offsetHeight" in html
    assert "term.refresh(0, Math.max(0, term.rows - 1))" in html
    assert "setTimeout(fitAndResize, 0)" in html
    assert "setTimeout(fitAndResize, 220)" in html
    assert "setTimeout(fitAndResize, 600)" in html
    assert "activeResizeObserver.observe(terminalPanel)" in html
    assert "window.addEventListener('resize', () => {" in html
    assert "if (activeFitAndResize) requestAnimationFrame(activeFitAndResize);" in html
