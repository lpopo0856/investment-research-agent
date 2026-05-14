"""Frozen-executable entry point for the local Investments UI.

This entry point imports the FastAPI app object directly (instead of the
``"ui.app:app"`` string used by the development script) so PyInstaller can
trace the application imports reliably.
"""

from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn

from ui.app import app
from ui.runtime_paths import bootstrap_local_data


def main() -> None:
    paths = bootstrap_local_data()
    port = int(os.environ.get("INVESTMENTS_UI_PORT", "8765"))
    url = f"http://127.0.0.1:{port}/"

    print(f"Server: {url}", flush=True)
    print(f"Data: {paths['data_root']}", flush=True)

    if os.environ.get("INVESTMENTS_UI_NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        reload=False,
        ws="websockets",
        log_level="info",
    )


if __name__ == "__main__":
    main()
