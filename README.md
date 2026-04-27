# Investments — Personal Research & Portfolio Reporting

This repo is a personal workspace for an AI investment research agent. It contains:

1. Agent specs (how the agent should think and write).
2. Personal data (your holdings, your settings) — git-ignored.
3. Generated HTML reports under `reports/` — also git-ignored.
4. A reference HTML design sample for the portfolio report.
5. Two Python templates under `scripts/` that the agent runs as-is — no need to author price-fetching or HTML-rendering code per session.

The agent runs inside an LLM client (e.g. Cowork / Claude). When you ask it to "produce a portfolio health check", it reads the specs and the personal data, runs `scripts/fetch_prices.py` to get the latest prices via `yfinance` (with the spec-mandated pacing and fallback), and runs `scripts/generate_report.py` to assemble the self-contained HTML in `reports/`.

## Repo layout

```
.
├── README.md                              ← you are here
├── AGENTS.md                              ← global agent spec (research style, output structure)
├── /docs/portfolio_report_agent_guidelines.md   ← spec for the portfolio report HTML deliverable
├── /docs/holdings_update_agent_guidelines.md    ← spec for natural-language holdings updates
├── SETTINGS.md                            ← your settings (git-ignored, copy from .example)
├── SETTINGS.example.md                    ← template for SETTINGS.md
├── HOLDINGS.md                            ← your holdings (git-ignored, copy from .example)
├── HOLDINGS.md.bak                        ← rolling backup written by the update agent (git-ignored)
├── HOLDINGS.example.md                    ← template for HOLDINGS.md
├── /scripts/
│   ├── fetch_prices.py                    ← canonical price-retrieval template (yfinance + fallback per spec §8)
│   └── generate_report.py                 ← canonical HTML rendering template (per spec §10/§13/§14)
├── .gitignore
└── reports/
    ├── _sample_redesign.html              ← canonical visual reference (de-identified demo data)
    └── *_portfolio_report.html            ← generated reports (git-ignored)
```

## First-time setup

1. Copy the example files and fill in your real data:

   ```sh
   cp SETTINGS.example.md SETTINGS.md
   cp HOLDINGS.example.md HOLDINGS.md
   ```

2. Edit `SETTINGS.md`:
   - Pick your preferred language.
   - Adjust the investment-style bullets to reflect your real risk tolerance.
   - (Optional) Tune the position-sizing rails the portfolio agent uses for warnings.

3. Edit `HOLDINGS.md`:
   - Replace every line with your actual positions.
   - Keep the four-bucket structure (`Long Term`, `Mid Term`, `Short Term`, `Cash Holdings`).
   - One lot per line: `<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]` — the trailing `on YYYY-MM-DD` is the lot's acquisition date (powers hold-period analytics), and `[<MARKET>]` is the market-type tag the price agent uses to format the `yfinance` symbol and pick the right fallback hierarchy.
   - Common market tags: `[US]`, `[TW]`, `[TWO]`, `[JP]`, `[HK]`, `[LSE]`, `[crypto]`, `[FX]`, `[cash]`. The full table lives in `HOLDINGS.example.md` and `docs/portfolio_report_agent_guidelines.md` §4.1.
   - Use `?` when cost basis or date is unknown — the agent renders the affected metric as `n/a` (vs. `—` for cells that never apply, e.g. cash P&L) rather than guessing.

`HOLDINGS.md`, `HOLDINGS.md.bak`, and `SETTINGS.md` are listed in `.gitignore`. They never leave your machine via git.

## How to use the agent

Open this folder in your LLM client. There are three things you can ask it to do:

### 1. Research questions (any time)

- "Analyze NVDA against my current position."
- "What is my exposure to the AI theme right now?"
- "Should I trim my short-term book before this week's earnings?"

The agent reads `SETTINGS.md` for tone and `HOLDINGS.md` for positions, then follows the research framework in `AGENTS.md` (bottom-line first, fundamentals, valuation, technicals, risk, playbook, scoring, verdict).

### 2. Portfolio health check

- "Produce today's portfolio health check."
- "Run my pre-market battle report."

The agent follows `/docs/portfolio_report_agent_guidelines.md` to produce a self-contained HTML report in `reports/`. The 11 sections (in order): today's summary, portfolio dashboard (KPIs), holdings table with P&L and per-lot popovers, holding period & pacing, theme/sector exposure, latest material news, forward-30-day event calendar, high-risk and high-opportunity list, recommended adjustments, today's action list, and sources & data gaps. A high-priority alerts banner sits above the 11 when any trigger fires.

Under the hood, the agent runs the two canonical Python templates rather than re-authoring the work each time:

```sh
# 1. Latest prices via yfinance (with §8.3 pacing, §8.4 auto-correction, §8.5 fallback)
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

# 2. HTML render (reads CSS from reports/_sample_redesign.html — the visual reference)
python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

The `report_context.json` is the agent's editorial layer: today's verdict prose, news items it gathered via web search, recommended adjustments, and the action list. Numeric content (totals, weights, P&L, hold period, pacing distribution, sources audit) comes from the two scripts mechanically.

### 3. Update holdings via natural language

Just describe the trade. Examples:

- "I bought 30 NVDA at $185 yesterday."
- "Sold 10 TSLA at $400 today."
- "Log trade: 5 BTC at 78,500 on 2026-04-25, long-term."
- "Trim 50% of my INTC short-term lots at $82."
- "Fix the GOOG lot from last September: 70 shares not 75."

The agent will:

1. Parse the trade(s) and echo every assumption (defaulted date, inferred bucket, currency, etc.).
2. Show a unified diff of `HOLDINGS.md` plus the resulting bucket totals and (for sells) realized P&L per lot.
3. Wait for an explicit `yes` from you in the same turn.
4. Back up the existing file to `HOLDINGS.md.bak`, write the new file, re-read it to verify, then reply with the path.

It will **never** silently overwrite. It will **never** invent missing fields. If something is ambiguous (no price currency, multiple matching cash lines, unknown bucket for a new ticker), it asks one specific question. Full rules live in `/docs/holdings_update_agent_guidelines.md`.

## Generated reports

Portfolio reports are written to `reports/` with the naming pattern:

```
reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html
```

The HTML is a single self-contained file — no external CSS, JS, fonts, or chart libraries — so you can open it directly in a browser, share it, or archive it. There is **no Markdown summary or companion file** any more; the HTML is the single deliverable.

`reports/_sample_redesign.html` is the canonical visual reference. It uses fully fictional data and exists only to lock in the design language. Do not delete it; both the portfolio agent and `scripts/generate_report.py` read its CSS as the single source of styling.

## Editing the agent specs

`AGENTS.md`, `/docs/portfolio_report_agent_guidelines.md`, and `/docs/holdings_update_agent_guidelines.md` are the contracts that shape every agent run. Treat them like prompts under version control:

- Change them when you want to change *how* the agent thinks or writes.
- Don't put personal data in them — that belongs in `SETTINGS.md` or `HOLDINGS.md`.
- After significant edits, ask the agent to regenerate one report so you can verify the new behavior.

## Privacy

- `HOLDINGS.md`, `HOLDINGS.md.bak`, `SETTINGS.md`, and any generated `*_portfolio_report.html` are git-ignored.
- Only the agent specs, the example templates, the Python script templates under `/scripts/`, the README, and the visual reference sample are tracked.
- If you fork or share this repo, only the templates and specs travel with it; your real positions, backups, and reports stay local.

## Disclaimer

This repo and the reports it produces are for personal research only. They are not financial advice, do not constitute a solicitation to buy or sell any security, and should not be relied on for trading decisions without independent verification. The agent will surface data gaps and uncertainty, but it can still be wrong — verify before acting.
