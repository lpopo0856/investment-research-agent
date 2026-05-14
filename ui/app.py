"""FastAPI application for the one-page local investment management UI.

Mount point: ``ui/app.py:app`` — started by ``scripts/run_ui_server.py``.
Bound to ``127.0.0.1:8765`` (enforced by the server script, not here).

Route summary
-------------
GET  /                                        → serve static index.html or 503
GET  /api/accounts                            → account list + default
GET  /api/accounts/{name}/holdings            → live recompute
GET  /api/accounts/{name}/reports             → paginated report list
GET  /accounts/{name}/reports/{file}          → serve report HTML
GET  /api/accounts/{name}/settings            → read SETTINGS.md
POST /api/accounts/{name}/settings/preview    → diff preview + token
PUT  /api/accounts/{name}/settings            → atomic write
WS   /ws/terminal                             → PTY pump
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import shutil
import sys
from typing import Optional, Union

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from ui.accounts import default_account, discover_accounts, resolve_account_path
from ui.holdings import HoldingsRecomputeError, recompute_holdings
from ui.reports import list_reports, paginate, resolve_report_path
from ui.settings_io import (
    build_diff,
    build_section_diff,
    list_sections,
    read_settings,
    write_section,
    write_settings,
)
from ui.terminal import AgentNotFoundError, TerminalSession, close_all_active
from ui.runtime_paths import bootstrap_local_data, resource_path

logger = logging.getLogger(__name__)

_STATIC_DIR = resource_path("ui", "static")
_INDEX_HTML = _STATIC_DIR / "index.html"

# Agent registry. Each entry maps a stable id used in the WS query string and
# in /api/agents responses to a (label, argv) pair. The label is shown on the
# UI button; argv is what gets executed. Detection runs once at import time —
# the server is started per-session, so a missing binary at boot won't flap.
_AGENT_SPECS: dict[str, dict] = {
    "claude": {"label": "claude", "argv": ["claude"], "binary": "claude"},
    "codex": {"label": "codex", "argv": ["codex"], "binary": "codex"},
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

_INSTALLABLE_AGENT_SPECS: dict[str, dict] = {
    "claude": {
        "id": "install_claude",
        "label": "Install Claude Code",
        "tool": "claude",
        "command": "npm install -g @anthropic-ai/claude-code",
        "binary": "claude",
    },
    "codex": {
        "id": "install_codex",
        "label": "Install Codex",
        "tool": "codex",
        "command": "npm install -g @openai/codex",
        "binary": "codex",
    },
}


def _installer_argv(spec: dict) -> list[str]:
    """Return a shell session that shows, but does not auto-run, install help."""

    command = spec["command"]
    tool_label = spec["label"]
    if sys.platform == "win32":
        message = (
            f"Write-Host '{tool_label}'; "
            f"Write-Host 'Review and run this command if you want to install it:'; "
            f"Write-Host '{command}'; "
            "Write-Host ''; "
            "Write-Host 'This packaged app does not bundle optional agent CLIs.'"
        )
        return ["powershell", "-NoExit", "-Command", message]

    shell = os.environ.get("SHELL") or "/bin/sh"
    message = (
        f"printf '%s\\n' {shlex.quote(tool_label)} "
        f"{shlex.quote('Review and run this command if you want to install it:')} "
        f"{shlex.quote(command)} '' "
        f"{shlex.quote('This packaged app does not bundle optional agent CLIs.')}; "
        f"exec {shlex.quote(shell)} -l"
    )
    return [shell, "-lc", message]

app = FastAPI(title="Investments UI", version="1.0.0")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def _startup() -> None:
    bootstrap_local_data()
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
    return JSONResponse({"accounts": accounts, "default": default_account(accounts)})


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
    """Return available optional agents and install affordances."""

    installers = [
        {
            "id": spec["id"],
            "label": spec["label"],
            "tool": spec["tool"],
        }
        for spec in _INSTALLABLE_AGENT_SPECS.values()
        if shutil.which(spec["binary"]) is None
    ]
    return JSONResponse({
        "agents": [
            {"id": aid, "label": spec["label"]}
            for aid, spec in _AVAILABLE_AGENTS.items()
        ],
        "installers": installers,
    })


@app.websocket("/ws/terminal")
async def ws_terminal(websocket: WebSocket, agent: str = "claude", account: str = "default") -> None:
    await websocket.accept()

    # Validate agent.
    spec = _AVAILABLE_AGENTS.get(agent)
    installer_spec = next(
        (
            candidate for candidate in _INSTALLABLE_AGENT_SPECS.values()
            if candidate["id"] == agent
        ),
        None,
    )
    if spec is None:
        if installer_spec is None:
            await websocket.close(code=4400, reason="unsupported agent")
            return
        argv = _installer_argv(installer_spec)
        spec = {
            "label": installer_spec["label"],
            "argv": argv,
            "binary": argv[0],
            "installer": True,
        }

    # Validate account for real agent sessions. Installer helper sessions are
    # allowed before the first empty profile contains any accounts.
    if not spec.get("installer"):
        try:
            resolve_account_path(account)
        except ValueError:
            await websocket.close(code=4400, reason="bad account")
            return

    session = TerminalSession()
    try:
        session.spawn(spec["argv"], account)
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
        session.close()
