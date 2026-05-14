# Local Management UI

Single-page local web dashboard for the investments repo. Browser front-end
served by a FastAPI back-end bound to `127.0.0.1`. Lets the user view
holdings, browse + open reports, edit `SETTINGS.md` section-by-section, run a
`claude` / `codex` / `omx` agent inside an embedded xterm.js terminal, and
fire prefilled trade/deposit prompts at that agent.

Originating spec: [`.omc/specs/deep-interview-one-page-management-ui.md`](../.omc/specs/deep-interview-one-page-management-ui.md).
Originating impl plan: [`.omc/plans/autopilot-impl.md`](../.omc/plans/autopilot-impl.md).

---

## Run it

```bash
python3 -m venv .venv-ui                  # use a Python 3.9+ interpreter
source .venv-ui/bin/activate              # mac/linux
# Windows: .venv-ui\Scripts\Activate.ps1
pip install -r requirements-ui-dev.txt
python3 scripts/run_ui_server.py          # NOT just `python` if it is shell-aliased
# → "Server: http://127.0.0.1:8765/"
```

If your shell aliases `python` to a non-venv interpreter, call `python3`
explicitly or `unalias python` first. Auto-opening the browser can be
suppressed with `INVESTMENTS_UI_NO_BROWSER=1`; the port can be overridden
with `INVESTMENTS_UI_PORT=<port>`.

---

## Repo layout

```
ui/                              ← new Python package
  __init__.py
  accounts.py        71 lines    account discovery + path safety
  reports.py        110 lines    report listing + pagination + safe path resolve
  holdings.py        89 lines    cost-basis read via portfolio_snapshot.compute_snapshot(prices={})
  settings_io.py    249 lines    SETTINGS.md read / parse-by-section / safe-write with backup
  terminal.py       327 lines    cross-platform PTY (ptyprocess on POSIX, pywinpty on win32)
  app.py            360 lines    FastAPI app — all HTTP/WS routes
  static/
    index.html     1033 lines    single-page dark dashboard (Tailwind + xterm.js + htmx via CDN)
  tests/
    test_accounts.py
    test_reports.py
    test_settings_io.py
    test_app_routes.py
    test_terminal_posix.py       (skipped on win32)
scripts/
  run_ui_server.py   45 lines    uvicorn entrypoint
requirements-ui.txt              fastapi, uvicorn[standard], websockets, platformdirs, ptyprocess/pywinpty
requirements-ui-dev.txt          +pytest, httpx (>=0.27 for ASGITransport)
requirements-ui-build.txt        +PyInstaller and report-fetch dependencies for one-file executable builds
```

`ui/static/index.html` is intentionally a single file — Tailwind, xterm.js,
xterm-addon-attach, xterm-addon-fit, htmx all come from public CDNs. **No
bundler, no `node_modules`, no build step.**

---

## Backend stack

| Concern | Choice | Notes |
|---|---|---|
| HTTP / WS | **FastAPI** + uvicorn | bound to `127.0.0.1` only |
| PTY | **ptyprocess** (POSIX) / **pywinpty** (win32) | platform-conditional via `sys_platform` markers in `requirements-ui.txt`. Only `ui/terminal.py` branches on `sys.platform`. |
| Holdings | re-uses `scripts/portfolio_snapshot.py` | `compute_snapshot(prices={})` returns lots/cost-basis without any network fetch — see "Holdings contract" below |
| Settings I/O | stdlib `hashlib`/`difflib`/`os.replace` | token-gated TOCTOU; timestamped `.bak.<UTC>` before every write |
| Packaged data dirs | **platformdirs** | frozen builds store mutable data under OS app-data paths; source checkouts keep repo-relative data by default |

The server is **single-process, single-user, local-only**. There is no
auth, no CORS layer, no rate limiting — that's safe because uvicorn binds
to `127.0.0.1` and `_AVAILABLE_AGENTS` is the only thing that can launch a
child process.

---

## HTTP / WS routes

| Method | Path | Behavior |
|---|---|---|
| GET | `/` | serves `ui/static/index.html` (also accepts HEAD for liveness) |
| GET | `/api/accounts` | `{accounts: [...], default: ...}` — directories under `accounts/` that contain at least one of `SETTINGS.md` / `ledger/` / `reports/`. The OR rule is important: `_total` has only `reports/` and would otherwise be silently dropped. |
| GET | `/api/accounts/{name}/holdings` | live cost-basis recompute, **no price fetch**. Hard 10s timeout. On any failure: HTTP 503 `{"error": "..."}`. Never substitutes cached data. |
| GET | `/api/accounts/{name}/reports?page=N&size=12` | paginated list, sorted desc by filename timestamp |
| GET | `/accounts/{name}/reports/{file}` | serve report HTML statically (regex + commonpath guarded) |
| GET | `/api/accounts/{name}/settings` | raw file content (`{content: ...}`) |
| GET | `/api/accounts/{name}/settings/sections` | `{preamble, sections: [{index, name, body}, ...]}` — splits by `## ` headings (fence-blind, see "Settings section parser" below) |
| POST | `/api/accounts/{name}/settings/preview` | full-file preview, returns `{old, new, unified_diff, token}` |
| POST | `/api/accounts/{name}/settings/sections/{idx}/preview` | section-only preview; same response shape, token covers full-file replacement |
| PUT | `/api/accounts/{name}/settings` | full-file write, requires token from preview |
| PUT | `/api/accounts/{name}/settings/sections/{idx}` | section-only write, requires token |
| GET | `/api/agents` | `[{id, label}]` — only includes ids whose binary is on PATH (detected once at server import) |
| WS | `/ws/terminal?agent=<id>&account=<name>` | PTY pump; see "Terminal wire protocol" below |

All routes that take `{name}` or `{file}` pass through `ui.accounts.resolve_account_path`
or `ui.reports.resolve_report_path` first; invalid names → 400, missing
files → 404. Path traversal (`..%2F..%2F..%2Fetc%2Fpasswd`) is rejected at
the regex layer.

---

## Packaged executable build

The desktop-app-feel build path uses PyInstaller one-file executables. The
tracked build wrapper is `scripts/build_ui_executable.py`; it packages
`scripts/run_packaged_ui.py`, bundles `ui/static/`, and deliberately does not
add `accounts/`, ledgers, reports, or root market-data caches as data files.

Build dependencies live in `requirements-ui-build.txt`. It includes PyInstaller
plus the report-fetch dependencies that existing scripts load lazily so CI
artifacts do not depend on whatever happens to be installed on a developer's
machine. GitHub Actions builds macOS, Linux, and Windows artifacts in
`.github/workflows/build-ui-executables.yml` and uploads one runnable executable
per OS artifact using `actions/upload-artifact@v4`.

Mutable data policy:

- Source checkout default: keep using repo-relative `accounts/` for existing
  developer/test behavior.
- Frozen executable default: create an empty app-data workspace via
  `platformdirs` and store mutable `accounts/` plus cache data there.
- Overrides: `INVESTMENTS_DATA_ROOT` points the app at an explicit mutable
  workspace; `INVESTMENTS_ACCOUNTS_ROOT` can override just account discovery.

First run of a packaged app creates the workspace directories only; it does
not ship or seed personal/demo account data.

## Terminal wire protocol

The browser's xterm.js talks to the server-side PTY over `/ws/terminal`.
Two frame types matter:

- **TEXT frames** — always stdin. The server unconditionally writes the
  UTF-8 bytes to the PTY. AttachAddon in the browser pipes `term.onData`
  to `ws.send(text)` so user keystrokes flow through this branch.
- **BINARY frames starting with `0x01`** — resize control:
  `[0x01][JSON {"cols": int, "rows": int}]`. The server parses the JSON
  and calls `session.resize(cols, rows)`.

**Why split text vs binary?** An earlier version put resize on text frames
with the same `\x01` prefix. That collided with Ctrl-A (byte `0x01`) —
typing Ctrl-A in readline got swallowed because the server tried to JSON-
decode the rest. Splitting by frame type means stdin can contain any byte
including `\x01` and resize is unambiguous.

**Doubled-input gotcha**: `AttachAddon` already wires `term.onData →
ws.send` internally. Do **not** register another `term.onData(d => ws.send(d))`
handler — every keystroke would be sent twice. Only the resize handler
should be manually registered.

**Resize handshake**: register `term.onResize` BEFORE the first
`fitAddon.fit()` call so the initial fit's resize event is captured. Also
re-send the current `term.cols × term.rows` from `ws.onopen` — at xterm
init time the WebSocket is still CONNECTING and the resize would be
silently dropped if the handler only sent when open. Without the post-open
resend, the PTY stays at 80×24 default while xterm renders at the fitted
size; the mismatch breaks autoscroll math.

---

## Holdings contract (no live prices, deliberately)

`ui/holdings.py` calls `scripts.portfolio_snapshot.compute_snapshot(prices={})`
and projects each `aggregate` to `{ticker, qty, avg_cost, total_cost,
trade_currency}` — all in the lot's native trade currency.

We do **not** call `fetch_prices.main` or any yfinance API. Earlier
versions did; the network round-trip blew the spec's 30s budget and added
`yfinance` + `requests` to the dependency surface. The current contract:
the UI is a viewer of the ledger state. Market prices come from running
the full report-generation flow through the embedded agent.

If the ledger db is missing (e.g. for `_total`, which is a reports-only
aggregate account), `recompute_holdings` raises `HoldingsRecomputeError`
immediately and the API returns HTTP 503. **No silent substitution of
cached or stale data** — the user sees the failure mode verbatim with a
Retry button rendered next to the holdings table.

---

## Settings save flow (TOCTOU + backup)

1. `read_settings(account)` → current bytes
2. `build_diff(account, new_content)` → `{old, new, unified_diff, token}`.
   `token = sha256(old + "\0" + new + "\0" + account)[:16]`, stashed in a
   16-slot TTL dict (10 min).
3. `write_settings(account, new_content, token)`:
   - re-reads current on-disk content and re-derives the expected token
   - if the file changed between step 2 and 3 (token mismatch) → `ValueError`
     ("settings token invalid or expired") → HTTP 409 → frontend toast
     "SETTINGS.md changed externally — re-opening editor."
   - writes `accounts/{name}/SETTINGS.md.bak.<UTC-iso>` first
   - atomic `os.replace` of a same-dir temp file
   - returns `{backup_path: ...}`

Backups with `_<n>` suffix bumping if two writes hit the same UTC second.

The `.gitignore` already covers `accounts/*/SETTINGS.md.bak.*` so backups
never leak into commits.

### Settings section parser

`_parse_sections(content)` splits on lines starting with `## ` (level-2
headings) and returns `(preamble, sections[])`. Each section's body
includes its heading and runs to the next `## ` or EOF.

The parser is **fence-blind**: it does NOT track ` ``` ` / `~~~` code
fences. The reason is real: `accounts/default/SETTINGS.md` wraps the
entire file in an outer ` ```markdown ` fence for display purposes. A
fence-aware parser would treat the whole file as preamble and find zero
sections. Trade-off: a user who writes a literal `## something` line
inside a fenced code block will see it become a section boundary, which
is recoverable but uncommon in SETTINGS.md files.

Section-only writes still go through the full-file `write_settings` path:
`_rebuild_with_section` reads current on-disk content fresh, replaces the
target section's body, and hands the full bytes to `write_settings`. This
means unrelated sections changed between preview and write trigger the
same TOCTOU rejection as full-file writes.

---

## Agent registry

`ui/app.py` defines:

```python
_AGENT_SPECS = {
    "claude":    {"label": "claude",     "argv": ["claude"],                    "binary": "claude"},
    "codex":     {"label": "codex",      "argv": ["codex"],                     "binary": "codex"},
    "codex_omx": {"label": "codex(omx)", "argv": ["omx", "--madmax", "--high"], "binary": "omx"},
}
_AVAILABLE_AGENTS = {aid: spec for aid, spec in _AGENT_SPECS.items() if shutil.which(spec["binary"])}
```

Detection runs **once at module import**. Adding a new agent: extend
`_AGENT_SPECS`. The frontend fetches `/api/agents` on init and renders
buttons dynamically — no HTML change needed unless you want a custom
label-to-icon mapping.

`TerminalSession.spawn(argv, account)` resolves `argv[0]` via `shutil.which`
and forwards the rest as args. Cwd is the repo root. Env adds
`INVESTMENTS_ACTIVE_ACCOUNT=<name>` so the agent can self-route.

---

## Frontend mental model

`ui/static/index.html` is a single module-scope `<script type="module">`.
Key state vars (~line 164):

| Var | Purpose |
|---|---|
| `selectedAccount` | currently-active account; reflected in `?account=` |
| `reportsPage` / `reportsTotalPages` | report pagination |
| `activeWs` / `activeTerm` / `activeFitAddon` | live xterm session, if any |
| `activeAgentId` | so we can relaunch with the same agent after a settings save |
| `pendingDiff` | currently-previewed section edit waiting on Confirm |
| `settingsDirty` | did any save happen during this modal session? if true, restart terminal on close |
| `lastHoldingsData` | so toggling Sell/Buy can re-render without a re-fetch |
| `holdingActions` | which ticker has its inline action form open + which mode (`sell`/`buy`) |

### Layout

```
┌─ Header (brand + clock)
├─ Main (grid 320px + 1fr)
│  ├─ Sidebar (accounts list w/ per-row ⚙ on the selected row; reports list paginated)
│  └─ Section (flex column)
│     ├─ Scroll wrapper (flex-1, overflow-y-auto)
│     │  └─ Holdings panel (shrink-0, max-h-72 on body)
│     └─ Terminal panel (shrink-0, height: clamp(360px, 50vh, 600px))
└─ Modals (z-50)
   ├─ Settings modal — section cards w/ per-section edit
   ├─ Diff modal — unified diff preview + Confirm
   ├─ Report viewer modal — near-fullscreen iframe (95vw / 94vh)
   ├─ Action form modal — generic Deposit / Buy-new form
   └─ Toast container (top-right, click-through)
```

The Holdings panel + Terminal panel split is intentional: Terminal is
pinned at the bottom so it's never pushed below the fold by a long
holdings table. Both have `shrink-0` so flex doesn't squash them.

### Modals

- **Settings**: opened from the ⚙ next to the selected account in the
  sidebar. Cards-per-section view; click `Edit` on any card to switch
  that card to a textarea; `Save` triggers section preview → diff modal →
  Confirm. On Confirm the per-section PUT runs, `settingsDirty = true`,
  and the section reloads. Closing the settings modal (`×` / ESC) — if
  `settingsDirty && activeWs` — tears down the current terminal and
  relaunches the same agent so it picks up the new SETTINGS.md.
- **Diff**: shows the full-file unified diff for either a section save or
  (legacy) a full-file save. Always full-file even for section edits so
  the user can see the whole picture before committing.
- **Report viewer**: 95vw × 94vh iframe pointing at
  `/accounts/{acct}/reports/{file}`. ESC closes it. The iframe's `src` is
  reset to `about:blank` on close so the report's JS/timers stop running.
- **Action form**: generic small modal driven by `ACTION_FORMS[kind]`
  with `{title, fields, build(values, acct)}`. `submitActionForm()` →
  builds the prompt → `typeToTerminal(prompt)` → closes modal. To add a
  new action: extend `ACTION_FORMS` and add a button somewhere that calls
  `openActionForm('<your-kind>')`.

### Fast actions (terminal prefill)

`typeToTerminal(text, {submit})` pipes `text` to the active WS as a TEXT
frame. With `submit: true` it also sends `\r`. Default is no auto-Enter
— the user reviews the prompt in the terminal before sending. If no live
terminal is active, it shows a toast and returns `false`.

Current fast actions:

| Trigger | Prompt template |
|---|---|
| Holdings header `Daily report` | `Generate today's daily report for the <acct> account and show me the highlights.` |
| Holdings header `Portfolio report` | `Generate a fresh portfolio report for the <acct> account.` |
| Holdings header `Snapshot` | `Show me a quick snapshot of the <acct> account — current positions, cash, and biggest movers.` |
| Holdings header `Deposit` | form → `Please record a deposit of <amount> <ccy> into the <acct> account (note: <note>).` |
| Holdings header `Buy new` | form → `Please buy <qty> <TICKER> at <price> <ccy> for the <acct> account.` |
| Per-row `Sell` (inline form) | `Please sell <qty> <TICKER> at <price> (<ccy>)` |
| Per-row `Buy` (inline form) | `Please buy <qty> <TICKER> at <price> (<ccy>)` |
| Per-row `Ask` | `Walk me through my <TICKER> position — thesis, risk, what I should do next.` |
| Per-report `💬` | `Walk me through the <kind> report at accounts/<acct>/reports/<file> — what stands out and what should I do.` |

---

## How to extend it

- **Add an agent type**: add an entry to `_AGENT_SPECS` in `ui/app.py`.
  Detection at startup auto-includes it in `/api/agents` if the binary is
  on PATH; the frontend renders the button automatically.
- **Add a fast action button**: write a handler in the inline script of
  `index.html`, call `typeToTerminal('...')`. For a form, add a config
  entry to `ACTION_FORMS` and hook a button up to `openActionForm('<kind>')`.
- **Add an API route**: add the handler in `ui/app.py`. Reuse
  `resolve_account_path` / `resolve_report_path` for any user-supplied
  identifiers. Errors: 400 for bad input, 404 for missing files, 409 for
  TOCTOU conflicts, 503 for upstream-resource failures.
- **Add a holdings column**: extend the projection in
  `ui/holdings.py:_do_recompute` (read other fields off `agg`), update
  the table header in `index.html`, update the `<td>` in
  `renderHoldingsRows`, update the colspan in `renderHoldingsSkeleton`
  and `renderHoldingsError`.

---

## Tests

```bash
source .venv-ui/bin/activate
python3 -m pytest ui/tests -q
```

54 tests covering: regex acceptance/rejection, path traversal, section
parser round-trip, settings TOCTOU, ASGI routes (via `httpx.AsyncClient` +
`ASGITransport`), POSIX PTY spawn/echo/close. The Windows PTY path is not
covered by automated tests — verify manually on win32.

---

## Gotchas / things future-me will trip on

1. **`python` aliased to a non-venv interpreter** — common on macOS where
   `python` may be aliased to `/usr/bin/python3`. Use `python3` after
   activating the venv, or `unalias python`.
2. **PEP-604 unions on Python 3.9** — `str | None` evaluates at decorator
   time in FastAPI route signatures, so `from __future__ import
   annotations` doesn't save us. All route handler annotations use
   `Optional[X]` / `Union[X, Y]` from `typing`.
3. **`fitAddon.fit()` before WS open** — register `term.onResize` first
   so the initial event isn't lost, AND explicitly `sendResize()` from
   `ws.onopen`. Otherwise PTY stays at 80×24 while xterm renders fitted.
4. **Doubled keystrokes** — `AttachAddon` already wires stdin. Don't add
   another `term.onData` handler unless you know it's not duplicating.
5. **Flex-shrink trap** — every panel inside the scrollable wrapper needs
   `shrink-0`, otherwise the wrapper's `overflow-y-auto` never kicks in
   and the first panel gets visually crushed to 0px.
6. **`_total` has no `transactions.db.bak`** — `holdings.py` returns 503
   for it intentionally. Account discovery still lists it because it has
   a `reports/` directory; that's the whole point of the OR-based
   discovery rule.
