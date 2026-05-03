# Help — Agent Guidelines

Brand-agnostic contract for "what can I do here?" requests. Any agent
(Claude Code, OpenAI Codex, Gemini CLI, or similar) should follow this
when the user asks for a capability overview rather than a specific
workflow.

The goal: in one short reply, give the user a clear menu of what this
repo enables, *how to ask for each thing in plain English*, and which
deeper doc the agent will follow once they pick. This is the
conversational front door, not a reprint of `README.md`.

## 1. When this applies

Trigger on any of:

- "Help" / "What can I do here?" / "What can you do?"
- "How does this repo work?" / "Show me what's possible."
- "What should I ask you?" / "I don't know where to start."
- A user who has just finished onboarding and asks "now what?"

If the user is asking about a *specific* capability already
("generate a report", "log a trade", "import this CSV"), do **not**
render the help menu — route directly to the relevant workflow doc.

## 2. State-aware reply

Before rendering the menu, check repo state using the account-aware
detection:

```sh
# Detect active account (multi-account layout)
python scripts/transactions.py account list 2>/dev/null \
  || ls accounts/ 2>/dev/null \
  || echo "(no accounts)"

# Check settings + DB for the active account
python scripts/transactions.py db stats 2>/dev/null
```

For a simpler one-shot check when `transactions.py` is not yet available:

```sh
ls accounts/.active accounts/ SETTINGS.md transactions.db 2>/dev/null
```

Tailor the reply:

- **Cold start** (`accounts/` missing or empty, and no root `SETTINGS.md` /
  `transactions.db`) — lead with onboarding. Tell the user the other
  workflows depend on having those two artifacts in place. Point at
  `docs/onboarding_agent_guidelines.md`.
- **Legacy layout detected** (root `SETTINGS.md` or `transactions.db`
  present, no `accounts/`) — note that migration is needed and any script
  run will prompt for it automatically.
- **Empty DB** (active account's `transactions.db` exists, 0 rows) — lead
  with transaction recording. The other workflows work but will be empty.
- **Ready** (active account has settings + DB with rows) — render the full
  four-item menu.
- **Multiple accounts exist** (`account list` shows ≥ 2 entries) — after
  the four-item menu, add a **"Switch account"** sub-action (see §3 E).

State the detected state in one sentence at the top so the user knows
which mode they are in.

## 3. The capability menu

Render exactly these four items, in this order, in the user's
`SETTINGS.md` `Language` if available (else English). Each item is one
line of plain-English ask + one line of agent action. Do not list CLI
commands here — the user is asking the agent, not the shell.

### A. Onboarding (one-time)

- **Ask like:** "Help me get started." / "Onboard me — here's my
  brokerage statement." (attach PDF / CSV / JSON / XLSX / screenshot /
  text)
- **Agent does:** detects missing `SETTINGS.md` / `transactions.db`,
  bootstraps both, converts whatever format you handed it into canonical
  transactions, confirms before writing, runs `verify`. Contract:
  `docs/onboarding_agent_guidelines.md`.

Hide this item from the menu once both artifacts exist and the DB has
rows.

### B. Record a transaction (most frequent flow)

- **Ask like:** "I bought 30 NVDA at $185 yesterday." / "Sold 10 TSLA
  at $400 today." / "Q1 GOOG dividend, $80." / "Deposited $5,000." /
  "Here's my Schwab CSV — please import it."
- **Agent does:** parses the message (or file), shows the canonical
  JSON plan, asks for `yes`, then writes + auto-rebuilds + verifies.
  Hard rule: never writes without explicit confirmation. Contract:
  `docs/transactions_agent_guidelines.md`.

### C. Research a name or the portfolio (read-only)

- **Ask like:** "Analyze NVDA against my current portfolio." / "What
  is my AI exposure now?" / "Should I trim short-term positions before
  earnings?" / "Is XYZ a fit for my strategy?"
- **Agent does:** reads `SETTINGS.md` (full `Investment Style And
  Strategy` section), loads positions from `transactions.db`, and
  responds first-person as the user — variant view, sized in pp of NAV,
  with kill criteria. No writes. Contract: `AGENTS.md` (Output structure
  + sourcing rules).

### D. Generate a report (choose type + scope)

- **Ask like:** "Generate my daily report." / "Generate my portfolio report." / "Run a consolidated all-accounts daily report."
- **Agent does:** first separates content type from account scope. If the user asks to generate a report without choosing `daily_report` or `portfolio_report`, the agent stops and asks which type they want before running the pipeline. `daily_report` keeps daily decision/editorial sections but removes Profit Panel, Performance Attribution, Discipline Check, Holding Period/Pacing, and P&L Ranking. `portfolio_report` keeps the longer math/position view but removes immediate-attention/news/events/actions/trading-psychology sections and the holdings Action column. Scope is either one account or `--all-accounts`; total is not a report type. The pipeline runs `fetch_prices` → `fetch_history` → `transactions.py snapshot` → only the required editorial gather → `validate_report_context.py --report-type ...` → `generate_report.py --report-type ...`. Intermediate JSON lives under `/tmp` in `$REPORT_RUN_DIR` and is deleted after success.
  In auto / unattended environments, the agent should obtain explicit
  consent before sending tickers to external market-data sources.
  Contract: `docs/portfolio_report_agent_guidelines.md` and every
  numbered file under `docs/portfolio_report_agent_guidelines/`.

### E. Total-account scope note (conditional — show only when ≥ 2 accounts exist)

- **Ask like:** "Run this across all accounts" or "total account daily report."
- **Agent does:** applies `--all-accounts` to the selected `daily_report` or `portfolio_report`. Output lands under `accounts/_total/reports/<dated>_total_account_<report_type>.html`. Total scope suppresses strategy-dependent/editorial sections; it does not create a third report type.

Hide this note when only one account exists.

### F. Switch account (conditional — show only when ≥ 2 accounts exist)

- **Ask like:** "Switch to my Roth account." / "Use the 'trading' account."
  / "Which account am I on?" / "List my accounts."
- **Agent does:** runs `python scripts/transactions.py account list` to
  show all accounts (active marked with `*`), then runs
  `python scripts/transactions.py account use <name>` on the user's choice.
  All subsequent commands in the session resolve against the new active
  account (equivalent to passing `--account <name>` on every call).
  No writes to any DB. Contract: `docs/transactions_agent_guidelines.md`
  (Active-account resolution section).

Hide this item when only one account exists.

## 4. Customisation pointer

Below the menu, add one line:

> "To change how I act as you — risk appetite, sizing, off-limits zones,
> language, base currency — say *'walk me through my settings'* and
> I'll interview you. Or edit `SETTINGS.md` directly."

The interview path follows `docs/settings_agent_guidelines.md`. Do not
enumerate every SETTINGS field in the menu reply.

## 5. What this menu does **not** include

- CLI command listings (the user is asking the agent, not the shell;
  manual CLI lives in `README.md` "Manual setup (fallback)").
- Schema / field reference (lives in `docs/transactions_agent_guidelines.md` §2).
- Report section taxonomy (lives in `docs/portfolio_report_agent_guidelines/`).
- API key setup, advanced flags, demo ledger workflow. Mention these
  only if the user asks specifically.

## 6. Format and length

- ≤ 25 lines total in the rendered reply, including the four menu items.
- One-line state sentence + four bulleted items + one-line customisation
  pointer is the target shape.
- No emojis unless `SETTINGS.md` requests them.
- Do not include CLI snippets in the menu reply itself; reference the
  contract docs instead.
- Close with a single open-ended prompt, e.g. "Which of these would you
  like to do?"

## 7. What does **not** belong here

- Generating a report, recording a transaction, or running onboarding
  inline. The help reply is a menu; once the user picks, switch to the
  matching contract doc and follow it end-to-end.
- Editing `SETTINGS.md` content beyond the customisation pointer.
- Recommending specific positions, themes, or trades (research happens
  under capability C, not in the help menu).
- Editing any spec under `docs/`. Help is rendering, not authoring.
