# Holdings Update Workflow

This spec governs every change the agent makes to `HOLDINGS.md`. The user describes a trade or correction in natural language; the agent parses it, shows a diff, gets explicit confirmation, then writes — never the other way around.

`HOLDINGS.md` is the **open-position ledger**, not a trade log. After a sell, the lot quantity decreases or the line disappears; realized P&L is reported in the confirmation step but is not persisted into the file.

**README languages** · [English](../README.md) · [繁體中文](l10n/README.zh-Hant.md) · [简体中文](l10n/README.zh-Hans.md) · [日本語](l10n/README.ja.md) · [Tiếng Việt](l10n/README.vi.md) · [한국어](l10n/README.ko.md) (canonical project overview: English; this spec is English-only.)

## When this spec applies

Any user message that describes a position change. Typical phrasings:

- "I bought 30 NVDA at $185 yesterday"
- "Sold 10 TSLA at $400 today"
- "Log trade: 5 BTC at 78,500 on 2026-04-25, long-term"
- "Trim 50% of my INTC short-term lots at $82"
- "Add 100 shares of GAMA at $660 to mid term"
- "Fix the GOOG lot from 2025-09: actually 70 shares not 75"

If the message is ambiguous (e.g. just "buy NVDA"), ask for the missing fields before parsing.

## Hard safety rules

1. **Never** write to `HOLDINGS.md` without an explicit user confirmation in the same conversation turn that contains the diff.
2. **Always** back up to `HOLDINGS.md.bak` (single rolling backup, overwritten each write) before touching `HOLDINGS.md`.
3. **Never** reformat unrelated lines, comments, blank lines, or section ordering. Only the affected lot lines and the corresponding cash line change.
4. **Never** persist realized P&L, dividends, fees, or any field outside the documented lot format into `HOLDINGS.md`.
5. **Never** silently invent missing fields. Echo every assumption.
6. **Re-read** the file after writing and verify the on-disk state matches the planned content; if not, restore from `HOLDINGS.md.bak` and tell the user.

## Parse: required fields per trade

For each trade in the user's message, extract:

| Field | Notes |
|---|---|
| Direction | `BUY` or `SELL` |
| Ticker | Case-normalized; preserve exchange suffix (`2330.TW`) and crypto symbols |
| Quantity | Decimal allowed (crypto / fractional shares) |
| Price | Per unit; preserve original currency prefix (`$`, `NT$`, `€`, …) |
| Date | `YYYY-MM-DD`. If the user did not say, default to today's local date and **state the assumption** |
| Bucket | `Long Term`, `Mid Term`, `Short Term`. Required for a BUY of a ticker not yet in the book; for an existing ticker, default to that ticker's current bucket and confirm; for a SELL, derive from existing lots |
| Currency | Settlement currency. Derive from the price prefix and the ticker's market. If multiple cash lines could match, ask |
| Market | Required market-type tag — `US`, `TW`, `TWO`, `JP`, `HK`, `LSE`, `crypto`, `FX`, or `cash`. For an existing ticker, default to that ticker's prior tag and confirm. For a new ticker, derive from the venue / suffix / asset class; if ambiguous (e.g. dual-listed), ask |

If any required field is missing or ambiguous, stop and ask one specific question — do not guess.

## BUY procedure

- Append a new lot line in the canonical format (the `[<MARKET>]` tag is **required** for new lots):
  - Equities: `<TICKER>: <qty> shares @ <price> on <YYYY-MM-DD> [<MARKET>]`
  - Crypto / FX: `<SYMBOL> <qty> @ <price> on <YYYY-MM-DD> [<MARKET>]` (no "shares")
- Place the line at the end of the chosen bucket section. Do not reorder existing lines.
- Cash impact: subtract `qty × price` from the corresponding cash line. If that line would go negative, stop and ask.
- The market tag is the single source of truth for `scripts/fetch_prices.py`; the script will format `2330.TW`, `BTC-USD`, `7203.T`, `VWRA.L`, etc. based on this tag — do not duplicate the suffix into the ticker itself unless the user wrote it that way.

## SELL procedure

- List candidate lots for the ticker, sorted by **highest cost basis first** (default tax-efficient ordering for gains). The user may override the ordering per trade with phrases like "FIFO", "oldest first", "specific lot 2098-09".
- Decrement quantities across one or more lots until the sell quantity is satisfied. If a lot reaches zero, remove the line entirely.
- Cash impact: add `qty × price` to the corresponding cash line.
- Compute realized P&L per affected lot and show it in the confirmation step. Do not write it to `HOLDINGS.md`.
- If the requested sell quantity exceeds total open quantity, refuse with the max sellable amount per lot.

## EDIT procedure (corrections to existing lots)

When the user is fixing a typo / wrong price / wrong date / wrong quantity (not logging a new trade), follow the same parse → confirm → write flow but:

- The proposed plan must say "EDIT" (not "BUY" / "SELL") and identify the exact line being changed.
- Do not adjust cash. Edits are corrections, not trades.
- If the user wants both an edit and a trade in the same message, list them as separate items.

## Confirmation transcript (required before writing)

Before any write, reply with exactly these blocks:

1. **Parsed trades** — a small table or bullet list with every field per trade. Mark every defaulted / inferred field as `(assumed)`.
2. **Plan** — bullet list of file-level edits, e.g.:
   - `Append to Long Term: NVDA: 30 shares @ $185.00 on 2026-04-27`
   - `Adjust USD: 50000 → 44450`
3. **Diff** — a fenced unified diff (` ```diff `) of `HOLDINGS.md` showing only the changed lines.
4. **Resulting state** — short summary: lot count per bucket, cash totals after the trade.
5. **Realized P&L** — only for SELL: per-lot realized P&L and the new cost-weighted average cost / hold period for the remaining lots. (IRR is intentionally not computed; see `docs/portfolio_report_agent_guidelines.md` §9.4.)
6. **Question** — literal prompt: `Confirm and write? (yes / no / edit)`.

Write only on `yes` / `confirm` / `go` / equivalent. On `edit`, re-prompt for what to change. On `no`, drop the plan and reply with a one-liner acknowledgement.

## Write procedure

1. Copy current `HOLDINGS.md` to `HOLDINGS.md.bak` (overwrite if exists).
2. Write the new `HOLDINGS.md`.
3. Re-read the file and confirm the changed lines match the plan exactly (no whitespace drift, no line reordering).
4. Reply with the absolute path of the updated file and a one-line summary, e.g. `Wrote /Users/.../HOLDINGS.md — added 1 lot (NVDA), USD cash 50000 → 44450.`
5. If the verification fails, restore from `HOLDINGS.md.bak` and report the failure without retrying silently.

## Edge cases

- **Sell more than held** → refuse, list each lot's max sellable quantity.
- **BUY for unknown ticker without a bucket** → ask the user to pick `Long Term` / `Mid Term` / `Short Term`.
- **Multiple cash lines in the same currency** → ask which one to debit / credit.
- **Date in the future** → refuse. `HOLDINGS.md` is the open-position ledger; planned or limit orders are out of scope.
- **Ambiguous price prefix** (e.g. bare `185` with no `$`) → ask for the currency.
- **Multi-trade batch** ("bought 10 NVDA at 200 and sold 5 TSLA at 400 yesterday") → parse each trade separately and present them as a single confirmation block. Write atomically.
- **Cash-only adjustments** ("I deposited $5,000") → allow as a special EDIT to the cash line, with the same confirmation flow.

## After-write follow-up (optional)

If the user wants the portfolio report regenerated after the write, hand off to `/docs/portfolio_report_agent_guidelines.md`. Do not auto-trigger; wait for the user to ask.
