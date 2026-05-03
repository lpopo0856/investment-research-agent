#!/usr/bin/env python3
"""Static checks for mobile holdings card markup in generated report HTML."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def _failures(html: str) -> list[str]:
    failures: list[str] = []
    if 'class="tbl-wrap holdings-table-wrap"' not in html:
        failures.append('missing .holdings-table-wrap desktop/tablet wrapper')
    if 'class="holdings-cards"' not in html:
        failures.append('missing .holdings-cards phone card container')
    if '<span class="sym-trigger"' in html:
        failures.append('static ticker span uses .sym-trigger interactive affordance')
    if re.search(r'class="sym-label"[^>]*(?:tabindex=|role="button")', html):
        failures.append('.sym-label must stay non-interactive')
    if not re.search(r'\.sym-trigger\s+\.sym-text\s*\{[^}]*text-decoration-line\s*:\s*underline', html, flags=re.S):
        failures.append('CSS missing always-visible dotted underline on .sym-trigger .sym-text')
    if not re.search(r'\.price-trigger\s+\.price-num\s*\{[^}]*text-decoration-line\s*:\s*underline', html, flags=re.S):
        failures.append('CSS missing always-visible dotted underline on interactive .price-num')

    cards = re.findall(r'<article class="holding-card"(?:\s|>).*?</article>', html, flags=re.S)
    row_count = 0
    # The first </tbody> inside holdings-tbl can close a nested lot popover table — count rows
    # only inside the desktop wrapper up to the phone card stack.
    wrap = re.search(
        r'holdings-table-wrap">(.*?)<div class="holdings-cards"',
        html,
        flags=re.S,
    )
    if wrap:
        row_count = wrap.group(1).count('<div class="sym-trigger" tabindex="0" role="button">')
    if not cards:
        failures.append('no .holding-card entries found')
    if row_count and len(cards) != row_count:
        failures.append(f'card count {len(cards)} does not match holdings table row count {row_count}')

    required_classes = [
        'holding-card-symbol',
        'holding-card-category',
        'holding-card-price',
        'holding-card-weight',
        'holding-card-value',
        'holding-card-pnl',
        'holding-card-action',
    ]
    for idx, card in enumerate(cards, start=1):
        for cls in required_classes:
            if cls not in card:
                failures.append(f'card {idx} missing {cls}')
        if '<div class="sym-trigger" tabindex="0" role="button">' not in card:
            failures.append(f'card {idx} missing exact sym-trigger div contract')
        if '<span class="sym-text">' not in card:
            failures.append(f'card {idx} missing .sym-text affordance marker')
        if '<div class="price-trigger" tabindex="0" role="button">' not in card:
            failures.append(f'card {idx} missing exact price-trigger div contract')

    for button_match in re.finditer(r'<button\b.*?</button>', html, flags=re.S | re.I):
        if 'class="pop ' in button_match.group(0) or "class='pop " in button_match.group(0):
            failures.append('popover markup appears inside a <button> ancestor')
            break
    if not re.search(r'\.holdings-cards\s*\{\s*display\s*:\s*none\s*\}', html):
        failures.append('CSS missing default .holdings-cards{display:none}')
    if not re.search(r'\.holdings-table-wrap\s*\{\s*display\s*:\s*none\s*\}', html):
        failures.append('CSS missing phone .holdings-table-wrap{display:none}')
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    args = parser.parse_args()
    html = args.html.read_text(encoding='utf-8')
    failures = _failures(html)
    if failures:
        print('FAIL — mobile holdings card checks failed:')
        for failure in failures:
            print(f'  - {failure}')
        return 1
    print('OK — mobile holdings card static checks passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
