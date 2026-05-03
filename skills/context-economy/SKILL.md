---
name: context-economy
description: Enforce context-drop and temp-researcher discipline for large extraction, research, PDF/OCR, web-search, multi-file, or broad database phases. Use when a workflow will produce more than about 5K tokens of raw tool output, needs a result artifact or short summary, or mentions context economy, context drop, temp-researcher, subagent isolation, compaction, or keeping research data out of the parent context.
---

# Context Economy

## Core Rule

This skill is the context hygiene gate. Follow `docs/context_drop_protocol.md` and `docs/temp_researcher_contract.md`; this skill is only the trigger and checklist.

Use it whenever a phase's internal work is likely to produce > 5K tokens of raw tool output and the deliverable is a file or short summary. Typical cases: daily-report §10.5 news/events research, onboarding statement extraction, large broker imports, PDF/OCR/image parsing, broad web research, broad multi-file reads, and broad transaction/database scans.

## Natural-Language User Interface

Treat natural language as the only default user interface. Command snippets, flags, paths, and machine formats below are internal agent contracts or audit evidence, not user instructions. Execute eligible steps yourself via tools, summarize results naturally, and collect missing parameters conversationally. Do not ask the user to run commands, choose flags, know canonical command names, assemble files, or write JSON unless they explicitly request CLI/API instructions or execution is blocked by missing authority. Confirmation gates ask for the required decision in natural language and must not delegate command execution or machine formatting to the user.

## Decision Gate

Before starting a tool-heavy phase, classify it:

- **Small / local**: ≤ a few thousand tokens, no repeated large reads, no result artifact needed → stay in parent.
- **Research-class / temporary**: > 5K raw tool-output tokens, or large WebSearch/WebFetch/PDF/OCR/multi-file/DB output, and a compact artifact can represent the result → isolate it.
- **Forbidden by mode**: if the active report/account/workflow policy says the phase must not run (for example `portfolio_report` news/events/actions research), skip it instead of delegating.

## Temp-Researcher Contract

For research-class phases, run the work in an isolated temp-researcher / subagent / fresh session. The parent brief must include:

- `task`
- `result_file` absolute path, usually under `/tmp`
- `schema`
- `spec_excerpts`
- `quality_requirements`

The temp-researcher writes the artifact, validates it, computes audit fields, and returns only:

```text
result_file: <absolute path>
summary: <100-200 words>
audit:
  bytes: <n>
  sha256: <first 16 hex chars>
  record_count: <n>
  sources_count: <n>
  assumed_fields: <list or "none">
  gaps: <list or "none">
```

Do not paste raw findings, search dumps, OCR text, table extracts, or result-file contents back into the parent response. The result file is the boundary.

## Artifact Rules

- Write temporary artifacts under `/tmp` unless the active workflow specifies another temp directory.
- Validate JSON artifacts with `jq . <path>` or an equivalent parser before returning.
- Record enough audit to prove the artifact is real: bytes, hash, record count, source count, gaps, and assumed fields where relevant.
- Parent reads artifacts lazily and narrowly; prefer `jq`, targeted grep, offsets, or schema fields over full-file dumps.
- No artifact, no drop: if the artifact is missing or invalid, fail or retry according to the owning workflow's fallback rule.

## Runtime Adaptation

Use the isolation primitive available in the current agent runtime:

- Codex: native subagent/fresh session where available.
- Claude: Task tool / temp-researcher agent where available.
- Gemini: subagent or fresh CLI session where available.
- Hand-rolled: launch a fresh process/session, give it the brief, take only the strict return shape.

When the phase requires live web access, the isolated worker must have network access. If the runtime cannot provide it, stop and surface the constraint; do not silently return empty research.

## Stop Conditions

Stop or reroute when:

- the owning workflow forbids the phase;
- the temp-researcher brief lacks `result_file`, `schema`, or `quality_requirements`;
- the artifact cannot be written or validated;
- the worker returns raw data instead of `{result_file, summary, audit}`;
- the parent would need to read the full raw artifact into context.
