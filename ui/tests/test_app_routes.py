"""Tests for ui.app FastAPI routes — no live server, asyncio.run shim."""

import asyncio

import httpx
from httpx import ASGITransport

from ui.app import app


def _run(coro):
    """Synchronous shim so tests need no pytest-asyncio dependency."""
    return asyncio.run(coro)


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
# GET /api/accounts/_total/holdings → 503 (no db)
# ---------------------------------------------------------------------------

def test_get_holdings_total_returns_503():
    async def _test():
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/accounts/_total/holdings")
        assert resp.status_code == 503
        body = resp.json()
        assert "error" in body

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
        installer_ids = {a["id"] for a in body.get("installers", [])}
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
        # Missing Claude/Codex get install affordances instead of being bundled.
        for aid, binary in (("install_claude", "claude"), ("install_codex", "codex")):
            if shutil.which(binary) is None:
                assert aid in installer_ids

    _run(_test())
