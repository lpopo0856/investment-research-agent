# Gemini Guide

Read `AGENTS.md` first. It is the project authority for workflow routing, investment behavior, safety floors, and verification expectations.

This file is only a Gemini adapter. Do not duplicate workflow rules here:

- Use root-level `skills/*/SKILL.md` as the first-line workflow contracts.
- Use referenced `docs/*.md` as the detailed source of truth.
- For large extraction/research phases, use `skills/context-economy/SKILL.md`; use a Gemini subagent/fresh session as the isolated worker when available.
- Put scratch/report intermediates under `/tmp` unless the active skill/doc explicitly allows a final deliverable path.

If this file and `AGENTS.md` disagree, follow `AGENTS.md`.
