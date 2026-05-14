"""Build a one-file executable for the local Investments UI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "scripts" / "run_packaged_ui.py"


def _script_hidden_imports() -> list[str]:
    """Return top-level script modules that PyInstaller may not infer."""

    ignored = {"run_ui_server", "run_packaged_ui", "build_ui_executable"}
    return [
        path.stem
        for path in sorted((REPO_ROOT / "scripts").glob("*.py"))
        if path.stem not in ignored and path.stem.isidentifier()
    ]


def build_command(args: argparse.Namespace) -> list[str]:
    """Construct the PyInstaller command for this platform."""

    data_sep = os.pathsep
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        args.name,
        "--distpath",
        str(args.distpath),
        "--workpath",
        str(args.workpath),
        "--specpath",
        str(args.specpath),
        "--paths",
        str(REPO_ROOT),
        "--paths",
        str(REPO_ROOT / "scripts"),
        "--add-data",
        f"{REPO_ROOT / 'ui' / 'static'}{data_sep}ui/static",
        "--collect-submodules",
        "uvicorn",
        "--collect-submodules",
        "websockets",
        "--copy-metadata",
        "platformdirs",
    ]
    for module in _script_hidden_imports():
        cmd.extend(["--hidden-import", module])
    cmd.append(str(ENTRYPOINT))
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="investments-ui")
    parser.add_argument("--distpath", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--workpath", type=Path, default=REPO_ROOT / "build" / "pyinstaller")
    parser.add_argument("--specpath", type=Path, default=REPO_ROOT / "build" / "pyinstaller-spec")
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print the PyInstaller command without executing it.",
    )
    args = parser.parse_args(argv)

    args.distpath.mkdir(parents=True, exist_ok=True)
    args.workpath.mkdir(parents=True, exist_ok=True)
    args.specpath.mkdir(parents=True, exist_ok=True)

    cmd = build_command(args)
    if args.print_command:
        print(" ".join(cmd))
        return 0

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "PyInstaller is not installed. Install build dependencies from "
            "requirements-ui-build.txt.",
            file=sys.stderr,
        )
        return 2

    subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
