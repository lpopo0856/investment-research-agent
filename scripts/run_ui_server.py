"""Entrypoint for the local investment management UI.

Usage (from repo root):
    python scripts/run_ui_server.py

Environment variables:
    INVESTMENTS_UI_PORT        Listening port (default: 8765).
    INVESTMENTS_UI_NO_BROWSER  Set to "1" to suppress automatic browser open.
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

# Ensure repo root is importable so ``ui.app`` resolves correctly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402 — must come after sys.path patch


def main() -> None:
    port = int(os.environ.get("INVESTMENTS_UI_PORT", "8765"))
    url = f"http://127.0.0.1:{port}/"

    print(f"Server: {url}", flush=True)

    if os.environ.get("INVESTMENTS_UI_NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        "ui.app:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        ws="websockets",
        log_level="info",
    )


if __name__ == "__main__":
    main()
