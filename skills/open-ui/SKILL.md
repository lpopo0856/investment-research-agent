---
name: open-ui
description: Open the local investment dashboard quickly and reliably. Use when the user asks to open, start, launch, or show the UI/browser dashboard for this repo; prefer the optimized known-entrypoint path over rediscovering the UI each time.
---

# Open UI

## Goal

Open the local FastAPI dashboard at `http://127.0.0.1:8765/` with the least safe work needed. This is repo maintenance / local UI launch only; it does not require account resolution unless the task expands into account-bound output or protected file access.

## Fast Path

1. **Do not start with broad repository discovery.** In this repo the UI entrypoint is stable:
   - server: `scripts/run_ui_server.py`
   - app target: `ui.app:app`
   - frontend: `ui/static/index.html`
   - default URL: `http://127.0.0.1:8765/`
2. Probe the default URL first. On Unix/macOS shells use:

   ```bash
   curl -fsS --max-time 1 -o /dev/null http://127.0.0.1:8765/
   ```

   On Windows PowerShell, avoid `curl` because it may be an alias; use:

   ```powershell
   try {
     $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/' -TimeoutSec 1
     if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { exit 0 }
     exit 1
   } catch { exit 1 }
   ```

3. If the probe succeeds, open that URL immediately (`open <url>` on macOS, `Start-Process <url>` on Windows) and stop after reporting it.
4. If the probe fails, start the server in a **visible independent terminal window**, never in the agent's background/tool session. The user must be able to see the server process and close that terminal window themselves. This is a hard requirement: do not use Codex/agent-managed background sessions for the UI server.

   On macOS, prefer Terminal via AppleScript from the repo root:

   ```bash
   REPO_ROOT=$(pwd)
   osascript - "$REPO_ROOT" <<'OSA'
   on run argv
     set repoRoot to item 1 of argv
     tell application "Terminal"
       activate
       do script "cd " & quoted form of repoRoot & " && PY=.venv-ui/bin/python; [ -x \"$PY\" ] || PY=python3; INVESTMENTS_UI_NO_BROWSER=1 \"$PY\" scripts/run_ui_server.py"
     end tell
   end run
   OSA
   ```

   On Windows, prefer a visible PowerShell window from the repo root. Use the Windows venv path when present, then fall back to `python`:

   ```powershell
   $repo = (Get-Location).Path
   $inner = @"
   Set-Location -LiteralPath '$($repo -replace "'", "''")'
   `$py = Join-Path (Get-Location).Path '.venv-ui\Scripts\python.exe'
   if (-not (Test-Path `$py)) { `$py = 'python' }
   `$env:INVESTMENTS_UI_NO_BROWSER = '1'
   & `$py scripts/run_ui_server.py
   "@
   Start-Process powershell.exe -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $inner)
   ```

   `INVESTMENTS_UI_NO_BROWSER=1` prevents duplicate browser opens because the agent will open the verified URL explicitly after the server is reachable. Do **not** use a hidden long-running tool session or any Codex/agent-managed background process for the UI server.
5. Wait only until the URL probe succeeds, then open `http://127.0.0.1:8765/`. The visible terminal window remains open for the user to stop/close.
6. Verify with the same probe style: `curl -fsS --max-time 2 -o /dev/null http://127.0.0.1:8765/` on Unix/macOS, or `Invoke-WebRequest -UseBasicParsing -TimeoutSec 2` on Windows PowerShell. Avoid piping full HTML to `head`; that can produce a harmless broken-pipe `curl: (23)` message and confuse the status.

## Fallbacks

- If `.venv-ui` is missing dependencies, install only `requirements-ui.txt` into the chosen Python environment, then retry the server.
- If port `8765` is occupied by a non-UI service, choose a free local port and start the visible terminal command with `INVESTMENTS_UI_PORT=<port> INVESTMENTS_UI_NO_BROWSER=1 ...` on Unix/macOS or `$env:INVESTMENTS_UI_PORT='<port>'; $env:INVESTMENTS_UI_NO_BROWSER='1'; ...` on Windows; report the resulting URL.
- If macOS Terminal/AppleScript or Windows PowerShell is unavailable, use another visible local terminal emulator when available. If no visible terminal launch path exists, do **not** start the UI server in an agent-managed background process; report the blocker and give the URL/command only as manual fallback.
- If the environment provides an in-app Browser tool and the user specifically wants that surface, navigate the Browser to the verified local URL. Otherwise use the platform opener (`open` on macOS) or Python `webbrowser.open`.
- Use `omx explore` only when the known files above are missing or the launch path has changed.

## Report Contract

Keep the user-facing response short:

- URL opened
- whether the server was already running or newly started
- whether a visible terminal window was opened for the server
- verification result
- any fallback used or blocker found
