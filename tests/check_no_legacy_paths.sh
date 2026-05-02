#!/usr/bin/env bash
# Doc-drift canary: fails if any doc references legacy single-account paths
# as the recommended invocation. Demo/-scoped references are explicitly exempt.
#
# Usage:
#   bash tests/check_no_legacy_paths.sh
#   exit 0 = clean; exit 1 = legacy patterns found
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DOC_GLOBS=(
  "README.md"
  "CLAUDE.md"
  "AGENTS.md"
  "GEMINI.md"
  "docs/onboarding_agent_guidelines.md"
  "docs/transactions_agent_guidelines.md"
  "docs/settings_agent_guidelines.md"
  "docs/help_agent_guidelines.md"
  "docs/portfolio_report_agent_guidelines.md"
  "docs/portfolio_report_agent_guidelines/"
  "docs/l10n/"
)

# Patterns that indicate legacy invocation as the recommended form.
# Each pattern is grep -E (extended regex). Demo references are filtered out via grep -v.
LEGACY_PATTERNS=(
  '--db[[:space:]]+transactions\.db([^/]|$)'
  '--settings[[:space:]]+SETTINGS\.md([^/]|$)'
)

EXIT=0
for pat in "${LEGACY_PATTERNS[@]}"; do
  echo "Checking: $pat"
  hits=$(grep -RnE "$pat" "${DOC_GLOBS[@]}" 2>/dev/null || true)
  # Filter out demo/ and demo references
  hits_filtered=$(echo "$hits" | grep -v 'demo' || true)
  if [ -n "$hits_filtered" ]; then
    echo "FAIL: legacy pattern '$pat' found in non-demo context:" >&2
    echo "$hits_filtered" >&2
    EXIT=1
  fi
done

# Also check for hardcoded `transactions.db` or `SETTINGS.md` paths in command-line examples
# that aren't explicitly account-scoped or demo-scoped. (Code blocks containing
# `python scripts/...` and these paths.)
for f in "${DOC_GLOBS[@]}"; do
  if [ -d "$f" ]; then
    files=$(find "$f" -name "*.md" -type f)
  elif [ -f "$f" ]; then
    files="$f"
  else
    continue
  fi
  for file in $files; do
    # In code blocks: python scripts/... that contain 'transactions.db' or 'SETTINGS.md'
    # without 'accounts/' or 'demo/' prefix.
    suspicious=$(awk '
      /^```/ { in_block = !in_block; next }
      in_block && /python scripts\// && /transactions\.db|SETTINGS\.md/ && !/accounts\/|demo\// {
        print FILENAME ":" NR ": " $0
      }
    ' "$file" 2>/dev/null || true)
    if [ -n "$suspicious" ]; then
      echo "FAIL: code block uses legacy path in $file:" >&2
      echo "$suspicious" >&2
      EXIT=1
    fi
  done
done

if [ "$EXIT" -eq 0 ]; then
  echo "OK: no legacy single-account patterns found in docs."
fi

exit "$EXIT"
