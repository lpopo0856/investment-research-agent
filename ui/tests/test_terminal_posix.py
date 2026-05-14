"""POSIX PTY tests for ui.terminal — skipped on win32."""

import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX PTY test")

from ui.terminal import AgentNotFoundError, TerminalSession, _active_sessions


# ---------------------------------------------------------------------------
# spawn with non-existent binary raises AgentNotFoundError
# ---------------------------------------------------------------------------

def test_spawn_nonexistent_binary_raises():
    session = TerminalSession()
    with pytest.raises(AgentNotFoundError):
        session.spawn("__no_such_binary_xyz__", "default")


# ---------------------------------------------------------------------------
# spawn bash, write, read, close
# ---------------------------------------------------------------------------

def test_spawn_bash_echo_hello():
    session = TerminalSession()
    session.spawn("bash", "default")
    assert session in _active_sessions

    # Give the shell a moment to start (macOS bash may run rc files first),
    # then send the command. Generous warmup keeps the test stable under
    # full-suite load where the event loop and shell startup contend.
    time.sleep(0.5)
    session.write(b"echo HELLO\n")

    # Poll for up to 5 seconds for the output to appear
    output = b""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        chunk = session.read_nonblocking(4096)
        output += chunk
        if b"HELLO" in output:
            break
        time.sleep(0.05)

    session.close()

    assert b"HELLO" in output, f"expected HELLO in PTY output, got {output!r}"
    assert not session.is_alive()
    assert session not in _active_sessions
