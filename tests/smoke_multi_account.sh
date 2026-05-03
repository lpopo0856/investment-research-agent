#!/usr/bin/env bash
# Multi-account migration smoke test (Phase 7, AC-VER-2, C-4).
# Stages a legacy layout in /tmp/, runs migration, verifies post-state,
# cycles all 7 entry-points, checks live-repo non-pollution, cleans up.
set -euo pipefail

trap 'echo "SMOKE FAIL at line $LINENO" >&2' ERR

RUN="$(date -u +%Y%m%dT%H%M%SZ)"
SMOKE="/tmp/investments_multi_account_smoke_${RUN}"
REPO="$(git rev-parse --show-toplevel)"

# --- Pre-check: skip if live repo doesn't have legacy layout ---
if [ ! -f "$REPO/SETTINGS.md" ] || [ ! -f "$REPO/transactions.db" ]; then
  echo "SMOKE SKIP: live repo does not have legacy root layout (SETTINGS.md + transactions.db)."
  exit 0
fi

echo "SMOKE: staging $SMOKE"
mkdir -p "$SMOKE"

# --- Stage: copy live state into smoke dir (read-only sources) ---
cp -R "$REPO/scripts" "$SMOKE/"
cp -R "$REPO/docs" "$SMOKE/"
cp "$REPO/SETTINGS.example.md" "$SMOKE/" 2>/dev/null || true
cp "$REPO/SETTINGS.md" "$SMOKE/SETTINGS.md"
cp "$REPO/transactions.db" "$SMOKE/transactions.db"
[ -f "$REPO/transactions.db.bak" ] && cp "$REPO/transactions.db.bak" "$SMOKE/" || true

mkdir -p "$SMOKE/reports"
if [ -d "$REPO/reports" ]; then
  # copy any existing report HTML
  cp -R "$REPO/reports/." "$SMOKE/reports/" 2>/dev/null || true
fi

# Don't copy market_data_cache.db — migration leaves it at root, but for smoke we
# create a stub at $SMOKE/ root so the script's existence checks behave as in real use.
touch "$SMOKE/market_data_cache.db"

cd "$SMOKE"

# --- 1. Confirm legacy state staged ---
test -f SETTINGS.md
test -f transactions.db
test ! -d accounts
echo "SMOKE: legacy state confirmed at $SMOKE"

# --- 2. Detect, then migrate ---
detect=$(python scripts/transactions.py account detect 2>&1 | tail -n 1)
echo "SMOKE: detect_legacy_layout = $detect"
test "$detect" = "migrate"

python scripts/transactions.py account migrate --yes
echo "SMOKE: migration completed (account migrate --yes)"

# --- 3. Post-migration assertions ---
test -f accounts/default/SETTINGS.md      # AC-MIG-2
test -f accounts/default/transactions.db  # AC-MIG-2
test -d accounts/default/reports          # AC-MIG-2 (may be empty)
test -f accounts/.active                  # AC-MIG-2
grep -q '^default$' accounts/.active      # AC-MIG-2 pointer content
test -d .pre-migrate-backup               # AC-MIG-2 backup
test -f .pre-migrate-backup/migration-manifest.json  # AC-MIG-2 manifest
test ! -f SETTINGS.md                     # root cleaned
test ! -f transactions.db                 # root cleaned
test -f market_data_cache.db || true      # cache MAY remain at root (we created stub)
test ! -f accounts/default/market_data_cache.db  # AC-MIG-5: cache NOT moved
echo "SMOKE: post-migration assertions OK"

# --- 4. Idempotency: second migration is a no-op ---
detect2=$(python scripts/transactions.py account detect 2>&1 | tail -n 1)
test "$detect2" = "clean"
echo "SMOKE: second detect = clean (idempotent)"

# --- 5. 7-entry-point cycle (using --help to avoid network/heavy ops) ---
# autodetect at top of main() is a no-op now because state is "clean".
python scripts/transactions.py verify --account default >/dev/null
python scripts/fetch_prices.py --help >/dev/null
python scripts/fetch_history.py --help >/dev/null
python scripts/fill_history_gap.py --help >/dev/null
python scripts/generate_report.py --help >/dev/null
python scripts/report_archive.py --help >/dev/null
python scripts/validate_report_context.py --help >/dev/null
echo "SMOKE: 7-entry-point cycle OK"

# --- 6. Account subcommand sanity ---
python scripts/transactions.py account list | grep -q "default"
python scripts/transactions.py account create test_smoke
test -d accounts/test_smoke
test -f accounts/test_smoke/SETTINGS.md
test -f accounts/test_smoke/transactions.db
python scripts/transactions.py account use test_smoke
grep -q '^test_smoke$' accounts/.active
python scripts/transactions.py account use default
echo "SMOKE: account subcommands OK"

# --- 7. Live-repo non-pollution check (C-4 belt-and-suspenders) ---
test ! -d "$REPO/accounts" || { echo "LIVE REPO POLLUTED: $REPO/accounts/" >&2; exit 1; }
test ! -d "$REPO/.pre-migrate-backup" || { echo "LIVE REPO POLLUTED: $REPO/.pre-migrate-backup/" >&2; exit 1; }
test ! -f "$REPO/accounts/.active" || { echo "LIVE REPO POLLUTED: $REPO/accounts/.active" >&2; exit 1; }
# Confirm live repo's legacy state is intact (we never touched it)
test -f "$REPO/SETTINGS.md" || { echo "LIVE REPO MUTATED: $REPO/SETTINGS.md missing" >&2; exit 1; }
test -f "$REPO/transactions.db" || { echo "LIVE REPO MUTATED: $REPO/transactions.db missing" >&2; exit 1; }
echo "SMOKE: live repo non-pollution OK"

# --- 8. Cleanup ---
cd /
rm -rf "$SMOKE"
echo "SMOKE PASS"
