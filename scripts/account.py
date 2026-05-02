#!/usr/bin/env python3
"""
Account-resolution helper for the multi-account layout.

Resolves which account directory (under ``accounts/<name>/``) a script
should read SETTINGS.md and transactions.db from, and provides the
auto-migrate cutover that converts the legacy root layout
(SETTINGS.md / transactions.db / reports/ at repo root) into
``accounts/default/`` on first run.

Standalone module: stdlib only. Other scripts import it via the R-6
preamble::

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from account import autodetect_and_migrate_or_exit, add_account_args, resolve_account

CLI::

    python scripts/account.py --self-test     # run inline self-tests
    python scripts/account.py --detect        # print detect_legacy_layout()
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR: Path = REPO_ROOT / "accounts"
ACTIVE_POINTER: Path = ACCOUNTS_DIR / ".active"
BACKUP_DIR: Path = REPO_ROOT / ".pre-migrate-backup"
MANIFEST_NAME: str = "migration-manifest.json"

LEGACY_FILES: Tuple[str, ...] = (
    "SETTINGS.md",
    "transactions.db",
    "transactions.db.bak",
    "reports",
)

SHARED_ROOT_FILES: Tuple[str, ...] = (
    "market_data_cache.db",
    "market_data_cache.db-shm",
    "market_data_cache.db-wal",
)

NAME_REGEX = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

RESERVED_HARD = frozenset({"demo"})
RESERVED_SOFT = frozenset({"default"})

DEFAULT_ACCOUNT = "default"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class AccountNameError(ValueError):
    """Invalid account name (regex failure or reserved-name rejection)."""


class LegacyLayoutError(RuntimeError):
    """Legacy root layout detected; migration required before resolution."""


class NoAccountError(RuntimeError):
    """No account could be resolved (no pointer, no default, no legacy)."""


class MigrationError(RuntimeError):
    """Migration failure (verify mismatch, sub-process failure, etc)."""


# --------------------------------------------------------------------------- #
# AccountPaths dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AccountPaths:
    """Resolved on-disk paths for a single account."""

    name: str
    settings: Path
    db: Path
    reports_dir: Path
    cache: Path  # always REPO_ROOT/market_data_cache.db (shared)


def _paths_for(name: str) -> AccountPaths:
    """Build canonical AccountPaths for an account name (no I/O)."""
    base = _accounts_dir() / name
    return AccountPaths(
        name=name,
        settings=base / "SETTINGS.md",
        db=base / "transactions.db",
        reports_dir=base / "reports",
        cache=_repo_root() / "market_data_cache.db",
    )


# --------------------------------------------------------------------------- #
# Internal: dynamic root accessors (so self-tests can monkey-patch REPO_ROOT)
# --------------------------------------------------------------------------- #


def _repo_root() -> Path:
    return REPO_ROOT


def _accounts_dir() -> Path:
    return _repo_root() / "accounts"


def _active_pointer() -> Path:
    return _accounts_dir() / ".active"


def _backup_dir() -> Path:
    return _repo_root() / ".pre-migrate-backup"


# --------------------------------------------------------------------------- #
# Hash + content equivalence helpers
# --------------------------------------------------------------------------- #


def _sha256(path: Path) -> str:
    """Streaming sha256 of a file (raises if path is not a regular file)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _dir_contents(root: Path) -> List[Dict[str, object]]:
    """Recursive size+sha256 listing of files under ``root`` (sorted)."""
    out: List[Dict[str, object]] = []
    for sub in sorted(root.rglob("*")):
        if not sub.is_file():
            continue
        rel = sub.relative_to(root).as_posix()
        out.append(
            {
                "rel": rel,
                "size": sub.stat().st_size,
                "sha256": _sha256(sub),
            }
        )
    return out


def _content_equivalent(a: Path, b: Path) -> bool:
    """Return True iff the two paths are byte-for-byte equivalent.

    Files: equal size + equal sha256.
    Dirs:  same recursive contents (per _dir_contents).
    Mixed (one dir, one file): False.
    """
    if a.is_dir() and b.is_dir():
        return _dir_contents(a) == _dir_contents(b)
    if a.is_file() and b.is_file():
        if a.stat().st_size != b.stat().st_size:
            return False
        return _sha256(a) == _sha256(b)
    return False


# --------------------------------------------------------------------------- #
# Name validation, listing, account-of helper, pairing
# --------------------------------------------------------------------------- #


def validate_account_name(name: str, *, for_create: bool = False) -> None:
    """Raise AccountNameError if ``name`` is invalid.

    Always: must match NAME_REGEX.
    When for_create=True: RESERVED_HARD names are rejected outright.
    RESERVED_SOFT names are always allowed (the resolver / scaffold code
    decides whether the corresponding directory must already exist).
    """
    if not isinstance(name, str) or not NAME_REGEX.match(name):
        raise AccountNameError(
            f"invalid account name {name!r}: must match {NAME_REGEX.pattern}"
        )
    if for_create and name in RESERVED_HARD:
        raise AccountNameError(
            f"{name!r} is reserved for the demo fixture directory at repo "
            "root. Use 'demo/' directly with explicit --db/--settings."
        )


def list_accounts() -> List[str]:
    """Return sorted account directory names under accounts/.

    Excludes hidden entries (names starting with '.') and non-directories.
    """
    accounts = _accounts_dir()
    if not accounts.is_dir():
        return []
    out: List[str] = []
    for entry in accounts.iterdir():
        if entry.name.startswith("."):
            continue
        if not entry.is_dir():
            continue
        if not NAME_REGEX.match(entry.name):
            continue
        out.append(entry.name)
    out.sort()
    return out


def _account_of(path: Optional[Path]) -> Optional[str]:
    """Return the account name iff ``path`` is account-scoped under
    ``accounts/<name>/``. Returns None for any other path including
    root SETTINGS.md / transactions.db / demo/* / /tmp/* / non-repo paths.
    """
    if path is None:
        return None
    try:
        p = Path(path).resolve()
    except (OSError, RuntimeError):
        return None
    accounts = _accounts_dir().resolve()

    # Must be under accounts/.
    try:
        rel = p.relative_to(accounts)
    except ValueError:
        return None

    parts = rel.parts
    if not parts:
        return None
    name = parts[0]
    if name.startswith("."):
        return None
    if not NAME_REGEX.match(name):
        return None
    return name


def check_pairing(db: Optional[Path], settings: Optional[Path]) -> Optional[str]:
    """Return a warning string if both paths are account-scoped and disagree
    on account name, else None (escape-hatch mode: at least one path is not
    account-scoped, so no warning).
    """
    db_acct = _account_of(db)
    settings_acct = _account_of(settings)
    if db_acct is None or settings_acct is None:
        return None
    if db_acct != settings_acct:
        return (
            f"--db is account '{db_acct}' but --settings is account "
            f"'{settings_acct}'"
        )
    return None


# Plan compatibility alias.
_check_pairing = check_pairing


# --------------------------------------------------------------------------- #
# Active pointer (atomic read/write)
# --------------------------------------------------------------------------- #


def read_active_pointer() -> Optional[str]:
    """Return the account name in accounts/.active, or None if absent/empty
    or invalid (caller should treat invalid as 'no pointer').

    Security: refuses symlinks. accounts/.active must be a regular file.
    """
    ptr = _active_pointer()
    if not ptr.exists():
        return None
    if ptr.is_symlink():
        sys.stderr.write(
            "Refusing to read accounts/.active: it is a symlink. "
            "Remove it manually if intentional.\n"
        )
        return None
    try:
        raw = ptr.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    if not NAME_REGEX.match(raw):
        return None
    return raw


def write_active_pointer(name: str) -> None:
    """Atomically write ``name`` to accounts/.active.

    Validates against NAME_REGEX. Refuses RESERVED_HARD outright. Allows
    RESERVED_SOFT iff the corresponding accounts/<name>/ directory already
    exists (the only legitimate reason to point at a soft-reserved name).
    """
    if not isinstance(name, str) or not NAME_REGEX.match(name):
        raise AccountNameError(
            f"invalid account name {name!r}: must match {NAME_REGEX.pattern}"
        )
    if name in RESERVED_HARD:
        raise AccountNameError(
            f"{name!r} is reserved and cannot be the active account"
        )
    accounts = _accounts_dir()
    if name in RESERVED_SOFT and not (accounts / name).is_dir():
        raise AccountNameError(
            f"{name!r} is reserved-soft; accounts/{name}/ must exist before "
            "writing the active pointer"
        )

    accounts.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=".active.", dir=str(accounts))
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(name + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, _active_pointer())
        # Durably commit the rename in the parent directory so the cutover
        # sentinel survives power loss between rename and next metadata flush.
        try:
            dir_fd = os.open(str(accounts), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- #
# create_account_scaffold
# --------------------------------------------------------------------------- #


def create_account_scaffold(name: str) -> AccountPaths:
    """Create accounts/<name>/ + reports/, copy SETTINGS.example.md, init
    transactions.db. Idempotent: if accounts/<name>/ already exists, returns
    its AccountPaths without overwriting anything.
    """
    validate_account_name(name, for_create=True)
    paths = _paths_for(name)
    base = paths.settings.parent

    if base.is_dir():
        return paths

    base.mkdir(parents=True, exist_ok=False)
    paths.reports_dir.mkdir(parents=True, exist_ok=True)

    # Copy SETTINGS.example.md if available.
    example = _repo_root() / "SETTINGS.example.md"
    if example.is_file():
        shutil.copy2(example, paths.settings)

    # Initialize transactions.db via the canonical entry-point. We import
    # lazily to avoid pulling transactions.py into self-tests (which run
    # without sqlite-dependent fixtures).
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from transactions import db_init  # type: ignore[import-not-found]
    except ImportError:
        # Self-test contexts run without sqlite-dependent fixtures. The CLI
        # path (account create) cannot reach this branch because the same
        # import is used elsewhere; surfacing here as None is intentional.
        return paths
    # db_init failures (sqlite errors, permission denied, schema bugs) MUST
    # surface so the user knows the scaffold is incomplete. Do not swallow.
    db_init(paths.db)

    return paths


# --------------------------------------------------------------------------- #
# Layout detection
# --------------------------------------------------------------------------- #


def _has_root_legacy_files() -> bool:
    """True iff SETTINGS.md or transactions.db exists at the repo root."""
    root = _repo_root()
    return (root / "SETTINGS.md").exists() or (root / "transactions.db").exists()


def _has_any_legacy_root_path() -> bool:
    """True iff ANY LEGACY_FILES path exists at the repo root."""
    root = _repo_root()
    return any((root / n).exists() for n in LEGACY_FILES)


def _populated_account_dirs() -> List[str]:
    """Return regex-valid sub-dirs under accounts/ (excluding hidden)."""
    accounts = _accounts_dir()
    if not accounts.is_dir():
        return []
    out: List[str] = []
    for entry in accounts.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_dir() and NAME_REGEX.match(entry.name):
            out.append(entry.name)
    out.sort()
    return out


def detect_legacy_layout() -> str:
    """Classify the on-disk layout. Returns one of:

      - "clean":               no migration needed
      - "migrate":             root legacy files exist and accounts/ is
                               absent or has no regex-valid sub-dirs
      - "partial":             mixed / inconsistent state (root legacy +
                               custom accounts/, empty accounts/, stale
                               .active pointer alongside root files, etc.)
      - "demo_only_at_root":   only demo/ is present (no root SETTINGS.md
                               or transactions.db) — treat as new-user clean
    """
    root = _repo_root()
    accounts = _accounts_dir()
    has_root_settings = (root / "SETTINGS.md").exists()
    has_root_db = (root / "transactions.db").exists()
    has_root_legacy = has_root_settings or has_root_db
    accounts_exists = accounts.is_dir()
    sub_dirs = _populated_account_dirs() if accounts_exists else []
    pointer_present = _active_pointer().exists()
    pointer_value = read_active_pointer() if pointer_present else None
    pointer_target_exists = (
        bool(pointer_value)
        and (accounts / pointer_value).is_dir()
        if pointer_value
        else False
    )

    # Stale pointer: pointer present but target missing (with or without
    # root files). This is "partial" — the system has begun multi-account
    # mode but the pointer is broken.
    if pointer_present:
        if pointer_value is None or not pointer_target_exists:
            return "partial"
        # Pointer present and valid + root legacy files still present →
        # finish-cleanup hook handles this case; for the detector that's
        # "partial" from the migration-prompt point of view.
        if has_root_legacy:
            return "partial"

    # Empty accounts/ directory + root legacy files = genuine half-started
    # migration → "partial". Empty accounts/ alone (no root legacy) is benign
    # — the user might have created the dir manually; let it fall through to
    # the demo-only / clean detection below.
    if accounts_exists and not sub_dirs and has_root_legacy:
        return "partial"

    # Root legacy files + at least one custom accounts/<x>/ → partial.
    if has_root_legacy and sub_dirs and DEFAULT_ACCOUNT not in sub_dirs:
        return "partial"

    # accounts/default/ already populated → clean (regardless of whether
    # there's lingering root content; the post-pointer cleanup hook handles
    # that path; the detector itself reports clean).
    if DEFAULT_ACCOUNT in sub_dirs:
        # If root legacy files also exist, the cleanup hook will run.
        # Detector still reports clean: the autodetect hook checks the
        # finish-cleanup branch first.
        return "clean"

    # Migrate path: root legacy files exist, no accounts/ sub-dirs.
    if has_root_legacy and not sub_dirs:
        return "migrate"

    # Demo-only / new-user path: no root legacy, no accounts/ sub-dirs,
    # demo/ may or may not be present.
    demo_settings = (root / "demo" / "SETTINGS.md").exists()
    if not has_root_legacy and not sub_dirs and demo_settings:
        return "demo_only_at_root"

    return "clean"


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #


def add_account_args(parser: argparse.ArgumentParser) -> None:
    """Add ``--account NAME`` to a parser. Idempotent (skips if present)."""
    for action in parser._actions:  # type: ignore[attr-defined]
        if "--account" in getattr(action, "option_strings", []):
            return
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        metavar="NAME",
        help="Account name under accounts/<name>/. "
        "Defaults to accounts/.active or 'default'.",
    )


def _explicit(value: object) -> bool:
    """Sentinel test: arg was set by the user (not the CLI default None)."""
    return value is not None


def resolve_account(args: argparse.Namespace) -> AccountPaths:
    """Resolve account paths from parsed args using the documented
    precedence (Phase 1 §resolve_account()):

      1. Explicit --db AND --settings → use them as-is. Account name
         derived via _account_of(); falls back to "<custom>" if either path
         is non-account-scoped.
      2. --account NAME → derive from accounts/<NAME>/. Validate name;
         error if dir absent.
      3. accounts/.active → if present and target dir exists, use it;
         if pointer exists but target missing, raise NoAccountError.
      4. accounts/default/ exists → use 'default'.
      5. Legacy root layout → raise LegacyLayoutError.
      6. Else → raise NoAccountError.

    Per-flag override: explicit args.db replaces the resolved db (and
    likewise for settings) without rejecting the rest.
    """
    explicit_db = _explicit(getattr(args, "db", None))
    explicit_settings = _explicit(getattr(args, "settings", None))
    explicit_account = _explicit(getattr(args, "account", None))

    if explicit_db and explicit_settings:
        db_path = Path(getattr(args, "db"))
        settings_path = Path(getattr(args, "settings"))
        db_acct = _account_of(db_path)
        settings_acct = _account_of(settings_path)
        if db_acct is not None and settings_acct is not None and db_acct == settings_acct:
            name = db_acct
        else:
            name = "<custom>"
        if name == "<custom>":
            # Reports go alongside the explicitly-supplied db so that a
            # user pointing --db at /tmp/foo/transactions.db gets reports at
            # /tmp/foo/reports, not the live repo's reports directory.
            custom_reports = db_path.parent / "reports"
        else:
            custom_reports = _accounts_dir() / name / "reports"
        return AccountPaths(
            name=name,
            settings=settings_path,
            db=db_path,
            reports_dir=custom_reports,
            cache=_repo_root() / "market_data_cache.db",
        )

    # Helper: apply per-flag overrides on top of a resolved AccountPaths.
    def _apply_overrides(base: AccountPaths) -> AccountPaths:
        db = Path(getattr(args, "db")) if explicit_db else base.db
        settings = (
            Path(getattr(args, "settings")) if explicit_settings else base.settings
        )
        return AccountPaths(
            name=base.name,
            settings=settings,
            db=db,
            reports_dir=base.reports_dir,
            cache=base.cache,
        )

    accounts = _accounts_dir()

    if explicit_account:
        name = getattr(args, "account")
        validate_account_name(name)
        if not (accounts / name).is_dir():
            raise NoAccountError(
                f"--account {name!r}: accounts/{name}/ does not exist. "
                f"Run 'transactions.py account create {name}'."
            )
        return _apply_overrides(_paths_for(name))

    pointer = read_active_pointer()
    if pointer is not None:
        if (accounts / pointer).is_dir():
            return _apply_overrides(_paths_for(pointer))
        raise NoAccountError(
            f"accounts/.active points to {pointer!r} but accounts/{pointer}/ "
            "does not exist. Run 'transactions.py account use <name>' or "
            "remove accounts/.active."
        )

    if (accounts / DEFAULT_ACCOUNT).is_dir():
        return _apply_overrides(_paths_for(DEFAULT_ACCOUNT))

    if _has_root_legacy_files():
        raise LegacyLayoutError(
            "Legacy single-account root layout detected. Run "
            "'python scripts/transactions.py account migrate --yes' "
            "or invoke any script interactively to start the migration."
        )

    raise NoAccountError(
        "No account resolved. Run 'python scripts/transactions.py "
        "account create <name>' to create one, or 'account use <name>' "
        "to select an existing account."
    )


# --------------------------------------------------------------------------- #
# Manifest + verify_layout
# --------------------------------------------------------------------------- #


def _build_manifest(sources: List[str]) -> Dict[str, object]:
    """Build the migration-manifest dict (no I/O beyond hashing inputs)."""
    root = _repo_root()
    moves: List[Dict[str, object]] = []
    for src in sources:
        src_path = root / src
        if not src_path.exists():
            continue
        target_rel = f"accounts/{DEFAULT_ACCOUNT}/{src}"
        if src_path.is_dir():
            moves.append(
                {
                    "src": src,
                    "target": target_rel + "/",
                    "kind": "dir",
                    "contents": _dir_contents(src_path),
                }
            )
        else:
            moves.append(
                {
                    "src": src,
                    "target": target_rel,
                    "kind": "file",
                    "size": src_path.stat().st_size,
                    "sha256": _sha256(src_path),
                }
            )
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "pre-migrate",
        "moves": moves,
    }


def verify_layout(manifest_path: Path) -> List[str]:
    """Return list of error strings (empty if all good).

    Iterates ``manifest['moves']``; for each entry, asserts the target file
    exists with matching size + sha256, or for dir entries that each
    listed sub-file exists with matching size + sha256.
    """
    errors: List[str] = []
    if not manifest_path.is_file():
        return [f"manifest not found: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"manifest unreadable: {manifest_path}: {exc}"]

    moves = manifest.get("moves", [])
    if not isinstance(moves, list):
        return ["manifest 'moves' is not a list"]

    root = _repo_root()
    for entry in moves:
        target_str = entry.get("target", "")
        if not isinstance(target_str, str) or not target_str:
            errors.append(f"manifest entry missing target: {entry!r}")
            continue
        target = root / target_str.rstrip("/")
        kind = entry.get("kind", "file")
        if kind == "dir":
            if not target.is_dir():
                errors.append(f"target dir missing: {target}")
                continue
            contents = entry.get("contents", [])
            if not isinstance(contents, list):
                errors.append(f"manifest 'contents' for {target} is not a list")
                continue
            for sub in contents:
                rel = sub.get("rel")
                size = sub.get("size")
                sha = sub.get("sha256")
                if not (isinstance(rel, str) and isinstance(size, int) and isinstance(sha, str)):
                    errors.append(f"bad sub-entry in {target}: {sub!r}")
                    continue
                f = target / rel
                if not f.is_file():
                    errors.append(f"missing: {f}")
                    continue
                if f.stat().st_size != size:
                    errors.append(f"size mismatch: {f}")
                    continue
                if _sha256(f) != sha:
                    errors.append(f"sha256 mismatch: {f}")
        else:
            size = entry.get("size")
            sha = entry.get("sha256")
            if not target.is_file():
                errors.append(f"target file missing: {target}")
                continue
            if isinstance(size, int) and target.stat().st_size != size:
                errors.append(f"size mismatch: {target}")
                continue
            if isinstance(sha, str) and _sha256(target) != sha:
                errors.append(f"sha256 mismatch: {target}")
    return errors


# --------------------------------------------------------------------------- #
# .gitignore patcher
# --------------------------------------------------------------------------- #


def _patch_gitignore() -> None:
    """Append-only update to .gitignore (idempotent)."""
    gi = _repo_root() / ".gitignore"
    desired = [
        ".pre-migrate-backup/",
        "accounts/.active",
        "accounts/*/SETTINGS.md",
        "accounts/*/transactions.db.bak",
    ]
    existing: List[str] = []
    if gi.is_file():
        existing = gi.read_text(encoding="utf-8").splitlines()
    existing_set = {line.strip() for line in existing if line.strip()}
    additions = [p for p in desired if p not in existing_set]
    if not additions:
        return
    with open(gi, "a", encoding="utf-8") as fh:
        if existing and not (existing[-1].strip() == "" if existing else True):
            fh.write("\n")
        fh.write("# multi-account layout\n")
        for p in additions:
            fh.write(p + "\n")


# --------------------------------------------------------------------------- #
# Migration executor
# --------------------------------------------------------------------------- #


def _execute_migration() -> None:
    """The atomic cutover sequence (per plan §Phase 4 step 8-15).

    Pre-conditions: caller has already cleared TTY guard, partial-state
    refusal, and the [y/N] prompt.
    """
    root = _repo_root()
    target_dir = _accounts_dir() / DEFAULT_ACCOUNT
    backup = _backup_dir()
    sources = [s for s in LEGACY_FILES if (root / s).exists()]

    # Defense-in-depth: refuse if the backup directory already has staged
    # legacy files. The public prompt_and_migrate() also enforces this at
    # the backup-root level, but a direct caller of _execute_migration must
    # not silently overwrite a previous backup's contents.
    if any((backup / s).exists() for s in LEGACY_FILES):
        raise MigrationError(
            "backup destination not empty; refuse to overwrite "
            "existing .pre-migrate-backup/ contents"
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "reports").mkdir(parents=True, exist_ok=True)
    backup.mkdir(parents=True, exist_ok=True)

    # 1. Copy backup snapshot first (defensive).
    for src in sources:
        src_path = root / src
        if src_path.is_dir():
            dst = backup / src
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src_path, dst)
        else:
            shutil.copy2(src_path, backup / src)

    # 2. Build + write manifest.
    manifest = _build_manifest(sources)
    manifest_path = backup / MANIFEST_NAME
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())

    # 3. Copy sources into accounts/default/.
    for src in sources:
        src_path = root / src
        dst = target_dir / src
        if src_path.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src_path, dst)
        else:
            shutil.copy2(src_path, dst)

    # 4. verify_layout (manifest-driven).
    errors = verify_layout(manifest_path)
    if errors:
        # Revert: remove accounts/default and pointer (root files intact).
        _rollback_pre_cutover()
        for e in errors:
            sys.stderr.write(f"verify_layout: {e}\n")
        raise MigrationError(
            "Migration aborted before commit. Original layout intact at "
            "root. Backup preserved at .pre-migrate-backup/."
        )

    # 5. DB replay verify via subprocess.
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(_repo_root() / "scripts" / "transactions.py"),
                "verify",
                "--account",
                DEFAULT_ACCOUNT,
            ],
            cwd=str(_repo_root()),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        _rollback_pre_cutover()
        raise MigrationError(f"verify subprocess failed to launch: {exc}") from exc
    if completed.returncode != 0:
        _rollback_pre_cutover()
        sys.stderr.write(completed.stdout or "")
        sys.stderr.write(completed.stderr or "")
        raise MigrationError(
            "Migration aborted before commit. Original layout intact at "
            "root. Backup preserved at .pre-migrate-backup/."
        )

    # 6. CUTOVER SENTINEL: atomic pointer write.
    write_active_pointer(DEFAULT_ACCOUNT)

    # 7. Patch .gitignore.
    _patch_gitignore()

    # 8. Delete root files (cleanup phase).
    for src in sources:
        p = root / src
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            os.unlink(p)

    print(f"Migrated to accounts/{DEFAULT_ACCOUNT}/. Continuing original command...")


def _rollback_pre_cutover() -> None:
    """Remove accounts/default/ and accounts/.active iff they exist
    (only safe before cutover sentinel)."""
    target = _accounts_dir() / DEFAULT_ACCOUNT
    pointer = _active_pointer()
    if target.exists():
        try:
            shutil.rmtree(target)
        except OSError:
            pass
    if pointer.exists():
        try:
            pointer.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# prompt_and_migrate / finish_migration_cleanup / autodetect entry-point
# --------------------------------------------------------------------------- #


_MIGRATE_PLAN_TEXT = (
    "Migrating to multi-account layout:\n"
    "  SETTINGS.md       -> accounts/default/SETTINGS.md\n"
    "  transactions.db   -> accounts/default/transactions.db\n"
    "  transactions.db.bak (if present) -> accounts/default/transactions.db.bak\n"
    "  reports/          -> accounts/default/reports/\n"
    "Backup of originals will be saved to .pre-migrate-backup/.\n"
    "market_data_cache.db is SHARED across accounts and will NOT be moved.\n"
)


def prompt_and_migrate(*, assume_yes: bool = False) -> None:
    """Top-of-main hook for entry-points (interactive variant).

    Order: detector → tty guard → backup-refusal → partial refusal → plan
    print → [y/N] → executor.
    """
    layout = detect_legacy_layout()
    if layout == "clean":
        return
    if layout == "demo_only_at_root":
        return
    if layout == "partial":
        sys.stderr.write(
            "Partial / inconsistent layout detected. Cannot auto-migrate.\n"
            "  - If you have legacy root files AND a custom accounts/ "
            "directory: manual reconciliation required.\n"
            "  - If accounts/ is empty: 'rmdir accounts' before migration.\n"
            "  - If accounts/.active points to a missing dir: remove it or "
            "run 'transactions.py account use <name>'.\n"
        )
        sys.exit(1)
    if layout != "migrate":
        return

    # TTY guard (R-2) — must come BEFORE backup-refusal so that non-tty
    # callers (CI / agents) get the actionable "use --yes" message rather
    # than a stale-backup message that they cannot resolve.
    if not assume_yes and not sys.stdin.isatty():
        sys.stderr.write(
            "Non-interactive shell: cannot prompt for migration.\n"
            "Run: python scripts/transactions.py account migrate --yes\n"
        )
        sys.exit(2)

    # Pre-existing backup refusal (R-4).
    backup = _backup_dir()
    if backup.exists():
        ts = "(no manifest found; manually inspect)"
        manifest_path = backup / MANIFEST_NAME
        if manifest_path.is_file():
            try:
                m = json.loads(manifest_path.read_text(encoding="utf-8"))
                ts = m.get("timestamp_utc", ts)
            except (OSError, json.JSONDecodeError):
                pass
        sys.stderr.write(
            f"Pre-existing backup at .pre-migrate-backup/ from {ts}.\n"
            "Either move it aside (mv .pre-migrate-backup "
            ".pre-migrate-backup-<date>) or delete it, then re-run.\n"
        )
        sys.exit(1)

    # Print plan.
    sys.stdout.write(_MIGRATE_PLAN_TEXT)
    sys.stdout.flush()

    if not assume_yes:
        sys.stdout.write("Migrate? [y/N]: ")
        sys.stdout.flush()
        try:
            answer = sys.stdin.readline().strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            sys.stderr.write("Aborted. No filesystem changes.\n")
            sys.exit(1)

    try:
        _execute_migration()
    except MigrationError as exc:
        sys.stderr.write(f"{exc}\n")
        sys.exit(1)


def finish_migration_cleanup() -> None:
    """Recovery hook. Idempotent — only deletes content-equivalent files.

    Two states trigger cleanup:
      1. Post-cutover cleanup: accounts/default/ populated AND
         accounts/.active == 'default' AND root legacy files present.
         A previous run died between pointer-write and delete-from-root.
      2. Strand-state recovery: accounts/default/ populated AND no
         accounts/.active pointer AND root legacy files present.
         A previous run of _execute_migration died between verify and
         pointer-write. Content-equivalence + manifest both validated;
         we write the pointer and delete root.
    """
    pointer = _active_pointer()
    target_dir = _accounts_dir() / DEFAULT_ACCOUNT
    root = _repo_root()
    has_root_legacy = any((root / s).exists() for s in LEGACY_FILES)
    pointer_exists = pointer.exists()

    if pointer_exists:
        active = read_active_pointer()
        if active != DEFAULT_ACCOUNT:
            return
        if not target_dir.is_dir():
            return
        is_strand = False
    else:
        # Strand state: no pointer + populated default + root legacy still present.
        if not (target_dir.is_dir() and has_root_legacy):
            return
        sys.stderr.write(
            "Strand state detected: accounts/default/ populated but "
            "accounts/.active is missing. Validating content equivalence "
            "before completing migration...\n"
        )
        is_strand = True
    # First pass: validate content equivalence for every still-present root.
    for name in LEGACY_FILES:
        rp = root / name
        if not rp.exists():
            continue
        tp = target_dir / name
        # Security: refuse if either side is a symlink. A symlink swap can
        # trick content-equivalence into accepting a deletion that targets
        # the wrong file.
        if rp.is_symlink() or (tp.exists() and tp.is_symlink()):
            sys.stderr.write(
                f"Cleanup refused: symlink detected at "
                f"{rp if rp.is_symlink() else tp}. Manual review required.\n"
            )
            sys.exit(2)
        if not tp.exists():
            sys.stderr.write(
                f"Cleanup refused: root '{name}' exists but "
                f"accounts/{DEFAULT_ACCOUNT}/{name} does not. "
                "Manual review required.\n"
            )
            sys.exit(2)
        if not _content_equivalent(rp, tp):
            sys.stderr.write(
                f"Cleanup refused: root '{name}' differs from "
                f"accounts/{DEFAULT_ACCOUNT}/{name}. Manual review required.\n"
                "  - If the root copy is canonical, copy it over the "
                "account copy and re-run cleanup.\n"
                "  - If the account copy is canonical, delete the root "
                "copy manually.\n"
            )
            sys.exit(2)
    # Strand recovery: content-equivalence passed; complete the cutover by
    # writing the pointer NOW (before deletion). Order matters: pointer must
    # be durable on disk before we delete root files.
    if is_strand:
        write_active_pointer(DEFAULT_ACCOUNT)
        sys.stderr.write(
            "Strand recovery: wrote accounts/.active = default. "
            "Proceeding to root cleanup.\n"
        )
    # Second pass: delete (only after every check passed and pointer is set).
    deleted_any = False
    for name in LEGACY_FILES:
        rp = root / name
        if rp.is_dir():
            shutil.rmtree(rp)
            deleted_any = True
        elif rp.exists():
            os.unlink(rp)
            deleted_any = True
    if deleted_any:
        sys.stderr.write("Migration cleanup completed. Root legacy files removed.\n")


def autodetect_and_migrate_or_exit() -> None:
    """The single entry-point hook. Composition:

      1. If pointer exists and root legacy files still present →
         finish_migration_cleanup() and return.
      2. Else prompt_and_migrate().
    """
    if _active_pointer().exists() and _has_any_legacy_root_path():
        finish_migration_cleanup()
        return
    prompt_and_migrate()


# --------------------------------------------------------------------------- #
# Inline self-tests
# --------------------------------------------------------------------------- #


class _RepoRootPatch:
    """Context manager: temporarily redirect REPO_ROOT to a tmp dir."""

    def __init__(self, new_root: Path) -> None:
        self.new_root = Path(new_root).resolve()
        self._saved: Dict[str, Path] = {}

    def __enter__(self) -> "_RepoRootPatch":
        global REPO_ROOT, ACCOUNTS_DIR, ACTIVE_POINTER, BACKUP_DIR
        self._saved["REPO_ROOT"] = REPO_ROOT
        self._saved["ACCOUNTS_DIR"] = ACCOUNTS_DIR
        self._saved["ACTIVE_POINTER"] = ACTIVE_POINTER
        self._saved["BACKUP_DIR"] = BACKUP_DIR
        REPO_ROOT = self.new_root
        ACCOUNTS_DIR = self.new_root / "accounts"
        ACTIVE_POINTER = ACCOUNTS_DIR / ".active"
        BACKUP_DIR = self.new_root / ".pre-migrate-backup"
        return self

    def __exit__(self, *exc: object) -> None:
        global REPO_ROOT, ACCOUNTS_DIR, ACTIVE_POINTER, BACKUP_DIR
        REPO_ROOT = self._saved["REPO_ROOT"]
        ACCOUNTS_DIR = self._saved["ACCOUNTS_DIR"]
        ACTIVE_POINTER = self._saved["ACTIVE_POINTER"]
        BACKUP_DIR = self._saved["BACKUP_DIR"]


def _self_test() -> int:
    """Run inline self-tests. Print PASS / FAIL: <reason>. Exit 0/1."""
    failures: List[str] = []

    def _ok(label: str) -> None:
        print(f"PASS: {label}")

    def _fail(label: str, why: str) -> None:
        failures.append(f"{label}: {why}")
        print(f"FAIL: {label}: {why}", file=sys.stderr)

    # Test 1: detect_legacy_layout clean (accounts/default/ populated).
    with tempfile.TemporaryDirectory() as td:
        with _RepoRootPatch(Path(td)) as ctx:
            (Path(td) / "accounts" / "default" / "reports").mkdir(parents=True)
            (Path(td) / "accounts" / "default" / "SETTINGS.md").write_text("x")
            (Path(td) / "accounts" / "default" / "transactions.db").write_text("x")
            got = detect_legacy_layout()
            if got != "clean":
                _fail("detect_clean", f"expected 'clean', got {got!r}")
            else:
                _ok("detect_clean")

    # Test 2: detect_legacy_layout migrate.
    with tempfile.TemporaryDirectory() as td:
        with _RepoRootPatch(Path(td)):
            (Path(td) / "SETTINGS.md").write_text("settings")
            (Path(td) / "transactions.db").write_text("db")
            got = detect_legacy_layout()
            if got != "migrate":
                _fail("detect_migrate", f"expected 'migrate', got {got!r}")
            else:
                _ok("detect_migrate")

    # Test 3: detect_legacy_layout demo_only_at_root.
    with tempfile.TemporaryDirectory() as td:
        with _RepoRootPatch(Path(td)):
            demo = Path(td) / "demo"
            demo.mkdir()
            (demo / "SETTINGS.md").write_text("demo")
            (demo / "transactions.db").write_text("demo")
            got = detect_legacy_layout()
            if got != "demo_only_at_root":
                _fail(
                    "detect_demo_only",
                    f"expected 'demo_only_at_root', got {got!r}",
                )
            else:
                _ok("detect_demo_only")

    # Test 4: detect_legacy_layout partial (root + half-empty accounts/foo/).
    with tempfile.TemporaryDirectory() as td:
        with _RepoRootPatch(Path(td)):
            (Path(td) / "SETTINGS.md").write_text("s")
            (Path(td) / "transactions.db").write_text("d")
            (Path(td) / "accounts" / "foo").mkdir(parents=True)
            got = detect_legacy_layout()
            if got != "partial":
                _fail("detect_partial", f"expected 'partial', got {got!r}")
            else:
                _ok("detect_partial")

    # Test 5: detect_legacy_layout stale-pointer (pointer to missing dir).
    with tempfile.TemporaryDirectory() as td:
        with _RepoRootPatch(Path(td)):
            (Path(td) / "accounts").mkdir()
            (Path(td) / "accounts" / ".active").write_text("ghost\n")
            got = detect_legacy_layout()
            if got != "partial":
                _fail("detect_stale_pointer", f"expected 'partial', got {got!r}")
            else:
                _ok("detect_stale_pointer")

    # Test 6: _account_of parametrized.
    with tempfile.TemporaryDirectory() as td:
        with _RepoRootPatch(Path(td)):
            (Path(td) / "accounts" / "ira").mkdir(parents=True)
            (Path(td) / "accounts" / "ira" / "SETTINGS.md").write_text("x")
            cases = [
                (Path(td) / "accounts" / "ira" / "SETTINGS.md", "ira"),
                (Path("/tmp/foo.db"), None),
                (Path(td) / "SETTINGS.md", None),
                (Path(td) / "demo" / "SETTINGS.md", None),
                (Path(td) / "accounts" / "ira" / "reports" / "x.html", "ira"),
            ]
            for p, want in cases:
                got = _account_of(p)
                if got != want:
                    _fail("account_of", f"{p}: expected {want!r}, got {got!r}")
                    break
            else:
                _ok("account_of")

    # Test 7: check_pairing matching/mismatch/escape.
    with tempfile.TemporaryDirectory() as td:
        with _RepoRootPatch(Path(td)):
            (Path(td) / "accounts" / "a").mkdir(parents=True)
            (Path(td) / "accounts" / "b").mkdir(parents=True)
            db_a = Path(td) / "accounts" / "a" / "transactions.db"
            set_a = Path(td) / "accounts" / "a" / "SETTINGS.md"
            db_a.write_text("d")
            set_a.write_text("s")
            db_b = Path(td) / "accounts" / "b" / "transactions.db"
            set_b = Path(td) / "accounts" / "b" / "SETTINGS.md"
            db_b.write_text("d")
            set_b.write_text("s")

            ok = True
            if check_pairing(db_a, set_a) is not None:
                _fail("check_pairing_match", "expected None for matched pair")
                ok = False
            warn = check_pairing(db_a, set_b)
            if warn is None or "a" not in warn or "b" not in warn:
                _fail("check_pairing_mismatch", f"unexpected warn: {warn!r}")
                ok = False
            if check_pairing(Path("/tmp/x.db"), set_a) is not None:
                _fail("check_pairing_escape", "expected None for non-account path")
                ok = False
            if ok:
                _ok("check_pairing")

    # Test 8: validate_account_name.
    try:
        validate_account_name("Bad-Name")
        _fail("validate_BadName", "should have raised")
    except AccountNameError:
        _ok("validate_BadName")

    try:
        validate_account_name("1foo")  # leading digit allowed by regex
        _ok("validate_1foo_allowed")
    except AccountNameError as exc:
        _fail("validate_1foo_allowed", f"unexpected reject: {exc}")

    try:
        validate_account_name("demo", for_create=True)
        _fail("validate_demo_create", "should have raised")
    except AccountNameError:
        _ok("validate_demo_create")

    # Reading 'demo' (not for_create) is fine — name is regex-valid.
    try:
        validate_account_name("demo")
        _ok("validate_demo_read")
    except AccountNameError as exc:
        _fail("validate_demo_read", f"unexpected reject: {exc}")

    for name in ("default", "ira", "tax-ira"):
        try:
            validate_account_name(name)
        except AccountNameError as exc:
            _fail(f"validate_{name}", f"unexpected reject: {exc}")
            break
    else:
        _ok("validate_default_ira_taxira")

    # Test 9: write_active_pointer + read_active_pointer round-trip.
    with tempfile.TemporaryDirectory() as td:
        with _RepoRootPatch(Path(td)):
            (Path(td) / "accounts" / "foo").mkdir(parents=True)
            try:
                write_active_pointer("foo")
            except Exception as exc:
                _fail("active_pointer_write", f"unexpected error: {exc}")
            else:
                got = read_active_pointer()
                if got != "foo":
                    _fail("active_pointer_round_trip", f"got {got!r}")
                else:
                    _ok("active_pointer_round_trip")

            # Refuses 'demo' for create context (here through write_active_pointer
            # which always rejects RESERVED_HARD).
            try:
                write_active_pointer("demo")
                _fail("active_pointer_refuses_demo", "should have raised")
            except AccountNameError:
                _ok("active_pointer_refuses_demo")

            # Reading remains unaffected — pointer still says 'foo'.
            if read_active_pointer() != "foo":
                _fail("active_pointer_unchanged_after_reject", "pointer mutated")
            else:
                _ok("active_pointer_unchanged_after_reject")

    # Test 10: verify_layout pass + fail.
    with tempfile.TemporaryDirectory() as td:
        with _RepoRootPatch(Path(td)):
            root = Path(td)
            (root / "accounts" / "default").mkdir(parents=True)
            f1 = root / "accounts" / "default" / "SETTINGS.md"
            f1.write_text("hello")
            manifest = {
                "timestamp_utc": "2026-05-02T00:00:00+00:00",
                "moves": [
                    {
                        "src": "SETTINGS.md",
                        "target": "accounts/default/SETTINGS.md",
                        "kind": "file",
                        "size": f1.stat().st_size,
                        "sha256": _sha256(f1),
                    }
                ],
            }
            mp = root / "manifest.json"
            mp.write_text(json.dumps(manifest), encoding="utf-8")
            errs = verify_layout(mp)
            if errs:
                _fail("verify_layout_pass", f"unexpected errors: {errs}")
            else:
                _ok("verify_layout_pass")

            # Tamper: change file content (size differs).
            f1.write_text("HELLO_LONGER")
            errs = verify_layout(mp)
            if not errs:
                _fail("verify_layout_fail", "expected at least one error")
            else:
                _ok("verify_layout_fail")

            # Missing target.
            f1.unlink()
            errs = verify_layout(mp)
            if not any("missing" in e for e in errs):
                _fail("verify_layout_missing", f"errors: {errs}")
            else:
                _ok("verify_layout_missing")

    if failures:
        print(f"\n{len(failures)} self-test failures:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nOK: account.py self-test passed.")
    return 0


# --------------------------------------------------------------------------- #
# CLI entry
# --------------------------------------------------------------------------- #


def _cli_main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Account resolution helper")
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Run inline self-tests and exit",
    )
    p.add_argument(
        "--detect",
        action="store_true",
        help="Print detect_legacy_layout() result and exit",
    )
    args = p.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.detect:
        print(detect_legacy_layout())
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
