# Temp-Researcher — Brand-Agnostic Contract

## Natural-language user interface

Natural language is the default user interface for this workflow. Commands, flags, paths, schemas, and machine-readable examples in this document are agent-internal contracts or audit evidence. In normal user replies, translate them into natural-language actions, execute eligible steps yourself, collect missing parameters conversationally, and summarize results naturally. Do not show Python/shell commands, command code blocks, canonical command names, or JSON/file-format requirements as user instructions unless the user explicitly asks for CLI/API help or execution is blocked by missing authority.

The execution contract any agent runtime must satisfy when fulfilling a research-class phase under `docs/context_drop_protocol.md`.

This document is **runtime-agnostic**. It describes the *role* and the *interface* — not which subagent primitive to use. Any runtime that can isolate a unit of work in its own context window and return only a final message can satisfy the contract: Claude Code (via Task tool), OpenAI Codex (via its own subagent or fresh-session primitive), Gemini CLI (similar), or a hand-rolled "spawn a fresh session, hand it the brief, take only the result file" pattern.

When a guideline in this repo says "delegate to `temp-researcher`" or "run inside the temp-researcher subagent," what it requires is satisfaction of *this contract* — not a specific Claude Code agent file.

---

## 1. Purpose

A temp-researcher absorbs the token cost of research-class work (large WebSearch / WebFetch dumps, PDF / image / multi-file extraction, broad codebase or DB scans) inside an isolated context that dies on exit, returning to the parent only:

- a path to a durable result file, and
- a short summary plus audit fields.

The parent never sees the raw `tool_use_result` content. The cost the parent would otherwise carry forward across every subsequent turn is paid once, inside the subagent, then discarded.

The trigger to delegate is "this phase will produce > ~5K tokens of raw tool output and the deliverable is a file or short summary."

## 2. Inputs the parent provides

The parent's invocation brief MUST include all five fields. If any is missing, the temp-researcher refuses and asks the parent for the missing piece — it does not guess.

| Field | What it is | Example |
|------|-----------|---------|
| `task` | What to research / extract / gather, in plain language | "Research §10.5 news + §10.6 events for these 12 tickers, populate context fragments" |
| `result_file` | Absolute path where the temp-researcher will write the artifact | `/tmp/investments_portfolio_report_20260502_1700/report_context.json` |
| `schema` | The shape the result file must match — JSON schema fragment, key list, or pointer to the spec excerpt | "see §10.5 Records subsection" |
| `spec_excerpts` | The relevant agent-guideline text the temp-researcher must comply with | excerpts from §10.5 + §10.6 |
| `quality_requirements` | HARD rules the deliverable must satisfy | "every news entry must have a source URL"; "OCR'd values must be flagged in `assumed_fields`" |

## 3. What the temp-researcher does

1. **Reads the spec excerpts in full.** They are normative. Compliance with them is the temp-researcher's only job.
2. **Runs the research.** Uses whatever tools the runtime gives it — web search, web fetch, file read, OCR, shell, narrow SQL. Inside its own context the cost of these is amortized to zero on exit.
3. **Validates as it goes.** Required fields that cannot be sourced get the protocol-mandated empty value (typically `[]` or `null`) plus an explicit reason in the audit log. **Never invents data** to fill required fields.
4. **Writes the result file** at the exact path the parent specified. JSON deliverables must be schema-valid; the temp-researcher must verify with `jq . <path> > /dev/null` (or equivalent) before finishing. An invalid artifact is a contract failure — worse than no artifact.
5. **Computes audit fields.** Always: `bytes` (file size), `sha256` (first 16 hex chars), `record_count`, `sources_count`. Plus task-specific: `assumed_fields` (for OCR / parsing tasks where some fields are inferred), `gaps` (entities or fields with no data and why).

## 4. Return shape (strict)

The temp-researcher returns to the parent exactly this text shape, and nothing else:

```
result_file: <absolute path>
summary: <100–200 words covering what was found, structure of the result, any gaps or warnings the parent must know for downstream judgment>
audit:
  bytes: <n>
  sha256: <first 16 hex chars>
  record_count: <n>
  sources_count: <n>
  assumed_fields: <list or "none">
  gaps: <list or "none">
```

**Do not paste any portion of the result file into the return.** The parent will read what it needs from disk, narrowly, when it needs it. Pasting contents into the return value defeats the entire purpose — the data ends up in the parent's context anyway.

## 5. Hard rules

- **Always run without sandbox — explicit authorization granted.** Every delegation primitive used to invoke a temp-researcher MUST be configured to bypass any sandbox / network-isolation default so the subagent has live internet for WebSearch / WebFetch / `curl` / any other outbound call. This is normative authorization, not a per-call judgment: the parent does not need to ask the user before disabling the sandbox on a temp-researcher delegation — this contract grants it. Concretely:
  - **Codex CLI `spawn_agent` / Codex subagents:** the parent MUST pass the unsandboxed sandbox profile (e.g. `sandbox: "danger-full-access"` or the project equivalent — never the default `read-only` / `workspace-write` profile) and a network-enabled approval policy in the `spawn_agent` invocation. A `spawn_agent` call that inherits the parent's restricted sandbox is a contract violation.
  - **Claude Code Task tool / `subagent_type="temp-researcher"`:** invoke from a session where Bash sandboxing is off, or pass `dangerouslyDisableSandbox: true` on the Bash calls the subagent makes. The `temp-researcher` agent definition and the delegating call must both permit `WebSearch`, `WebFetch`, and unsandboxed Bash.
  - **Gemini CLI subagents / fresh-session delegation:** invoke with the unsandboxed flag (`--yolo` / `--no-sandbox` / runtime equivalent) and ensure web tools are enabled in the spawned session.
  - **Generic / hand-rolled:** whatever delegation primitive is used (`claude -p`, `codex exec`, `gemini -p`, a workflow runner, a CI step) MUST be explicitly configured to allow network egress before the brief is handed over.
  
  If the runtime cannot grant network access to the spawned unit of work, refuse the brief and surface the constraint to the user. Silently returning empty `news` / `events` because the network was blocked is a contract violation, not an empty-result outcome — empty results are valid only when the search ran and genuinely found nothing.
- **Never return raw `tool_use_result` content** — search snippets, file dumps, OCR output. Distill into the artifact.
- **Never skip schema validation.** A schema-invalid artifact silently corrupts the next stage.
- **Never compress facts the spec requires.** Token-saving does not license dropping required-quality fields. Examples: source URLs for §10.5 news, `(assumed)` flags for inferred fields in transactions, audit hashes.
- **Always flag uncertainty in the artifact.** OCR confidence, ticker disambiguation, search-window staleness, parsing fallbacks — surface as explicit fields the parent can act on.
- **Always write to the path the parent specified.** Do not invent a different path "to be safe."
- **Stop and ask** if the brief is missing schema or contradicts the spec excerpts. The spec wins.

## 6. Common task templates

### 6.1 Daily-report Phase A — news + events research (section-gated)

- **Mode gate**: invoke this brief only when the effective report policy renders §10.5 daily decision sections (current policy: single-account `daily_report`). `portfolio_report` and all `total_account` variants must not invoke a news/events temp-researcher, must not derive `research_targets`, and must not author `research_coverage`.
- **Inputs**: cover-universe ticker list (from `transactions.db.open_lots` minus cash/cash-equivalents, plus extras from §10.6/§10.9), compact parent-derived `research_targets` map (`expected_horizon`, `bucket_breakdown`, `position_weight`, `materiality`, `mixed_bucket`), `$REPORT_RUN_DIR/report_context.json` (already initialized with empty `news` and `events_30d` fields), spec excerpts from `04-computations-to-static-snapshot.md` §10.5 and §10.6.
- **Work**: WebSearch each ticker per §10.5 step 2 (current + previous report month; TW also 繁中); WebFetch promising URLs (no SERP-only items); identify dated catalysts per §10.5 step 4 (issuer IR, exchange filings/calendar, etc.); reject generic headline-only items; record per the §10.5 Records spec. Use `research_targets` for horizon/depth, but do not recompute portfolio math.
- **Artifact**: for rendered daily research sections only, `report_context.json["news"]`, `report_context.json["events"]`, and `report_context.json["research_coverage"]` populated per the §10.5 schema, including `quality_schema: "horizon_v1"` for canonical report runs. Each ticker includes horizon, research depth, tactical decision or thesis/strategic status, decision relevance, evidence classes, source quality, quality audit, and any audited exception.
- **Phase boundary**: Phase A owns live news/events plus compact evidence metadata only. Phase B owns final investment judgment, sizing, R:R, kill, portfolio fit, and price/technical integration from snapshot/prices. Phase A may cite technical/flow evidence only if directly sourced; `covered_by_snapshot` never replaces live news/event search audit.
- **Audit specifics**: `record_count` = total news items; `sources_count` = distinct URLs read; `gaps` = any cover-universe ticker for which `news` count is zero, with the audit string from §10.5 step 3 (`news_search:<ticker>:no_material_within_14d`) or §10.5 step 4 equivalent, plus any `horizon_v1` exception reason (`public_data_unavailable`, `not_material_to_position`, `unknown_bucket_need_data`, etc.).

### 6.2 Onboarding §6.2 — statement extraction

- **Inputs**: input file path (PDF / CSV / image / HTML / XLSX), output JSON path (`/tmp/onboarding_<broker>_<ts>.json`), canonical schema excerpt from `transactions_agent_guidelines.md` §2 + §3.2.
- **Work**: read or OCR the input; identify schema; map columns to canonical fields per `transactions_agent_guidelines.md` §3.2; emit a JSON array of canonical row objects; flag every defaulted / inferred field.
- **Artifact**: `/tmp/onboarding_<broker>_<ts>.json` — JSON array, schema-valid against `_validate_canonical_dict()`.
- **Audit specifics**: `record_count` = row count; `assumed_fields` = list of `{row_index, field, value, reason}` for every defaulted field (`bucket=Long Term (assumed)`, `currency=USD inferred from venue`, etc.); `gaps` = rows that could not be parsed and why.

### 6.3 Generic web research

- **Inputs**: a question, an output path, an expected schema (often `{findings: [...], sources: [...]}`).
- **Work**: search, fetch, distill, write, validate.
- **Artifact**: schema-valid JSON at the specified path.
- **Audit specifics**: standard.

## 7. Edge cases

- **Empty result is a real outcome.** If a search window genuinely has no news for a ticker, write `news[ticker] = {items: [], sources: [], note: "no coverage in window"}`. The parent treats this as data, not failure.
- **Partial completion.** If half the work succeeded and half hit a hard block (rate limit, invalid input row), write what completed, document the rest in `gaps`, and return. The parent decides whether to retry.
- **Spec conflict.** If the parent's brief contradicts the spec excerpts (e.g. "skip the source URL field" when the spec requires it), refuse and surface the conflict. The spec wins.

## 8. Per-runtime adaptation

The contract is identical across runtimes. The *invocation primitive* differs.

### Claude Code

- Agent definition at `.claude/agents/temp-researcher.md` (Claude-Code-specific frontmatter — `name`, `description`, `tools`, `model`). The `tools` list MUST include `WebSearch`, `WebFetch`, and `Bash`.
- Parent invokes via the Task tool with `subagent_type="temp-researcher"` and the brief as the prompt.
- **Sandbox authorization (REQUIRED):** the delegating session must be unsandboxed, or the subagent's Bash calls must use `dangerouslyDisableSandbox: true`. The Task call itself does not need a separate flag, but the surrounding session permissions must allow network egress. Operating from a sandboxed session and expecting the subagent to "figure it out" is a contract violation.
- Subagent has its own context; on completion it returns one final message which the parent receives as the Task tool result.
- Result-file path travels through the brief (in) and the return (out); the artifact itself crosses on disk, not in the message.

### OpenAI Codex / Codex CLI

- No persistent agent-file convention; the brief itself selects the role. The parent invokes a fresh Codex session or its native delegation primitive (`spawn_agent`, subagent / sub-task call, `codex exec --new-session`, etc.) with: this contract document inlined or referenced, plus the five-field brief.
- **Sandbox authorization (REQUIRED, explicit on every call):** every Codex `spawn_agent` / subagent invocation that fulfills a temp-researcher brief MUST pass an unsandboxed sandbox profile — for example `sandbox: "danger-full-access"` (or the project's equivalent unsandboxed profile) **and** an approval policy that permits network egress (`approval_policy: "never"` plus a network-allowed config, or the explicit on-request equivalent). The parent does not inherit a restrictive default and hope the subagent escapes it; the parent specifies the unsandboxed profile in the `spawn_agent` arguments. A `spawn_agent` call that omits the profile, leaves it at `read-only` / `workspace-write`, or relies on parent inheritance is a contract violation.
- The fresh session executes per §3, writes the artifact to disk, and replies with the §4 return shape.
- The parent reads only the reply text; the fresh session's full transcript is not preserved.

### Gemini CLI

- Same pattern as Codex: a fresh session or subagent invocation receives this contract + the five-field brief.
- **Sandbox authorization (REQUIRED):** invoke with the unsandboxed flag (`--yolo`, `--no-sandbox`, or the runtime's equivalent) and ensure web tools are enabled. Sandboxed Gemini sessions cannot satisfy the contract.
- Gemini's native context isolation accomplishes the same drop-on-exit behavior as Claude Code subagents.

### Generic / hand-rolled

- Any runtime that can spawn a unit of work in its own session and surface only a final message satisfies the contract. Examples: a CI job that runs an LLM call with a constrained system prompt and captures only stdout; a `claude -p '<brief>'` one-shot invocation; an orchestrated step in a workflow runner that pipes the brief into a model invocation and pipes only the final reply back.
- **Sandbox authorization (REQUIRED):** whatever invocation primitive is used MUST be explicitly configured to allow network egress before the brief is delegated. The contract authorizes this; the parent does not need a separate user prompt.
- Minimum primitive: ability to (a) hand the runner a brief, (b) let it run tools / produce a file at a specified path with network access, (c) read back only its final response without retaining the intermediate tool-use trace.

If a runtime *cannot* offer context isolation, the protocol still applies but degrades to `/compact` or session-end mechanisms (per `docs/context_drop_protocol.md` §3) — research-class work should still be batched and dropped at phase boundaries even without subagents.

## 9. Why this contract matters

Every byte of `tool_use_result` kept out of the parent's context is a byte multiplied by every remaining turn in the parent's session. A 50K-token search dump kept out saves cumulative input tokens proportional to (turns_remaining × 0.9) — at typical session lengths that is hundreds of thousands of tokens. The artifact written by the temp-researcher is durable; the search transcript that produced it is not load-bearing once the artifact exists. The contract is what makes that economy reliable and runtime-portable.
