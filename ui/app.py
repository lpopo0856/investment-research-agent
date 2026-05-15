"""FastAPI application for the one-page local investment management UI.

Mount point: ``ui/app.py:app`` — started by ``scripts/run_ui_server.py``.
Bound to ``127.0.0.1:8765`` (enforced by the server script, not here).

Route summary
-------------
GET  /                                        → serve static index.html or 503
GET  /api/accounts                            → account list + default
POST /api/accounts                            → create account scaffold
POST /api/accounts/{name}/use                 → set active account
PATCH /api/accounts/{name}                    → rename account
DELETE /api/accounts/{name}                   → archive account
GET  /api/accounts/{name}/holdings            → live recompute
GET  /api/accounts/{name}/reports             → paginated report list
GET  /accounts/{name}/reports/{file}          → serve report HTML
GET  /api/accounts/{name}/settings            → read SETTINGS.md
POST /api/accounts/{name}/settings/preview    → diff preview + token
PUT  /api/accounts/{name}/settings            → atomic write
POST /api/accounts/{name}/imports/upload      → save a user-selected import file
WS   /ws/terminal                             → PTY pump
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from ui.accounts import (
    AccountAdminError,
    REPO_ROOT,
    account_summaries,
    active_account,
    archive_account,
    create_account,
    default_account,
    discover_accounts,
    rename_account,
    resolve_account_path,
    set_active_account,
)
from ui.holdings import HoldingsRecomputeError, recompute_holdings
from ui.reports import clear_old_reports, list_reports, paginate, resolve_report_path
from ui.settings_io import (
    build_diff,
    build_section_diff,
    list_sections,
    read_settings,
    write_section,
    write_settings,
)
from ui.terminal import AgentNotFoundError, TerminalSession, close_all_active

logger = logging.getLogger(__name__)

_STATIC_DIR = REPO_ROOT / "ui" / "static"
_INDEX_HTML = _STATIC_DIR / "index.html"
_TERMINAL_CLOSE_TIMEOUT_S = 5.0
_TERMINAL_MIN_COLS = 40
_TERMINAL_MAX_COLS = 240
_TERMINAL_MIN_ROWS = 10
_TERMINAL_MAX_ROWS = 80
_UPLOADS_ROOT = REPO_ROOT / "temp" / "ui_uploads"
_MAX_IMPORT_UPLOAD_BYTES = 50 * 1024 * 1024
_UPLOAD_FILENAME_BAD_CHARS_RE = re.compile(r'[\x00-\x1f\x7f/\\<>:"|?*]+')


# Agent registry. Each entry maps a stable id used in the WS query string and
# in /api/agents responses to a (label, argv) pair. The label is shown on the
# UI button; argv is what gets executed. Detection runs once at import time —
# the server is started per-session, so a missing binary at boot won't flap.
_AGENT_SPECS: dict[str, dict] = {
    "claude": {
        "label": "claude",
        "argv": ["claude", "--dangerously-skip-permissions"],
        "binary": "claude",
    },
    "codex": {
        "label": "codex",
        "argv": ["codex", "--dangerously-bypass-approvals-and-sandbox"],
        "binary": "codex",
    },
    "codex_omx": {
        "label": "codex(omx)",
        "argv": ["omx", "--madmax", "--high"],
        "binary": "omx",
    },
}
_AVAILABLE_AGENTS: dict[str, dict] = {
    aid: spec for aid, spec in _AGENT_SPECS.items()
    if shutil.which(spec["binary"]) is not None
}

app = FastAPI(title="Investments UI", version="1.0.0")


async def _close_terminal_session(
    session: TerminalSession,
    timeout_s: float = _TERMINAL_CLOSE_TIMEOUT_S,
) -> None:
    """Close a PTY session off the event loop.

    Stopping interactive agents can take a few seconds while signals escalate
    to SIGKILL. Running that synchronous teardown on the WebSocket event loop
    makes the whole local server appear frozen when the user confirms an agent
    switch, because the browser immediately opens the replacement WebSocket.
    """
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, session.close),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        logger.warning("terminal session close exceeded %.1fs budget", timeout_s)


def _clamp_terminal_size(cols: int, rows: int) -> tuple[int, int]:
    """Keep browser-provided terminal dimensions in a sane PTY range."""
    safe_cols = max(_TERMINAL_MIN_COLS, min(_TERMINAL_MAX_COLS, int(cols or 120)))
    safe_rows = max(_TERMINAL_MIN_ROWS, min(_TERMINAL_MAX_ROWS, int(rows or 32)))
    return safe_cols, safe_rows


def _safe_upload_filename(filename: str) -> str:
    """Return a display-safe basename for a browser-uploaded import file."""
    raw = str(filename or "upload").replace("\\", "/").split("/")[-1].strip()
    cleaned = _UPLOAD_FILENAME_BAD_CHARS_RE.sub("_", raw).strip(" ._")
    if not cleaned:
        cleaned = "upload"
    if len(cleaned) <= 120:
        return cleaned

    suffix = ""
    if "." in cleaned:
        stem, ext = cleaned.rsplit(".", 1)
        suffix = f".{ext[:24]}"
    else:
        stem = cleaned
    return f"{stem[: max(1, 120 - len(suffix))]}{suffix}"


def _upload_target_path(account: str, filename: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    unique = uuid.uuid4().hex[:10]
    return _UPLOADS_ROOT / account / f"{stamp}-{unique}-{_safe_upload_filename(filename)}"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def _startup() -> None:
    logger.info("Server up")


@app.on_event("shutdown")
async def _shutdown() -> None:
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, close_all_active), timeout=5.0
        )
    except asyncio.TimeoutError:
        logger.warning("close_all_active exceeded 5s shutdown budget")


# ---------------------------------------------------------------------------
# Static / root
# ---------------------------------------------------------------------------


@app.api_route("/", methods=["GET", "HEAD"], response_model=None)
async def root() -> Union[FileResponse, PlainTextResponse]:
    if _INDEX_HTML.exists():
        return FileResponse(str(_INDEX_HTML), media_type="text/html")
    return PlainTextResponse(
        "UI not built yet (ui/static/index.html missing)", status_code=503
    )


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


@app.get("/api/accounts", response_model=None)
async def get_accounts() -> JSONResponse:
    accounts = discover_accounts()
    active = active_account()
    return JSONResponse(
        {
            "accounts": accounts,
            "active": active,
            "default": default_account(accounts),
            "items": account_summaries(),
        }
    )


@app.post("/api/accounts", response_model=None)
async def post_account(body: dict) -> JSONResponse:
    name = str(body.get("name", "")).strip()
    set_active = bool(body.get("set_active", False))
    try:
        result = create_account(name, set_active=set_active)
    except AccountAdminError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(result, status_code=201)


@app.post("/api/accounts/{name}/use", response_model=None)
async def use_account(name: str) -> JSONResponse:
    try:
        result = set_active_account(name)
    except AccountAdminError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)
    return JSONResponse(result)


@app.patch("/api/accounts/{name}", response_model=None)
async def patch_account(name: str, body: dict) -> JSONResponse:
    new_name = str(body.get("name", "")).strip()
    try:
        result = rename_account(name, new_name)
    except AccountAdminError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)
    return JSONResponse(result)


@app.delete("/api/accounts/{name}", response_model=None)
async def delete_account(name: str) -> JSONResponse:
    try:
        result = archive_account(name)
    except AccountAdminError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------


@app.get("/api/accounts/{name}/holdings", response_model=None)
async def get_holdings(name: str, live: Optional[str] = None) -> JSONResponse:
    try:
        data = recompute_holdings(name, timeout_s=30.0)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except HoldingsRecomputeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return JSONResponse(data)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@app.get("/api/accounts/{name}/reports", response_model=None)
async def get_reports(name: str, page: int = 1, size: int = 12) -> JSONResponse:
    # Validate page and size before touching the filesystem.
    if page < 1:
        return JSONResponse({"error": "page must be >= 1"}, status_code=400)
    if not (1 <= size <= 100):
        return JSONResponse({"error": "size must be between 1 and 100"}, status_code=400)

    try:
        items = list_reports(name)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    result = paginate(items, page, size)
    return JSONResponse(result)


@app.get("/accounts/{name}/reports/{file}", response_model=None)
async def get_report_file(name: str, file: str) -> Union[FileResponse, JSONResponse]:
    try:
        path = resolve_report_path(name, file)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return FileResponse(str(path), media_type="text/html")


@app.delete("/api/accounts/{name}/reports/old", response_model=None)
async def delete_old_reports(name: str, days: int = 30) -> JSONResponse:
    try:
        result = clear_old_reports(name, days=days)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Import file staging
# ---------------------------------------------------------------------------


@app.post("/api/accounts/{name}/imports/upload", response_model=None)
async def upload_import_file(name: str, request: Request, filename: str = "") -> JSONResponse:
    if name == "_total":
        return JSONResponse(
            {"error": "_total is a read-only aggregate, not an import target"},
            status_code=400,
        )
    try:
        resolve_account_path(name)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    data = await request.body()
    if not data:
        return JSONResponse({"error": "uploaded file is empty"}, status_code=400)
    if len(data) > _MAX_IMPORT_UPLOAD_BYTES:
        return JSONResponse(
            {"error": "uploaded file exceeds the 50 MiB limit"},
            status_code=413,
        )

    target = _upload_target_path(name, filename)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError as exc:
        logger.exception("failed to stage import upload")
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse(
        {
            "account": name,
            "filename": _safe_upload_filename(filename),
            "path": str(target),
            "size": len(data),
        },
        status_code=201,
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@app.get("/api/accounts/{name}/settings", response_model=None)
async def get_settings(name: str) -> JSONResponse:
    try:
        content = read_settings(name)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"content": content})


@app.post("/api/accounts/{name}/settings/preview", response_model=None)
async def preview_settings(name: str, body: dict) -> JSONResponse:
    new_content: str = body.get("new_content", "")
    try:
        diff_result = build_diff(name, new_content)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse(diff_result)


@app.put("/api/accounts/{name}/settings", response_model=None)
async def put_settings(name: str, body: dict) -> JSONResponse:
    new_content: str = body.get("new_content", "")
    token: str = body.get("token", "")
    try:
        result = write_settings(name, new_content, token)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse(result)


@app.get("/api/accounts/{name}/settings/sections", response_model=None)
async def get_settings_sections(name: str) -> JSONResponse:
    try:
        result = list_sections(name)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse(result)


@app.post(
    "/api/accounts/{name}/settings/sections/{section_index}/preview",
    response_model=None,
)
async def preview_settings_section(
    name: str, section_index: int, body: dict
) -> JSONResponse:
    new_body: str = body.get("new_body", "")
    try:
        diff_result = build_section_diff(name, section_index, new_body)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse(diff_result)


@app.put("/api/accounts/{name}/settings/sections/{section_index}", response_model=None)
async def put_settings_section(
    name: str, section_index: int, body: dict
) -> JSONResponse:
    new_body: str = body.get("new_body", "")
    token: str = body.get("token", "")
    try:
        result = write_section(name, section_index, new_body, token)
    except ValueError as exc:
        # Distinguish bad-index (400) from bad-token (409) using the message.
        msg = str(exc)
        status = 400 if "section index out of range" in msg else 409
        return JSONResponse({"error": msg}, status_code=status)
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# WebSocket terminal
# ---------------------------------------------------------------------------


@app.get("/api/agents", response_model=None)
async def list_agents() -> JSONResponse:
    """Return agents available on this machine (detected at server startup)."""
    return JSONResponse({
        "agents": [
            {"id": aid, "label": spec["label"]}
            for aid, spec in _AVAILABLE_AGENTS.items()
        ]
    })


@app.websocket("/ws/terminal")
async def ws_terminal(
    websocket: WebSocket,
    agent: str = "claude",
    account: str = "default",
    cols: int = 120,
    rows: int = 32,
) -> None:
    await websocket.accept()

    # Validate agent.
    spec = _AVAILABLE_AGENTS.get(agent)
    if spec is None:
        await websocket.close(code=4400, reason="unsupported agent")
        return

    # Validate account.
    try:
        resolve_account_path(account)
    except ValueError:
        await websocket.close(code=4400, reason="bad account")
        return

    session = TerminalSession()
    try:
        initial_cols, initial_rows = _clamp_terminal_size(cols, rows)
        session.spawn(spec["argv"], account, cols=initial_cols, rows=initial_rows)
    except AgentNotFoundError:
        await websocket.close(code=4404, reason=f"agent not on PATH: {agent}")
        return

    loop = asyncio.get_running_loop()

    async def _read_pty() -> bytes:
        return await loop.run_in_executor(None, session.read_nonblocking, 4096)

    try:
        while True:
            if not session.is_alive():
                break

            # Read from WS (non-blocking with short timeout).
            # Wire protocol:
            #   - TEXT frames are always stdin (raw UTF-8 bytes to the PTY).
            #   - BINARY frames starting with 0x01 are resize control:
            #     [0x01][JSON {"cols": int, "rows": int}]
            #   - other BINARY frames are stdin bytes (rare; keystroke addons
            #     may send binary).
            stdin_bytes: bytes | None = None
            disconnected = False
            try:
                raw = await asyncio.wait_for(websocket.receive(), timeout=0.05)
                if raw.get("type") == "websocket.disconnect":
                    disconnected = True
                elif raw.get("bytes") is not None:
                    bin_msg: bytes = raw["bytes"]
                    if bin_msg[:1] == b"\x01":
                        try:
                            ctrl = json.loads(bin_msg[1:].decode("utf-8", errors="replace"))
                            session.resize(int(ctrl.get("cols", 80)), int(ctrl.get("rows", 24)))
                        except (ValueError, KeyError, TypeError):
                            pass
                    else:
                        stdin_bytes = bin_msg
                elif raw.get("text") is not None:
                    stdin_bytes = raw["text"].encode("utf-8")
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

            if disconnected:
                break

            if stdin_bytes is not None:
                session.write(stdin_bytes)

            # Read from PTY and forward to WS.
            pty_chunk = await _read_pty()
            if pty_chunk:
                try:
                    await websocket.send_text(pty_chunk.decode("utf-8", errors="replace"))
                except WebSocketDisconnect:
                    break

            # If both sides yielded nothing, yield the event loop briefly.
            if stdin_bytes is None and not pty_chunk:
                await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Unexpected error in ws_terminal pump loop")
    finally:
        await _close_terminal_session(session)
