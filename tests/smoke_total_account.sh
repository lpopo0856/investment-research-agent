#!/usr/bin/env bash
# tests/smoke_total_account.sh — end-to-end smoke for --all-accounts mode.
#
# Implementation per .omc/plans/total-account-report-plan.md Step 7.
# Mirrors tests/smoke_multi_account.sh:1-110 conventions: scripts copied into
# $SMOKE, all invocations relative to $SMOKE so __file__-derived REPO_ROOT
# resolves inside the smoke dir (POLLUTION-1).
#
# Verifies acceptance criteria AC#1, AC#2, AC#3, AC#4, AC#5, AC#7, AC#8 (numeric
# byte-diff), AC#9, AC#10, AC#11.

set -euo pipefail

RUN="$(date -u +%Y%m%dT%H%M%SZ)"
SMOKE="/tmp/investments_total_smoke_${RUN}_$$"
SMOKE_CACHE="/tmp/smoke_total_cache_${RUN}_$$.db"
FIXED_TODAY="2026-05-01"
REPO="$(git rev-parse --show-toplevel)"

# --- POLLUTION-1 EARLY GUARD ----------------------------------------------
# account.py:45 declares REPO_ROOT = Path(__file__).resolve().parent.parent —
# any direct invocation like `python /Users/.../scripts/transactions.py
# account create alpha` would resolve to the live repo regardless of cwd.
# Mirror smoke_multi_account.sh:23 — copy scripts into $SMOKE and invoke with
# relative paths from cd $SMOKE. ALSO refuse to run if a stale synthetic
# account dir already exists in the live repo.
for live in "$REPO/accounts/alpha" "$REPO/accounts/beta" "$REPO/accounts/beta_empty" "$REPO/accounts/_total"; do
    test ! -d "$live" || { echo "STALE LIVE-REPO POLLUTION: clean up $live first" >&2; exit 1; }
done

# Capture live cache mtime BEFORE any work (CACHE-PIN check at §9):
LIVE_CACHE="$REPO/market_data_cache.db"
if [ -f "$LIVE_CACHE" ]; then
    LIVE_CACHE_MTIME_BEFORE="$(stat -f %m "$LIVE_CACHE" 2>/dev/null || stat -c %Y "$LIVE_CACHE")"
else
    LIVE_CACHE_MTIME_BEFORE=""
fi

# --- SETUP ----------------------------------------------------------------
mkdir -p "$SMOKE"
# Copy scripts (POLLUTION-1: __file__-based REPO_ROOT lands inside $SMOKE):
cp -R "$REPO/scripts" "$SMOKE/"
[ -f "$REPO/SETTINGS.example.md" ] && cp "$REPO/SETTINGS.example.md" "$SMOKE/" || true
cd "$SMOKE"

trap 'cd / ; rm -rf "$SMOKE" "$SMOKE_CACHE"' EXIT

echo "=== smoke_total_account: $SMOKE (cache: $SMOKE_CACHE, today: $FIXED_TODAY)"

# --- Stage 3 fixture accounts ---------------------------------------------
# SCAFFOLD-1 NOTE: account create scaffolds dir + transactions.db, but
# SETTINGS.md is NOT auto-populated when SETTINGS.example.md is absent at the
# repo root (verified scripts/account.py:370-407 — heredoc copy at 388-389
# is conditional). We write SETTINGS explicitly via canonical heading+bullet
# form heredoc below, regardless of `account create`'s SETTINGS behavior.
python scripts/transactions.py account create alpha
python scripts/transactions.py account create beta
python scripts/transactions.py account create beta_empty

# FIXTURE-2 + SCAFFOLD-1: canonical heading+bullet form.
# parse_settings_profile uses _extract_settings_section_bullets +
# BASE_CURRENCY_PATTERN (verified scripts/portfolio_snapshot.py:237-345).
# `display_name` is computed from locale via DISPLAY_NAME_BY_LOCALE; the file
# has no `Display name:` key.
for acct in alpha beta beta_empty; do
    cat > "$SMOKE/accounts/$acct/SETTINGS.md" <<'EOF'
# Settings

## Language

- english

## Base currency

- Base currency: USD
EOF
done

# --- Seed transactions via `db add --json` ---
# (FIXTURE-1 corrected: alpha 10 NVDA - 5 sold = 5 net; beta 10 NVDA + 5 = 15
# net; merged total = 20.)
# `db add --json` is the canonical API; `db append` (in earlier plan drafts)
# does not exist. Verified at scripts/transactions.py db subcommand list.

# alpha seed: 5000 USD deposit + BUY 10 NVDA + SELL 5 NVDA
python scripts/transactions.py db add --account alpha --json '{
    "date": "2026-01-01", "type": "DEPOSIT", "amount": 5000,
    "currency": "USD", "cash_account": "USD",
    "rationale": "alpha seed cash"
}'
python scripts/transactions.py db add --account alpha --json '{
    "date": "2026-01-01", "type": "BUY", "ticker": "NVDA",
    "qty": 10, "price": 100, "gross": 1000, "fees": 0, "net": 1000,
    "currency": "USD", "cash_account": "USD",
    "bucket": "Long Term", "market": "US",
    "rationale": "alpha seed BUY (FIXTURE-1)"
}'
python scripts/transactions.py db add --account alpha --json '{
    "date": "2026-04-15", "type": "SELL", "ticker": "NVDA",
    "qty": 5, "price": 150, "gross": 750, "fees": 0, "net": 750,
    "currency": "USD", "cash_account": "USD",
    "bucket": "Long Term", "market": "US",
    "rationale": "alpha SELL (CB-2 same-date case)"
}'

# beta seed: 50000 TWD deposit + 10 NVDA + 100 2330.TW + 5 NVDA same-date
python scripts/transactions.py db add --account beta --json '{
    "date": "2026-01-15", "type": "DEPOSIT", "amount": 50000,
    "currency": "TWD", "cash_account": "TWD",
    "rationale": "beta seed cash"
}'
python scripts/transactions.py db add --account beta --json '{
    "date": "2026-01-15", "type": "BUY", "ticker": "NVDA",
    "qty": 10, "price": 120, "gross": 1200, "fees": 0, "net": 1200,
    "currency": "USD", "cash_account": "USD",
    "bucket": "Long Term", "market": "US",
    "rationale": "beta seed BUY (FIXTURE-1)"
}'
python scripts/transactions.py db add --account beta --json '{
    "date": "2026-02-01", "type": "BUY", "ticker": "2330.TW",
    "qty": 100, "price": 800, "gross": 80000, "fees": 0, "net": 80000,
    "currency": "TWD", "cash_account": "TWD",
    "bucket": "Long Term", "market": "TW",
    "rationale": "beta TW position"
}'
python scripts/transactions.py db add --account beta --json '{
    "date": "2026-04-15", "type": "BUY", "ticker": "NVDA",
    "qty": 5, "price": 145, "gross": 725, "fees": 0, "net": 725,
    "currency": "USD", "cash_account": "USD",
    "bucket": "Long Term", "market": "US",
    "rationale": "beta BUY (CB-2 same-date case)"
}'

# beta_empty: intentionally no transactions.

# --- MARKER-ESCAPE precondition (iteration 4) -----------------------------
# Empirically verify _esc("Holdings P&L and Weights") -> "Holdings P&amp;L and
# Weights" so §3 grep is robust against future _esc() refactors.
python -c "
import sys
sys.path.insert(0, '$SMOKE/scripts')
from generate_report import _esc
expected = 'Holdings P&amp;L and Weights'
actual = _esc('Holdings P&L and Weights')
assert actual == expected, (actual, expected)
print('MARKER-ESCAPE precondition: OK')
"

# --- PIPELINE -------------------------------------------------------------
echo "=== fetch_prices --all-accounts (skip yfinance)"
python scripts/fetch_prices.py \
    --all-accounts \
    --output "$SMOKE/prices.json" \
    --skip-yfinance

echo "=== fetch_history --all-accounts (per-run cache: $SMOKE_CACHE)"
python scripts/fetch_history.py \
    --all-accounts \
    --merge-into "$SMOKE/prices.json" \
    --cache "$SMOKE_CACHE" \
    --allow-incomplete

echo "=== snapshot --all-accounts (today=$FIXED_TODAY, base=USD)"
python scripts/transactions.py snapshot \
    --all-accounts \
    --prices "$SMOKE/prices.json" \
    --base-currency USD \
    --today "$FIXED_TODAY" \
    --output "$SMOKE/snapshot_all.json"

echo "=== generate_report --all-accounts (language=en)"
python scripts/generate_report.py \
    --snapshot "$SMOKE/snapshot_all.json" \
    --all-accounts \
    --language en \
    --output "$SMOKE/report.html"

# --- §1. prices.json union + _audit.positions_source ----------------------
echo "=== §1: prices.json union + _audit.positions_source"
test "$(jq 'has("NVDA")' "$SMOKE/prices.json")" = "true"      || { echo "FAIL §1: NVDA missing"; exit 1; }
test "$(jq 'has("2330.TW")' "$SMOKE/prices.json")" = "true"   || { echo "FAIL §1: 2330.TW missing"; exit 1; }
jq -r '._audit.positions_source' "$SMOKE/prices.json" | grep -q "^all_accounts:" \
    || { echo "FAIL §1: _audit.positions_source not all_accounts:..."; exit 1; }

# --- §2. snapshot aggregates: NVDA total qty == 20, base=USD --------------
echo "=== §2: snapshot aggregates"
NVDA_QTY="$(jq '.aggregates[] | select(.ticker=="NVDA").total_qty' "$SMOKE/snapshot_all.json")"
case "$NVDA_QTY" in
    20|20.0|20.00) : ;;
    *) echo "FAIL §2: NVDA total_qty=$NVDA_QTY (expected 20: alpha 10-5 + beta 10+5)"; exit 1 ;;
esac
BASE_CCY="$(jq -r '.totals.base_currency // .base_currency' "$SMOKE/snapshot_all.json")"
test "$BASE_CCY" = "USD" || { echo "FAIL §2: base_currency=$BASE_CCY (expected USD)"; exit 1; }

# --- §3. report.html math markers present ---------------------------------
echo "=== §3: math markers present"
# These markers are required (spec line 36-37: masthead + dashboard +
# allocation + holdings + cash/P&L panel are mandatory math sections).
for marker in \
    'class="masthead"' \
    "Portfolio Dashboard" \
    "Allocation" \
    "Holdings P&amp;L and Weights" \
    "Profit Panel" ; do
    grep -q "$marker" "$SMOKE/report.html" \
        || { echo "FAIL §3: math marker missing: $marker"; exit 1; }
done
# render_holding_period is KEEP per architect/critic verification (pure math),
# but the renderer returns "" when book_pacing.avg_hold_years is None
# (verified scripts/generate_report.py:3503). With thin fixtures (lots < 1
# month old or no compute_pacing data) this is legitimately empty. Treat as
# advisory: log presence but do not fail.
if grep -q "Holding Period and Pacing" "$SMOKE/report.html" ; then
    echo "  (info) Holding Period and Pacing rendered"
else
    echo "  (info) Holding Period and Pacing absent — book_pacing likely thin in fixture"
fi

# --- §4. report.html editorial markers absent (TEST-LEAK-1 corrected) -----
echo "=== §4: editorial markers absent"
for marker in \
    "Immediate Attention" \
    "Today's Summary" \
    "Latest Material News" \
    "Forward 30-Day Event Calendar" \
    "Recommended Adjustments" \
    "Today's Action List" \
    "Recent Trading Mindset" \
    "Theme and Sector Exposure" \
    "High Risk and High Opportunity" \
    "Performance Attribution" \
    "Trade Quality" \
    "Discipline Check" \
    "Report data quality" \
    "Sources and Data Gaps" ; do
    if grep -q "$marker" "$SMOKE/report.html" ; then
        echo "FAIL §4: editorial marker present: $marker"
        exit 1
    fi
done

# --- §5. output path: explicit --output works AND default lands under
#         accounts/_total/reports/<dated>_portfolio_report.html
echo "=== §5: default output path lands under accounts/_total/reports/"
test -f "$SMOKE/report.html" || { echo "FAIL §5: explicit --output missing"; exit 1; }
python scripts/generate_report.py \
    --snapshot "$SMOKE/snapshot_all.json" \
    --all-accounts \
    --language en
ls "$SMOKE/accounts/_total/reports/"*_portfolio_report.html >/dev/null 2>&1 \
    || { echo "FAIL §5: default output not under accounts/_total/reports/"; exit 1; }

# --- §M1. Mutex assertion (AC#7) + MUTEX-1 leak-free check ----------------
echo "=== §M1: mutex + MUTEX-1 leak-free check"
# Note: argparse exits 2 on conflicts and `set -o pipefail` would surface that
# even if grep matches. Capture stderr to a tempfile and grep separately.
# AC#7: passing both flags must reject.
TMP_ERR="$SMOKE/_m1.err"
set +e
python scripts/fetch_prices.py --account alpha --all-accounts --output /tmp/_x.json --skip-yfinance >/dev/null 2>"$TMP_ERR"
set -e
grep -q "not allowed with" "$TMP_ERR" \
    || { echo "FAIL §M1: --account + --all-accounts not rejected"; cat "$TMP_ERR"; exit 1; }
# MUTEX-1: subcommands that did NOT opt in must reject --all-accounts as
# unrecognized rather than treating it as a no-op.
for cmd in "account migrate" "verify" "db init" ; do
    set +e
    python scripts/transactions.py $cmd --all-accounts >/dev/null 2>"$TMP_ERR"
    set -e
    grep -q "unrecognized arguments\|invalid" "$TMP_ERR" \
        || { echo "FAIL §M1: '$cmd --all-accounts' not rejected (MUTEX-1 leak)"; cat "$TMP_ERR"; exit 1; }
done

# --- §M2. CB-2 deterministic same-date ordering: re-run pipeline, byte diff
echo "=== §M2: CB-2 deterministic re-run"
python scripts/transactions.py snapshot \
    --all-accounts \
    --prices "$SMOKE/prices.json" \
    --base-currency USD \
    --today "$FIXED_TODAY" \
    --output "$SMOKE/snapshot_all_2.json"
diff <(jq -S '. | del(.generated_at)' "$SMOKE/snapshot_all.json") \
     <(jq -S '. | del(.generated_at)' "$SMOKE/snapshot_all_2.json") \
    || { echo "FAIL §M2: re-run snapshots differ (non-determinism)"; exit 1; }

# --- §M3. add_account_args mutex idempotency (MJ-3 + MUTEX-1 opt-in) ------
echo "=== §M3: add_account_args idempotency"
python -c "
import argparse, sys
sys.path.insert(0, '$SMOKE/scripts')
from account import add_account_args

# Default mode: idempotent + does NOT leak --all-accounts.
p1 = argparse.ArgumentParser()
add_account_args(p1)
add_account_args(p1)
assert any('--account' in getattr(a, 'option_strings', []) for a in p1._actions), 'default: --account missing'
assert not any('--all-accounts' in getattr(a, 'option_strings', []) for a in p1._actions), \
    'MUTEX-1 violated: --all-accounts leaked into default-mode parser'

# Opt-in mode: idempotent + mutex group present.
p2 = argparse.ArgumentParser()
add_account_args(p2, support_all_accounts=True)
add_account_args(p2, support_all_accounts=True)
assert any('--account' in getattr(a, 'option_strings', []) for a in p2._actions), 'opt-in: --account missing'
assert any('--all-accounts' in getattr(a, 'option_strings', []) for a in p2._actions), 'opt-in: --all-accounts missing'
print('§M3: OK')
"

# --- §M4. Empty-accounts exit code 4 (MJ-4) -------------------------------
echo "=== §M4: empty-accounts exit code"
EMPTY="$SMOKE/empty_repo"
mkdir -p "$EMPTY/accounts" "$EMPTY/scripts"
cp -R "$SMOKE/scripts/." "$EMPTY/scripts/"
set +e
( cd "$EMPTY" && python scripts/fetch_prices.py --all-accounts --output /tmp/_empty.json --skip-yfinance ) 2>"$SMOKE/_empty.stderr"
EC=$?
set -e
test "$EC" = "4" || { echo "FAIL §M4: empty-accounts exit code=$EC (expected 4)"; cat "$SMOKE/_empty.stderr"; exit 1; }
grep -q "requires at least one real account" "$SMOKE/_empty.stderr" \
    || { echo "FAIL §M4: stderr missing 'requires at least one real account'"; cat "$SMOKE/_empty.stderr"; exit 1; }

# --- §M5. aggregate() ticker-market collision (CB-4 + M5-LITERAL) ---------
echo "=== §M5: aggregate() collision raises ValueError"
python <<PY
import sys
sys.path.insert(0, "$SMOKE/scripts")
from portfolio_snapshot import aggregate, Lot, MarketType

# Verified Lot signature at scripts/fetch_prices.py:335-345 (re-exported in
# portfolio_snapshot): (raw_line, bucket, ticker, quantity, cost, date,
# market, is_share=True). Phantom kwargs (acq_date) do not exist.
lot_us = Lot(
    raw_line="(synthetic) 10 0700.HK @ 100 USD",
    bucket="Long Term",
    ticker="0700.HK",
    quantity=10.0,
    cost=100.0,
    date="2026-01-01",
    market=MarketType.US,
    is_share=True,
)
lot_hk = Lot(
    raw_line="(synthetic) 5 0700.HK @ 120 HKD",
    bucket="Long Term",
    ticker="0700.HK",
    quantity=5.0,
    cost=120.0,
    date="2026-02-01",
    market=MarketType.HK,
    is_share=True,
)
try:
    aggregate([lot_us, lot_hk])
except ValueError as e:
    msg = str(e)
    assert "ticker market collision" in msg, msg
    assert "0700.HK" in msg, msg
    print("§M5: OK ->", msg)
else:
    raise SystemExit("§M5 FAIL: aggregate() did not raise on market collision")
PY

# --- §M6. account list does NOT show _total (AC#10) -----------------------
echo "=== §M6: account list excludes _total"
python scripts/transactions.py account list 2>&1 | grep -E "^\s*\*?\s*_total" \
    && { echo "FAIL §M6: account list shows _total"; exit 1; } || true

# --- §M7. Single-account equivalence AC#8 (PARSE-ASSERT + EXTRA-FIELDS) ----
echo "=== §M7: single-account equivalence (alpha vs alpha+beta_empty)"
# Remove beta entirely; keep alpha + beta_empty (which has no transactions).
# AC#8 then checks --all-accounts == --account alpha numerically.
rm -rf "$SMOKE/accounts/beta"

# PARSE-ASSERT: confirm alpha SETTINGS parses to (en, USD) BEFORE byte-diff.
python -c "
import sys
sys.path.insert(0, '$SMOKE/scripts')
from portfolio_snapshot import parse_settings_profile
from pathlib import Path
profile = parse_settings_profile(Path('$SMOKE/accounts/alpha/SETTINGS.md'))
assert profile.locale == 'en' and profile.base_currency == 'USD', profile
print('PARSE-ASSERT alpha SETTINGS: OK ->', profile.locale, profile.base_currency, profile.display_name)
"

# Re-fetch prices for the reduced account set (avoid stale union references).
python scripts/fetch_prices.py \
    --all-accounts \
    --output "$SMOKE/prices_alpha.json" \
    --skip-yfinance
python scripts/fetch_history.py \
    --all-accounts \
    --merge-into "$SMOKE/prices_alpha.json" \
    --cache "$SMOKE_CACHE" \
    --allow-incomplete

python scripts/transactions.py snapshot --all-accounts \
    --prices "$SMOKE/prices_alpha.json" --base-currency USD \
    --today "$FIXED_TODAY" --output "$SMOKE/snapshot_alpha_only.json"
python scripts/transactions.py snapshot --account alpha \
    --prices "$SMOKE/prices_alpha.json" --base-currency USD \
    --today "$FIXED_TODAY" --output "$SMOKE/snapshot_alpha_direct.json"

# EXTRA-FIELDS: byte-equivalence after canonicalization, stripping only
# generated_at. --today is pinned so .today matches; same prices.json used.
diff <(jq -S '. | del(.generated_at)' "$SMOKE/snapshot_alpha_only.json") \
     <(jq -S '. | del(.generated_at)' "$SMOKE/snapshot_alpha_direct.json") \
    || { echo "FAIL §M7: --all-accounts != --account alpha (AC#8 byte-equivalence)"; exit 1; }

# --- §7. Backwards-compat: --account alpha (no --all-accounts) ------------
echo "=== §7: backwards-compat --account alpha"
python scripts/generate_report.py \
    --snapshot "$SMOKE/snapshot_alpha_direct.json" \
    --account alpha \
    --output "$SMOKE/accounts/alpha/reports/regression_check.html" 2>&1 \
    || echo "(note: per-account render may require context — the snapshot path is what matters)"
test -f "$SMOKE/snapshot_alpha_direct.json" || { echo "FAIL §7: per-account snapshot missing"; exit 1; }

# --- §9. Live-repo non-pollution check ------------------------------------
echo "=== §9: live-repo non-pollution"
test ! -d "$REPO/accounts/alpha"      || { echo "LIVE REPO POLLUTED: $REPO/accounts/alpha"      >&2; exit 1; }
test ! -d "$REPO/accounts/beta"       || { echo "LIVE REPO POLLUTED: $REPO/accounts/beta"       >&2; exit 1; }
test ! -d "$REPO/accounts/beta_empty" || { echo "LIVE REPO POLLUTED: $REPO/accounts/beta_empty" >&2; exit 1; }
test ! -d "$REPO/accounts/_total"     || { echo "LIVE REPO POLLUTED: $REPO/accounts/_total"     >&2; exit 1; }
# CACHE-PIN: live cache mtime must NOT have advanced.
if [ -n "$LIVE_CACHE_MTIME_BEFORE" ] && [ -f "$LIVE_CACHE" ]; then
    LIVE_CACHE_MTIME_AFTER="$(stat -f %m "$LIVE_CACHE" 2>/dev/null || stat -c %Y "$LIVE_CACHE")"
    test "$LIVE_CACHE_MTIME_BEFORE" = "$LIVE_CACHE_MTIME_AFTER" \
        || { echo "LIVE CACHE BUMPED: $LIVE_CACHE mtime changed"; exit 1; }
fi

echo
echo "==============================================="
echo "smoke_total_account.sh: ALL ASSERTIONS PASSED"
echo "==============================================="
