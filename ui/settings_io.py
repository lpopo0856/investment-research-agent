"""Read, preview, and atomically write SETTINGS.md for a given account.

Workflow: read_settings → build_diff (get token) → write_settings (consume token).
All path resolution goes through ui.accounts.resolve_account_path.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import ui.accounts as _accounts

# ---------------------------------------------------------------------------
# Pending-token store
# ---------------------------------------------------------------------------

_MAX_PENDING = 16
_TOKEN_TTL = 600  # seconds


@dataclass
class _Pending:
    account: str
    old: str
    new: str
    created_at: float  # time.monotonic()


_pending_tokens: dict[str, _Pending] = {}


def _evict_expired() -> None:
    now = time.monotonic()
    expired = [t for t, p in _pending_tokens.items() if now - p.created_at > _TOKEN_TTL]
    for t in expired:
        del _pending_tokens[t]


def _evict_oldest() -> None:
    if len(_pending_tokens) >= _MAX_PENDING:
        oldest = min(_pending_tokens, key=lambda t: _pending_tokens[t].created_at)
        del _pending_tokens[oldest]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _settings_path(account: str) -> tuple[Path, Path]:
    account_dir = _accounts.resolve_account_path(account)
    return account_dir, account_dir / "SETTINGS.md"


def _derive_token(old: str, new: str, account: str) -> str:
    payload = (old + "\0" + new + "\0" + account).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_settings(account: str) -> str:
    """Return UTF-8 content of SETTINGS.md for *account*.

    Raises FileNotFoundError if SETTINGS.md is absent.
    Raises ValueError if *account* name is invalid (from resolve_account_path).
    """
    _, settings_path = _settings_path(account)
    if not settings_path.exists():
        raise FileNotFoundError(
            f"SETTINGS.md not found for account {account!r}: {settings_path}"
        )
    return settings_path.read_text(encoding="utf-8")


def build_diff(account: str, new_content: str) -> dict[str, Any]:
    """Preview a proposed SETTINGS.md change; return token authorising the write.

    Returns dict with keys: old, new, unified_diff, token.
    Token expires after 600 s; pass it unchanged to write_settings.
    """
    _evict_expired()

    old = read_settings(account)
    token = _derive_token(old, new_content, account)
    unified_diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile="SETTINGS.md (current)",
            tofile="SETTINGS.md (proposed)",
        )
    )

    _evict_oldest()
    _pending_tokens[token] = _Pending(
        account=account, old=old, new=new_content, created_at=time.monotonic()
    )
    return {"old": old, "new": new_content, "unified_diff": unified_diff, "token": token}


def write_settings(account: str, new_content: str, token: str) -> dict[str, Any]:
    """Atomically write *new_content* to SETTINGS.md after validating *token*.

    Token validation re-derives the expected token from the current on-disk
    content; if the file changed since build_diff the re-derived token will
    differ and ValueError is raised.

    Creates a timestamped backup before writing; uses a temp-file + os.replace
    for atomicity.  Returns dict with key backup_path.

    Raises ValueError("settings token invalid or expired") on bad/stale token.
    """
    _evict_expired()

    account_dir, settings_path = _settings_path(account)
    current_old = read_settings(account)
    expected_token = _derive_token(current_old, new_content, account)

    if _pending_tokens.get(token) is None or expected_token != token:
        raise ValueError("settings token invalid or expired")

    # Backup
    utc_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = account_dir / f"SETTINGS.md.bak.{utc_ts}"
    n = 1
    while backup_path.exists():
        backup_path = account_dir / f"SETTINGS.md.bak.{utc_ts}_{n}"
        n += 1
    backup_path.write_text(current_old, encoding="utf-8")

    # Atomic replace
    tmp_path: str | None = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=account_dir, delete=False, suffix=".tmp"
        ) as tmp:
            tmp_path = tmp.name
            tmp.write(new_content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, settings_path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    _pending_tokens.pop(token, None)
    return {"backup_path": str(backup_path)}


# ---------------------------------------------------------------------------
# Section parsing (level-2 markdown headings, fence-aware)
# ---------------------------------------------------------------------------

def _parse_sections(content: str) -> tuple[str, list[dict[str, Any]]]:
    """Split *content* into preamble + ordered ``## `` sections.

    Lines beginning with ``## `` (level-2 headings) start a new section,
    regardless of fenced-code-block state — some files in this repo wrap
    the entire content in an outer ``` ```markdown ``` ``` fence for display,
    and a strict fence-aware parser would treat the whole file as preamble.
    The trade-off: a user who literally writes ``## foo`` inside a code
    block will see it become a section boundary; this is acceptable because
    the conflict is visible in the resulting textarea and recoverable.
    """
    lines = content.splitlines(keepends=True)

    heading_indices: list[int] = [
        i for i, line in enumerate(lines)
        if line.startswith("## ") and not line.startswith("### ")
    ]

    if not heading_indices:
        return content, []

    preamble = "".join(lines[: heading_indices[0]])
    sections: list[dict[str, Any]] = []
    for idx, start in enumerate(heading_indices):
        end = heading_indices[idx + 1] if idx + 1 < len(heading_indices) else len(lines)
        heading_text = lines[start].rstrip("\n").rstrip("\r")
        name = heading_text[3:].strip()
        body = "".join(lines[start:end])
        sections.append({"index": idx, "name": name, "body": body})

    return preamble, sections


def list_sections(account: str) -> dict[str, Any]:
    """Return ordered ``## `` sections for the account's SETTINGS.md.

    Shape: ``{"preamble": str, "sections": [{"index", "name", "body"}, ...]}``.
    If the file has no ``## `` sections, ``sections`` is empty and the entire
    file content is returned in ``preamble`` so callers can still display it.
    """
    content = read_settings(account)
    preamble, sections = _parse_sections(content)
    return {"preamble": preamble, "sections": sections}


def _rebuild_with_section(account: str, section_index: int, new_body: str) -> str:
    """Compose new full SETTINGS.md content with *section_index* replaced.

    Reads current on-disk content fresh so any unrelated section changed since
    list_sections still round-trips correctly through write_settings's TOCTOU
    token check.
    """
    parsed = list_sections(account)
    sections = parsed["sections"]
    if not (0 <= section_index < len(sections)):
        raise ValueError(f"section index out of range: {section_index}")

    new_sections = [dict(s) for s in sections]
    new_sections[section_index]["body"] = new_body
    return parsed["preamble"] + "".join(s["body"] for s in new_sections)


def build_section_diff(account: str, section_index: int, new_body: str) -> dict[str, Any]:
    """Preview a section-only edit; return a token authorising the write.

    The token covers the FULL file replacement (so write_settings's TOCTOU
    check still applies). The unified diff is similarly file-scoped — that
    way the user sees exactly which lines change before confirming.
    """
    new_content = _rebuild_with_section(account, section_index, new_body)
    return build_diff(account, new_content)


def write_section(
    account: str, section_index: int, new_body: str, token: str
) -> dict[str, Any]:
    """Atomically replace one ``## `` section in SETTINGS.md.

    Delegates to write_settings for atomic write + TOCTOU validation.
    """
    new_content = _rebuild_with_section(account, section_index, new_body)
    return write_settings(account, new_content, token)
