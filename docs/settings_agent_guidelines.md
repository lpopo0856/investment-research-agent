# Settings — Agent Guidelines

Brand-agnostic contract for setting up or editing `SETTINGS.md`. Any
agent (Claude Code, OpenAI Codex, Gemini CLI, or similar) should follow
this when the user wants to create, fill in, review, or revise their
settings — including when invoked from
`docs/onboarding_agent_guidelines.md` §4.

The goal: turn the user's plain-English answers into a `SETTINGS.md`
that the research and report workflows can use, with the
`Investment Style And Strategy` section written richly enough that
downstream output sounds like the user wrote it themselves.

This document does **not** replace `SETTINGS.example.md`. That file is
the canonical template at the repo root; `account create <name>` copies
it into `accounts/<name>/SETTINGS.md` for each new account. This doc is
the elicitation contract for filling it in.

### Where SETTINGS.md lives

In the multi-account layout, each account owns its settings file:

```
accounts/<active>/SETTINGS.md
```

Resolve the active account via `accounts/.active`, or use
`--account <name>` explicitly. Before editing, confirm which account is
active:

```sh
python scripts/transactions.py account list   # shows active account (*)
python scripts/transactions.py account use <name>   # switch if needed
```

`SETTINGS.example.md` at the repo root is the master template. Never
edit it directly for user settings — it is the source that
`account create` copies from.

---

## 1. When this applies

Trigger on any of:

- `SETTINGS.md` does not exist (cold start, called from onboarding §4).
- "Help me set up my settings." / "Walk me through my strategy."
- "Edit my SETTINGS." / "Review my SETTINGS." / "Update my style."
- "What strategy did you internalise?" — read-only review variant.
- The user wants to change `Language`, `Base currency`, sizing rails,
  or API keys.

If the user is asking a *research* question or a *transaction* question,
do **not** start the settings interview. Route to the matching doc.

## 2. Hard safety rules

1. **Never** write to `SETTINGS.md` without showing the proposed content
   (full file or unified diff) and getting an explicit `yes` in the same
   turn.
2. **Always** back up to `SETTINGS.md.bak` before any write, except the
   first creation when the file does not yet exist.
3. **Never** invent the user's strategy. Fill the
   `## Investment Style And Strategy` section only from things the user
   said in this conversation, or from the neutral PM defaults documented
   in `AGENTS.md` (and only when the user explicitly accepts that
   fallback).
4. **Never** paraphrase the user's words in a way that loses risk
   nuance ("I can take big drawdowns if EV is positive" is *not* the
   same as "I have high risk tolerance"). Quote close to the source.
5. **Never** add API keys you generated, guessed, or remembered from
   another session. Keys come from the user's own paste only.
6. **Never** store the user's strategy or keys outside `SETTINGS.md`
   (no agent memory, no notepad, no commit). `SETTINGS.md` is
   gitignored; anything else is a leak.

## 3. Detection — what state is the file in?

Before starting an interview, resolve the active account and check its
settings file:

```sh
# Determine active account
cat accounts/.active 2>/dev/null || echo "default"

# Check for the account's settings and the repo template
ls accounts/<active>/SETTINGS.md SETTINGS.example.md 2>/dev/null
```

Map the result:

| State | Action |
|-------|--------|
| `SETTINGS.example.md` missing | Stop and tell the user the repo template is missing — do not proceed. |
| Only `SETTINGS.example.md` exists (no account file) | Cold start. Run §4 (full interview); writes to `accounts/<active>/SETTINGS.md`. |
| `accounts/<active>/SETTINGS.md` exists | Read it. Run §5 (review / edit). |

Always read `accounts/<active>/SETTINGS.md` if it exists before asking
anything — do not re-interview the user on fields they already filled in.

## 4. Cold start interview

Run when `SETTINGS.md` is being created from scratch.

### 4.1 Bootstrap the file

`account create` (run during onboarding §5) already copies the template.
If the directory exists but the file is missing, copy it manually:

```sh
cp SETTINGS.example.md accounts/<active>/SETTINGS.md
```

Tell the user what just happened: "Created `accounts/<active>/SETTINGS.md`
from the template. It is gitignored — your answers stay local. I'll walk
you through the sections that matter most."

### 4.2 Light fields (one batch, conversational)

Ask these together in one short message. Use defaults if the user does
not answer or says "use defaults". Confirm before writing.

| Field | Default | Notes |
|-------|---------|-------|
| `Language` | `english` | Built-in dictionaries: `english`, `traditional chinese`, `simplified chinese`. Other single-language values allowed. Detect from the user's prior messages — do not ask in English if they wrote in Chinese. |
| `Base currency` | `USD` | ISO 4217 (`USD`, `TWD`, `JPY`, `HKD`, `GBP`, `EUR`, …). Pick once and keep stable. |
| `Time zone` | `Asia / Taipei` | Optional. From the example template's "Reporting cadence". |

Do **not** ask about reporting cadence, sample sizing rails, or API keys
in this batch. The defaults in `SETTINGS.example.md` are reasonable; the
user can edit them later (§5).

### 4.3 Investment Style And Strategy — the main interview

This is the section that drives every recommendation. Treat it as the
core deliverable; everything else is dressing.

Frame it for the user once, in their language, before asking:

> "The next part is the most important. The agent reads this section
> every run and acts *as you* — your voice, your risk appetite, your
> entry and exit discipline. Vague text produces generic output; rich
> text produces output that sounds like you wrote it. I'll ask you a
> few short questions and draft the section in your voice for you to
> review. Sound good?"

Wait for `yes` (or `let me write it myself` → skip to §4.4).

Ask these dimensions, **one or two at a time** (not as a long list).
Adapt order and skip what the user already volunteered. Quote
`SETTINGS.example.md` "Useful things to cover" verbatim if the user
asks for examples.

1. **Temperament & drawdown tolerance.** "How much volatility / loss
   can you actually live with — psychologically, not just on paper?
   Numbers ('I've ridden through -40% before') beat adjectives."
2. **Conviction & sizing.** "When you find a setup you really like,
   do you size up (Kelly-lite, concentrated bets) or stay flat-weight?
   How big is too big for one name before you trim?"
3. **Holding-period bias.** "Trader (days–weeks), swing (months),
   multi-year investor, or generational holder? What pulls you out
   early — fundamental break, technical break, time stop?"
4. **Entry discipline.** "Wait for confirmation (breakout, earnings
   beat, structural break) or front-run the setup? What is the minimum
   evidence you need before the first add?"
5. **Contrarian appetite.** "Comfortable buying when the tape disagrees
   with you, or only when consensus has come around?"
6. **Hype tolerance.** "How much optimistic framing do you want? Should
   every upside number be base / bull / bear bracketed, or is a single
   bull-case target fine?"
7. **Off-limits zones.** "Anything you flat-out won't own —
   unprofitable biotech, single-stock options, OTC, leveraged ETFs,
   meme coins, specific sectors?"
8. **Decision style.** "Bullets first or narrative? Do you want the
   agent to flag data gaps explicitly? Should it ever pad an action
   list, or always be willing to say 'no edge today'?"

After each answer, reflect it back in one short sentence and ask the
next dimension. Do not draft prose mid-interview — collect first, draft
after.

### 4.4 Drafting the section

Once the user has answered (or said "that's enough, draft what you
have"):

1. Compose the `## Investment Style And Strategy` body in **first
   person, present tense**, in the user's chosen `Language`. 5–15
   bullets is the right length. Quote distinctive phrases the user
   used verbatim — those are signal for the report's Strategy readout.
2. For dimensions the user did not answer, write nothing for them — do
   not pad with PM defaults silently. If the user explicitly asked for
   defaults, write them and tag with parenthetical `(default — please
   replace when you have a stronger view)`.
3. Show the **full proposed section** (not a diff — the section is new)
   and ask: `Confirm and write to SETTINGS.md? (yes / no / edit)`.

Write only on `yes`. On `edit`, ask which bullet to change. On `no`,
keep the example template intact and move on.

### 4.5 API keys block

Leave the optional Market Data API Keys block blank in the cold start.
Tell the user once: "There is an optional `Market Data API Keys` block
at the bottom of `SETTINGS.md` for fallback price providers. You can
fill it in later by saying 'set my Twelve Data key' — keys never enter
git." Do not interview for keys.

### 4.6 Wrap-up

After the file is written, run no commands; `accounts/<active>/SETTINGS.md`
is read on-demand by every workflow (resolved via `--account <name>` or
`accounts/.active`). End with one line: "Done. Your settings are saved.
Want to continue onboarding (initialise the database / import
transactions), or ask me a research question now?"

## 5. Review / edit existing SETTINGS.md

When `SETTINGS.md` already exists:

1. **Read it.** Do not assume what's in it; the user may have edited
   directly.
2. **Show a tight summary**, in the user's `Language`. Format:
   - Language: <value>
   - Base currency: <value>
   - Strategy bullets: <count> — first 2–3 paraphrased
   - Sizing rails: <single-name / theme / high-vol / cash-floor>
   - API keys set: <comma list of provider names with non-empty values, or "none">
3. Ask: "What would you like to change?" Do not auto-edit.
4. For each change request:
   - **Strategy edits** — re-run the relevant §4.3 dimension, show the
     before/after of just that bullet, confirm.
   - **Light field edits** (language, base currency, rails, time zone)
     — show before/after, confirm.
   - **API key edits** — accept the user's pasted key as-is; never
     reformat or "validate" it. Show the masked key (`sk-…last4`) in
     the diff, not the full value.
5. Before writing: `cp accounts/<active>/SETTINGS.md accounts/<active>/SETTINGS.md.bak`.
6. Show a unified diff (or full new section for strategy rewrites) and
   ask: `Confirm and write? (yes / no / edit)`.
7. Write only on `yes`. On any failure, restore the `.bak`.

### 5.1 Read-only review variant

When the user asks "what strategy did you internalise?" / "read me my
SETTINGS back" / similar, run the §5 step 2 summary and stop. Do not
offer to edit unless asked. This is the variant the report's reviewer
pass uses to verify alignment.

## 6. Multi-language reminder

The agent's questions, summaries, drafts, diffs, and confirmation
prompts must all be rendered in the user's `Language` once it is set.
The first interview turn (before `Language` is captured) follows the
language the user opened the conversation in. Do not bilingual the
output unless the user asked for it.

For non-built-in languages (anything other than `english`,
`traditional chinese`, `simplified chinese`), the agent should still
render its own messages in that language; the report renderer's UI
dictionary handling is a separate concern documented in
`SETTINGS.example.md` under `## Language`.

## 7. What does **not** belong here

- Generating a portfolio report or running research from inside the
  settings interview. Once `SETTINGS.md` is saved, route back to the
  workflow the user actually wanted (or to the help menu).
- Editing `transactions.db`, the schema docs, or any spec under
  `docs/`. Settings is user data, not contract.
- Interviewing for fields the example template does not expose
  (custom rails, custom personas, anything beyond `SETTINGS.example.md`).
  Add to the example template first via a separate spec change, then
  the interview can pick it up.
- Saving any answer outside `SETTINGS.md` — no agent memory, no
  notepad, no shared store. Strategy and keys are local-only by
  design.
