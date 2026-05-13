#!/usr/bin/env python3
"""Check rendered report HTML for self-containment and obvious data leaks."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional


RAW_NAN_RE = re.compile(r"(?<![A-Za-z0-9_])NaN(?![A-Za-z0-9_])")


def check_html_text(text: str, *, require_lang: Optional[str] = None) -> List[str]:
    """Return report HTML contract violations."""
    lower = text.lower()
    errors: List[str] = []
    if "<script src" in lower:
        errors.append("external script tag found (`<script src...>`)")
    if 'rel="stylesheet"' in lower or "rel='stylesheet'" in lower:
        errors.append("external stylesheet link found (`rel=stylesheet`)")
    if "xmlhttprequest" in lower or re.search(r"\bfetch\s*\(", text):
        errors.append("runtime network fetch found (`fetch(` or `XMLHttpRequest`)")
    if RAW_NAN_RE.search(text):
        errors.append("raw NaN literal found")
    if require_lang and f'<html lang="{require_lang}"' not in text:
        errors.append(f"expected `<html lang=\"{require_lang}\">`")
    return errors


def check_html_file(path: Path, *, require_lang: Optional[str] = None) -> List[str]:
    if not path.exists():
        return [f"HTML file not found: {path}"]
    return check_html_text(path.read_text(encoding="utf-8"), require_lang=require_lang)


def _cli(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--require-lang", default=None)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _cli(argv)
    errors = check_html_file(args.html, require_lang=args.require_lang)
    if not errors:
        print("OK: report HTML passed self-containment checks.")
        return 0
    print(f"FAIL: {len(errors)} report HTML problem(s):", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
