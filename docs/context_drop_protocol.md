# Context Drop Protocol

## Natural-language user interface

Natural language is the default user interface for this workflow. Commands, flags, paths, schemas, and machine-readable examples in this document are agent-internal contracts or audit evidence. In normal user replies, translate them into natural-language actions, execute eligible steps yourself, collect missing parameters conversationally, and summarize results naturally. Do not show Python/shell commands, command code blocks, canonical command names, or JSON/file-format requirements as user instructions unless the user explicitly asks for CLI/API help or execution is blocked by missing authority.

A meta-rule that any multi-stage agent workflow in this repo must obey, so that source data marked **Temporary** never accumulates in the live conversation context past the point it is useful. The objective is **minimum cumulative input tokens** across long pipelines, achieved by *keeping data out by construction* rather than dropping it afterward.

This document is the contract. The mechanisms it relies on (subagent isolation, result-file handoff, phase-boundary compaction) are all native Claude Code primitives — no custom infrastructure required.

## Why this exists

Long agent pipelines (portfolio-report runs, onboarding imports, settings interviews followed by research) accumulate large `tool_use_result` blocks: WebSearch dumps, large file reads, raw price/transaction extractions, agent-to-agent reports. Once a phase's *result file* exists on disk, those raw inputs are no longer needed for any downstream phase — but they are re-sent on every subsequent API turn, paying token cost for data that has already been distilled.

This protocol prevents that by mandating that any data declared **Temporary** is produced inside an isolated context (a subagent), with only its *result file path* and a short summary returned to the caller.

## The three primitives

### 1. `@temporary` declaration

Every phase that produces large intermediate data must declare its lifetime up-front, in the agent guideline that owns the phase. The declaration is a five-field block:

```
@temporary
  producer: <agent or script>
  consumer_artifact: <absolute path that must exist before drop>
  bytes_estimate: <rough order of magnitude>
  drop_trigger: artifact_exists | phase_boundary | session_end
  fallback: keep | warn | fail
```

Example, for the section-gated daily-report news-research phase:

```
@temporary
  producer: subagent (general-purpose, WebSearch + WebFetch)
  consumer_artifact: $REPORT_RUN_DIR/report_context.json (news + events fields populated)
  bytes_estimate: 30k–80k tokens of search results
  drop_trigger: artifact_exists
  fallback: fail   # no silent rendering with empty news when the news section renders
```

### 2. Result artifact = the drop trigger

A phase is "closed" only when the `consumer_artifact` exists on disk **and** validates (schema check, non-empty, hash recorded). The artifact is the durable, compact record. No artifact, no drop — the protocol fails loud rather than silently discarding work.

The artifact is also the *only thing* the next phase reads. The next phase does **not** receive a re-summary of the producer's reasoning trace.

### 3. Clean State transition

When a phase closes, the workflow must take one of these actions, in priority order:

1. **Subagent exit** (preferred). If the phase ran inside a subagent, exit returns control to the parent with only the final assistant message. All `tool_use_result` blocks die with the subagent. **Zero token cost in main context for the dropped data.** This is the default mechanism.
2. **`/compact` at phase boundary** (fallback). If the phase ran in the main agent and produced large `tool_use_result` blocks anyway, trigger `/compact` once the artifact is durable. Coarse but real. Pays one cache-reprime cost; net-positive only when ≥ 4 turns of work remain.
3. **Session end + reload** (heavy). For pipelines too long to fit in a single useful context window, end the session at a phase boundary. The next stage starts fresh and reads only the artifact.

## HARD rules

- **Research-class phases run in subagents, not the main agent.** A "research-class phase" is any phase whose deliverable is a file or short summary and whose internal work involves > 5K tokens of tool_use_result (web searches, large file reads, repeated greps, multi-step API queries). Violation = workflow defect. The section-gated daily-report §10.5 Phase A news/events gather, the onboarding statement-parsing phase, and any /docs lookup that pulls > 3 files all qualify. `portfolio_report` does not qualify through §10.5 because it must not run that research at all.
- **Subagents must not return their full reasoning trace to the parent.** Return shape is `{result_file: <path>, summary: <≤ 200 words>, audit: <hash + bytes>}`. Pasting the subagent's intermediate findings back into the main response is the same as not having used a subagent.
- **The parent agent must read the result file lazily.** Read it only when the next-stage step actually needs a field, and prefer narrow reads (offset/limit, jq filters) over full file dumps. A full result-file read in the main context defeats the protocol.
- **No artifact, no drop.** If the consumer artifact is missing or fails validation at phase close, the protocol fails per the declaration's `fallback` setting. `keep` retains the temp data and warns; `warn` drops anyway with a logged warning; `fail` aborts the pipeline. Default `fallback` is `fail` for any artifact whose absence would corrupt downstream reasoning.
- **No global compaction without a closed phase.** Do not run `/compact` opportunistically mid-phase; it can drop content that the current phase still needs. `/compact` only fires at declared phase boundaries.

## How this slots into existing workflows

### Portfolio report (`docs/portfolio_report_agent_guidelines.md`)

Phases A–D already have an implicit version of this. Make it explicit:

- **Phase A (Gather)** — declare `@temporary` on news/events/research dumps only when the effective report policy renders §10.5 / daily decision sections (current policy: single-account `daily_report`). Run inside a subagent (`general-purpose` with WebSearch). Return path to the populated `report_context.json` segment plus ≤ 200-word summary. For `portfolio_report` and `total_account`, skip this phase entirely; do not produce `news`, `events`, `research_targets`, or `research_coverage`.
- **Phase B (Think)** — reads `report_context.json` lazily. Does *not* re-summarize Phase A's search results. If §10.5 was skipped by policy, Phase B must not treat absent research fields as a gap.
- **Phase D (Render)** — already does filesystem cleanup (`rm -rf "$REPORT_RUN_DIR"`). Add the context-side equivalent: after the HTML is durable, the main agent's response should not echo the snapshot/context contents back to the user; reply with the HTML path + audit notes only (this is already the rule, but cross-link it here for completeness).

### Onboarding (`docs/onboarding_agent_guidelines.md`)

Statement parsing (PDF/CSV/screenshot extraction) is research-class — large `tool_use_result` blocks. Run extraction in a subagent that returns `{transactions_json: <path>, summary, row_count, hash}`. Main agent reads `transactions_json` only at the import step.

### Settings interview (`docs/settings_agent_guidelines.md`)

Lower priority — interview turns are user-driven and not token-heavy. No subagent needed unless the agent runs large research lookups (e.g., scraping benchmark indices); those should follow the protocol.

### Transactions agent (`docs/transactions_agent_guidelines.md`)

Reading `transactions.db` and price caches can be large. Wrap as research-class when answering broad questions ("show me everything about ticker X over 5 years"); narrow queries can stay in the main agent.

## What this protocol does NOT do

- It does **not** rewrite past API messages mid-stream. That is not achievable through user-space hooks in Claude Code; pretending otherwise leads to broken designs and broken cache.
- It does **not** drop data the agent has *already* loaded into the main context. Once a 50K-token tool_use_result is in the main transcript, only `/compact` or session-end can reduce its weight, and both invalidate the prompt cache. The protocol's leverage is preventive — keep it out, don't try to remove it.
- It does **not** apply to small data (<= a few thousand tokens). Subagent overhead is real; reserve isolation for genuinely large or repeatedly-loaded source material.

## Glossary

- **Temporary**: data declared, at creation time, to have a defined drop point and not to outlive its consumer artifact.
- **Result file** / **consumer artifact**: the durable, compact, schema-validated output of a phase. The only thing that crosses the phase boundary into downstream context.
- **Clean State**: the transition immediately following phase closure where Temporary data is dropped via the chosen mechanism (subagent exit / `/compact` / session end).
- **Research-class phase**: a phase whose deliverable is a file or short summary and whose internal work involves more than ~5K tokens of raw tool output.
- **Drop trigger**: the condition that authorizes Clean State transition. Default = `artifact_exists`.
