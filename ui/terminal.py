"""Cross-platform PTY abstraction for the embedded one-page management UI.

This module is the only file in the project that branches on
``sys.platform`` for PTY back-end selection. The rest of the UI talks to
:class:`TerminalSession` and never touches ``ptyprocess`` or ``pywinpty``
directly.

Contract (see ``.omc/plans/autopilot-impl.md`` task T06):

* ``TerminalSession.spawn(agent, account)`` locates ``agent`` via
  ``shutil.which``; raises :class:`AgentNotFoundError` when missing.
* The child inherits ``os.environ`` plus
  ``INVESTMENTS_ACTIVE_ACCOUNT=<account>``, runs with the repo root as
  ``cwd``, and starts at 120 columns x 32 rows.
* I/O is bytes only so the FastAPI WebSocket streams UTF-8 chunks to
  xterm.js without lossy decode/encode passes.
* No subprocess fallback, no fake-PTY mode. If the platform back-end is
  unavailable the import fails loudly.
* Every live session is tracked in :data:`_active_sessions` so the
  FastAPI shutdown hook can terminate orphans on Ctrl-C.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from typing import Set

from ui.runtime_paths import source_root, terminal_working_dir

REPO_ROOT = source_root()

_DEFAULT_COLS = 120
_DEFAULT_ROWS = 32
_TERMINATE_TIMEOUT_S = 2.0


class AgentNotFoundError(RuntimeError):
    """Raised when the agent binary (e.g. ``claude``/``codex``) is not on PATH."""


# ---------------------------------------------------------------------------
# Platform back-end selection. This is the only platform branch in the file.
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    # pywinpty >= 2.0 (pinned in requirements-ui.txt) exposes
    # ``winpty.PtyProcess`` with a ``spawn`` classmethod that returns a
    # live PTY. read/write operate on ``str``; we encode/decode at the
    # back-end boundary so the public surface stays bytes-only.
    from winpty import PtyProcess as _WinPtyProcess  # type: ignore[import-not-found]

    _BACKEND = "win"

    class _Impl:
        """Windows back-end wrapping :class:`winpty.PtyProcess` (pywinpty>=2)."""

        def __init__(self) -> None:
            self._proc: "_WinPtyProcess | None" = None

        def spawn(
            self,
            argv: list[str],
            cwd: str,
            env: dict[str, str],
            cols: int,
            rows: int,
        ) -> None:
            self._proc = _WinPtyProcess.spawn(
                argv,
                cwd=cwd,
                env=env,
                dimensions=(rows, cols),
            )

        def read_nonblocking(self, size: int) -> bytes:
            proc = self._proc
            if proc is None or not proc.isalive():
                return b""
            try:
                chunk = proc.read(size, blocking=False)
            except EOFError:
                return b""
            if not chunk:
                return b""
            return chunk.encode("utf-8", errors="replace")

        def write(self, data: bytes) -> int:
            proc = self._proc
            if proc is None or not proc.isalive():
                return 0
            return proc.write(data.decode("utf-8", errors="replace"))

        def resize(self, cols: int, rows: int) -> None:
            proc = self._proc
            if proc is None:
                return
            proc.setwinsize(rows, cols)

        def terminate(self) -> None:
            proc = self._proc
            if proc is None:
                return
            proc.terminate()

        def kill(self) -> None:
            proc = self._proc
            if proc is None:
                return
            proc.terminate(force=True)

        def is_alive(self) -> bool:
            proc = self._proc
            if proc is None:
                return False
            return bool(proc.isalive())

else:
    import select

    from ptyprocess import PtyProcess as _PosixPtyProcess  # type: ignore[import-not-found]

    _BACKEND = "posix"

    class _Impl:  # type: ignore[no-redef]
        """POSIX back-end wrapping :class:`ptyprocess.PtyProcess` (bytes mode)."""

        def __init__(self) -> None:
            self._proc: "_PosixPtyProcess | None" = None

        def spawn(
            self,
            argv: list[str],
            cwd: str,
            env: dict[str, str],
            cols: int,
            rows: int,
        ) -> None:
            self._proc = _PosixPtyProcess.spawn(
                argv=argv,
                cwd=cwd,
                env=env,
                dimensions=(rows, cols),
            )

        def read_nonblocking(self, size: int) -> bytes:
            proc = self._proc
            if proc is None:
                return b""
            fd = proc.fd
            if fd is None or fd < 0:
                return b""
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                return b""
            try:
                return proc.read(size)
            except EOFError:
                return b""

        def write(self, data: bytes) -> int:
            proc = self._proc
            if proc is None or not proc.isalive():
                return 0
            try:
                return proc.write(data)
            except (OSError, EOFError):
                return 0

        def resize(self, cols: int, rows: int) -> None:
            proc = self._proc
            if proc is None:
                return
            proc.setwinsize(rows, cols)

        def terminate(self) -> None:
            proc = self._proc
            if proc is None:
                return
            proc.terminate(force=False)

        def kill(self) -> None:
            proc = self._proc
            if proc is None:
                return
            # First ask ptyprocess to escalate (SIGHUP -> SIGINT -> SIGKILL).
            proc.terminate(force=True)
            # Belt-and-suspenders: direct SIGKILL + waitpid. ptyprocess's
            # internal wait can race the kernel reaping the child; this
            # ensures isalive() flips False before we return.
            if proc.isalive():
                import os as _os
                import signal as _signal
                try:
                    _os.kill(proc.pid, _signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                wait_deadline = time.monotonic() + 1.0
                while time.monotonic() < wait_deadline:
                    try:
                        waited_pid, _ = _os.waitpid(proc.pid, _os.WNOHANG)
                    except (ChildProcessError, OSError):
                        break
                    if waited_pid:
                        break
                    time.sleep(0.02)
            try:
                proc.close()
            except (OSError, AttributeError):
                pass

        def is_alive(self) -> bool:
            proc = self._proc
            if proc is None:
                return False
            try:
                return bool(proc.isalive())
            except Exception:  # noqa: BLE001
                # ptyprocess can raise once the child has been reaped
                # externally; treat as dead.
                return False


# ---------------------------------------------------------------------------
# Public surface.
# ---------------------------------------------------------------------------


class TerminalSession:
    """Cross-platform handle around a single PTY-attached agent process."""

    def __init__(self) -> None:
        self._impl: _Impl = _Impl()
        self._spawned: bool = False

    def spawn(self, argv, account: str) -> None:
        """Launch ``argv`` under a fresh PTY.

        ``argv`` may be a bare binary name (``"claude"``) or a list of
        ``[binary, *args]`` (``["omx", "--madmax", "--high"]``). The binary
        is resolved against PATH via :func:`shutil.which`; remaining args
        are forwarded verbatim.
        """
        if isinstance(argv, str):
            argv = [argv]
        if not argv:
            raise AgentNotFoundError("empty argv")

        which_result = shutil.which(argv[0])
        if which_result is None:
            raise AgentNotFoundError(f"agent not on PATH: {argv[0]}")

        full_argv = [which_result, *argv[1:]]
        env = os.environ.copy()
        env["INVESTMENTS_ACTIVE_ACCOUNT"] = account
        env.setdefault("INVESTMENTS_DATA_ROOT", str(terminal_working_dir()))

        self._impl.spawn(
            argv=full_argv,
            cwd=str(terminal_working_dir()),
            env=env,
            cols=_DEFAULT_COLS,
            rows=_DEFAULT_ROWS,
        )
        self._spawned = True
        _active_sessions.add(self)

    def read_nonblocking(self, size: int = 4096) -> bytes:
        """Return up to ``size`` bytes from the PTY without blocking."""

        if not self._spawned:
            return b""
        return self._impl.read_nonblocking(size)

    def write(self, data: bytes) -> None:
        """Send raw bytes to the PTY's input. Silent no-op when closed."""

        if not self._spawned:
            return
        self._impl.write(data)

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY window to ``cols`` columns by ``rows`` rows."""

        if not self._spawned:
            return
        self._impl.resize(cols, rows)

    def close(self) -> None:
        """Terminate the child, escalating to kill after the timeout."""

        if self._spawned and self._impl.is_alive():
            self._impl.terminate()
            deadline = time.monotonic() + _TERMINATE_TIMEOUT_S
            while time.monotonic() < deadline:
                if not self._impl.is_alive():
                    break
                time.sleep(0.05)
            if self._impl.is_alive():
                self._impl.kill()
                # SIGKILL is asynchronous — give the kernel time to reap the
                # child before any caller checks is_alive(). Without this
                # spin, a test that calls close() then immediately asserts
                # not is_alive() can race the reaping and flake.
                kill_deadline = time.monotonic() + 1.0
                while time.monotonic() < kill_deadline and self._impl.is_alive():
                    time.sleep(0.02)
        _active_sessions.discard(self)

    def is_alive(self) -> bool:
        """``True`` while the underlying child process is still running."""

        if not self._spawned:
            return False
        return self._impl.is_alive()


_active_sessions: Set["TerminalSession"] = set()


def close_all_active() -> None:
    """Close every live :class:`TerminalSession`.

    Invoked from the FastAPI ``shutdown`` hook so Ctrl-C on uvicorn
    cannot leak PTY children.
    """

    for session in list(_active_sessions):
        try:
            session.close()
        except Exception:
            pass
