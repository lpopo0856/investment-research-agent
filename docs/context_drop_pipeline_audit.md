# Pipeline Token-Save Audit

Companion to `docs/context_drop_protocol.md`. The protocol defines the rules; this document identifies *where in the existing pipelines* the rules should be applied first, ranked by token savings vs. risk.

The estimates below are order-of-magnitude (within ~2×) based on typical run sizes.

## Executive summary — top 3 wins

| # | Change | Pipeline | Est. tokens saved per run | Quality risk |
|---|--------|----------|---------------------------|--------------|
| 1 | Wrap §10.5 news + §10.6 events research in a single subagent **only when those sections render** | single-account daily-report Phase A | 30k–80k | None — artifact (`report_context.json` fragment) is identical |
| 2 | Replace full `report_snapshot.json` reads with `jq` field reads | portfolio-report Phase B/D | 5k–25k | None — only the field actually needed crosses into context |
| 3 | Wrap statement-file extraction (PDF / image / large CSV) in a subagent | onboarding §6 | 10k–60k for big imports | None — output is canonical JSON either way |

Together these are the difference between a portfolio-report run that fits comfortably in main context and one that spills into auto-compaction. None of the three change *what* gets produced — they only change *where the production happens*.

---

## Portfolio Report Pipeline (`docs/portfolio_report_agent_guidelines.md`)

Heaviest pipeline in the repo. Four phases: A Gather → B Think → C Review → D Render.

### Where the tokens actually go

Per typical run, the dominant sources of cumulative input tokens are (descending):

1. **Phase A news/events research** — WebSearch + WebFetch dumps for §10.5 (news per ticker, full universe) and §10.6 (30-day catalysts), **only for modes that render those sections** (current policy: single-account `daily_report`). Each ticker may produce 2–5K tokens of search snippets; a 15-name portfolio = 30–80K tokens. **Lives in main context for every subsequent turn unless dropped.** `portfolio_report` saves the entire cost by skipping this research by policy.
2. **`report_snapshot.json`** read at Phase B and again at Phase D — typically 8–25K tokens of canonical numerics. Currently often read whole when only specific fields are referenced.
3. **`report_context.json`** read after Phase A populates it — 5–20K tokens.
4. **`transactions.db` dump** if the agent calls `db dump` for analytic context — can be 10–40K for established users.
5. **Spec corpus** (the bundled part files 00–07 + main guideline + CLAUDE.md + AGENTS.md) — ~30K tokens, read once at session start, then prompt-cached. **Already efficient; do not change.**
6. **`prices.json` (with `_history`/`_fx_history` merged)** — 3–10K tokens, narrow reads usually fine.

### Recommended changes

#### A1. News + events research → subagent (highest ROI)

**Status quo**: when daily sections render, Phase A may run WebSearch / WebFetch directly in the main agent. All snippets land in the main transcript. Live research is mandatory only for rendered daily decision sections; `portfolio_report` must not run it.

**Change**: daily Phase A delegates §10.5 + §10.6 research to a temp-researcher per `docs/temp_researcher_contract.md` (any runtime's isolation primitive). The temp-researcher is not invoked for `portfolio_report` or `total_account`. The temp-researcher:
- Receives the tickers list and the §10.5/§10.6 spec excerpts.
- Runs WebSearch / WebFetch / source-fetching to its heart's content.
- Writes findings directly into `$REPORT_RUN_DIR/report_context.json` under the `news` and `events_30d` fields.
- Returns to parent: `{updated_fields: ["news", "events_30d"], summary: "<= 200 words", sources_count: <n>, audit_hash: <sha>}`.

**Quality**: Identical — the artifact (`report_context.json` fragment) is the same bytes either way. The audit trail (per-source citations) lives in the artifact, not the conversation. Phase B reads what it needs from the artifact.

**Risk**: Low. When §10.5 renders, the rule "empty section without audit trail = workflow violation" is satisfied as long as the subagent's audit fields are present in the artifact. When §10.5 is skipped, the close-check is inverted: assert `news`, `events`, `research_targets`, and `research_coverage` are absent.

**Estimated savings**: 30k–80k tokens of cumulative input over the rest of the run (news snippets re-sent every turn after Phase A until session end or compaction).

**Where to update**: `docs/portfolio_report_agent_guidelines.md` section-level routing and `04-computations-to-static-snapshot.md` §10.5 / §10.6, with a section-gated `@temporary` declaration block per the protocol.

#### A2. Snapshot/context reads → field-narrow

**Status quo**: When Phase B or D needs a value from `report_snapshot.json` it often reads the full file. The file is mostly numerics the current step doesn't need.

**Change**: Use `jq` for snapshot/context reads:
```bash
jq '.profit_panel' "$REPORT_RUN_DIR/report_snapshot.json"
jq '.transaction_analytics.discipline_check.top_position_weights' "$REPORT_RUN_DIR/report_snapshot.json"
jq '.news[] | {ticker: .ticker, headlines: [.items[].headline]}' "$REPORT_RUN_DIR/report_context.json"
```
Reserve full reads for Phase D's render step where the renderer needs everything anyway — but note the renderer reads the file from disk, not via the agent's Read tool, so the full bytes never enter the agent transcript.

**Quality**: Identical. The renderer is the only consumer that needs the whole snapshot.

**Risk**: Negligible. `jq` is already a workflow dependency.

**Estimated savings**: 5k–25k tokens per run. Bigger on portfolios with deep `transaction_analytics`.

**Where to update**: `docs/portfolio_report_agent_guidelines/04-computations-to-static-snapshot.md` (snapshot consumers) and the Phase B / Phase D execution notes in the main guideline.

#### A3. Spec parts — load on demand, not always (deferred — needs measurement)

**Status quo**: Main guideline says "read every part file in order on every portfolio-report run." Total ~1200 lines for the parts.

**Possible change**: The parts split into Phase A material (00–03 + 10.5/10.6 sections of 04) and Phase B/C/D material (rest of 04, 05–07). Phase A loads only what it needs; Phase B subagent (if introduced) loads the rest.

**Why deferred**: This is prompt-cached after the first load. The savings only materialize if multiple report runs happen in the same session, OR if we structure Phase B as a subagent (which dies on exit). The current bundled-read pattern is also a coherence safeguard — easy to lose enforcement.

**Recommendation**: Leave it. Revisit only if, post-A1/A2, the spec corpus is observably a top token sink across runs.

#### A4. `transactions.db` queries — narrow SQL, not `db dump`

**Status quo**: Agent occasionally runs `db dump` to get raw transaction context for Phase B reasoning. Output can be huge.

**Change**: Prefer narrow queries (`db stats`, `db get-transactions --since 2026-01-01 --type SELL`, `sqlite3 transactions.db "SELECT … LIMIT 50"`) for analytic peeks. Use `transactions.py snapshot` / `transactions.py analytics` as the canonical path — they already produce compact, schema-validated JSON. `db dump` should be reserved for backup, never for "give me transaction context."

**Quality**: Identical — `snapshot` / `analytics` outputs are the canonical form Phase B is supposed to read anyway.

**Risk**: Low. Mostly a discipline rule.

**Estimated savings**: 10k–40k tokens for established users; near-zero for new users.

**Where to update**: `docs/portfolio_report_agent_guidelines/04-computations-to-static-snapshot.md` and `docs/transactions_agent_guidelines.md` §6 (cross-reference: "for report runs, use `snapshot`; `db dump` is for backup").

---

## Onboarding Pipeline (`docs/onboarding_agent_guidelines.md`)

Heaviest single-step is statement extraction (§6.2 step 1 — read PDF / image / large CSV).

### Recommended changes

#### B1. Statement-file extraction → subagent

**Status quo**: Main agent reads the user's statement file directly. PDFs and screenshots especially can be 5K–60K tokens of raw content.

**Change**: Delegate to a subagent that:
- Receives the file path and the canonical schema spec (§3 from `docs/transactions_agent_guidelines.md`).
- Reads, OCRs / parses, and writes canonical JSON to `/tmp/onboarding_<broker>_<ts>.json`.
- Returns `{output_json: <path>, row_count, type_counts, currencies, date_range, summary, audit_hash}`.

Main agent then proceeds to §6.3 confirmation using the *summary* fields, not the raw extraction. The user-facing "first 5–10 parsed rows" preview is read narrowly from `/tmp/onboarding_*.json` via `jq '.[0:10]'`.

**Quality**: Identical — `db import-json` validates the same canonical JSON either way.

**Risk**: Low. The subagent must surface OCR uncertainty in its summary so the main agent can flag `(assumed)` fields per §2 rule 4. Add an explicit `assumed_fields: [{row_index, field, value}]` array to the subagent return contract.

**Estimated savings**: 10k–60k tokens depending on input size. Multi-page PDFs are the big wins.

**Where to update**: `docs/onboarding_agent_guidelines.md` §6.2.

#### B2. Confirmation-block size cap

**Status quo**: §6.3 confirmation transcript shows "one-line per row or, for large batches, the path you will pass to `db import-json`". Some agents still inline the full row list.

**Change**: Make the path-only form the default for batches > 20 rows. Show the user a 5-row sample + counts + the `/tmp/...json` path.

**Quality**: Improved — large in-line lists are unreadable anyway.

**Risk**: None.

**Estimated savings**: 2k–15k tokens for big imports.

---

## Transactions Pipeline (`docs/transactions_agent_guidelines.md`)

Mostly fine. The natural-language workflow (§3) is small per turn. Bulk paths (§4) already dispatch to `import-csv` / `import-json` without needing to load file contents into the conversation.

### Recommended changes

#### C1. `db dump` is for backup, not context (cross-cut from A4)

Add an explicit "do not paste `db dump` output into the conversation; use `db stats` or narrow queries" line in §3 / §4. The cross-link to A4 covers the report-side concern.

#### C2. Bulk-import preview → narrow

When confirming a bulk CSV/JSON import, show counts + 5-row sample + path. Mirror B2's rule.

**Estimated savings**: 5k–20k tokens for big imports.

---

## Settings & Help

Both are low-volume conversational flows. No protocol change recommended; subagent overhead would exceed the savings. Settings interview turns rarely cross 3K tokens combined.

---

## Aggregate before/after estimate (typical 15-name portfolio, 6-month-old DB)

| Pipeline run | Before | After | Δ |
|--------------|--------|-------|---|
| Portfolio report (typical) | 90k–160k cumulative input | 25k–55k | -65k to -105k |
| Onboarding (3-page PDF + 80 rows) | 35k–70k | 10k–20k | -25k to -50k |
| Transactions (NL single trade) | 5k–10k | 5k–10k | 0 (already efficient) |
| Transactions (bulk CSV 200 rows) | 25k–45k | 8k–15k | -17k to -30k |

These are *cumulative input* (tokens × turns), not single-turn sizes. The savings compound the longer the session.

## Implementation order (suggested)

1. **A1 first** — biggest portfolio-report win, isolated change to one phase.
2. **B1 second** — biggest onboarding win, similar pattern, validates the subagent return contract.
3. **A2 + A4 + C1 + C2 third** — discipline rules, no infrastructure, easy to land together.
4. **A3 deferred** — only if measurement justifies it.

Each step is independently shippable. None of them require changes to scripts, just to agent guidelines + the temp-researcher contract at `docs/temp_researcher_contract.md` (with per-runtime adaptation files such as `.claude/agents/temp-researcher.md` for Claude Code).

## What we explicitly are NOT changing

- The bundled spec read at session start. Already prompt-cached; touching it adds risk for tiny gain.
- `transactions.py snapshot` / `analytics` / `pnl` outputs. They're already compact and canonical.
- Phase D HTML render (`generate_report.py`). Runs as a subprocess; output bytes never enter the conversation.
- `SETTINGS.md` reads. Small file, anchor-of-truth, read often.
- Filesystem cleanup (`rm -rf "$REPORT_RUN_DIR"`). Already correct per `CLAUDE.md`.

These are listed so future audits don't relitigate them without new evidence.
