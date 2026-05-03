# Investment Research Agent

**README languages** · [English](README.md) · [繁體中文](docs/l10n/README.zh-Hant.md) · [简体中文](docs/l10n/README.zh-Hans.md) · [日本語](docs/l10n/README.ja.md) · [Tiếng Việt](docs/l10n/README.vi.md) · [한국어](docs/l10n/README.ko.md)

The English README is the canonical version. Other languages are reader-friendly translations.

Investment Research Agent is a private, local assistant for tracking your portfolio, recording trades, importing brokerage statements, and turning your holdings into clear research and action plans. Open the workspace with your assistant and describe what you want in normal language.

## Report Demo

**[Report Demo](https://lpopo0856.github.io/investment-research-agent/)**

## Main features

You do not need technical setup knowledge. Describe your intention in plain language, and the assistant will handle the workflow. If anything changes saved portfolio data, it will show you the proposed change and ask for confirmation before saving.

- **Get started** — create your first account, import your starting portfolio, and set up your investing style.
- **Set your strategy** — define risk tolerance, sizing style, holding period, language, base currency, and off-limits areas.
- **Manage accounts** — create, switch, review, and combine multiple brokerage, retirement, regional, or strategy accounts.
- **Record activity** — add buys, sells, deposits, withdrawals, dividends, fees, and currency conversions using normal wording.
- **Import broker files** — bring in statements, exports, spreadsheets, PDFs, screenshots, or pasted transaction history.
- **Fix records** — correct mistaken trades, remove duplicates, reconcile cash, and check open lots against a broker statement.
- **Research investments** — analyze stocks, ETFs, themes, sectors, markets, and portfolio exposure through your own strategy.
- **Daily report** — produce a current decision dashboard with prices, news, events, alerts, opportunities, suggested adjustments, and today’s action list.
- **Portfolio report** — review holdings, cash, allocation, profit and loss, concentration, pacing, and portfolio structure without daily trading noise.
- **Total report** — combine all accounts into one high-level view while keeping each account’s records separate.
- **Risk and exposure checks** — ask what is concentrated, overlapping, high risk, underfunded, or due for attention.

## Detailed usage

### Ask what is possible

If you are not sure where to start, say something like:

> "What can I do here?"
> "Show me what is possible."
> "Help."

The assistant will give you a simple menu for onboarding, recording transactions, researching investments, and producing reports.

### Get started or onboard a portfolio

For a new setup, describe the goal:

> "Help me get started."
> "Onboard me."
> "Please onboard me with this statement."
> "Import this broker file and set up my portfolio."

You can attach a brokerage statement, spreadsheet, PDF, screenshot, or pasted transaction history. The assistant will help create the account, understand your investing style, prepare your records, and verify that the setup is usable.

### Set or review your investing style

Tell the assistant how you invest so future research sounds and acts like you:

> "Walk me through my settings."
> "Review my strategy."
> "Update my risk tolerance."
> "Change my base currency to TWD."
> "Use Traditional Chinese for my reports."
> "These sectors are off-limits for me."

This can include risk tolerance, position sizing, holding period, entry discipline, preferred language, base currency, and areas you want to avoid.

### Add and manage accounts

Use natural language to manage multiple accounts:

> "Create a new account for my Japan portfolio."
> "Add a retirement account."
> "Show all my accounts."
> "Which account am I using now?"
> "Switch to my default account."
> "Switch to my Taiwan account."
> "Generate a report for my Japan account."
> "Generate a total report across all accounts."

Each account keeps its own settings, transactions, cash, holdings, and reports. A total report combines accounts for a high-level view while keeping the underlying accounts separate.

### Record trades and cash flows

Describe portfolio activity in everyday words:

> "I bought 30 NVDA at $185 yesterday."
> "Sold 10 TSLA at $400 today."
> "Q1 GOOG dividend, $80."
> "Deposited $5,000."
> "Withdrew $1,000 for taxes."
> "I paid a $12 trading fee."
> "I converted USD 2,000 to TWD."

The assistant will parse the activity, show you the proposed record, and wait for your confirmation before updating your portfolio.

### Fix or reconcile records

If something is wrong, describe the correction:

> "Fix the GOOG lot from last September."
> "That NVDA trade should have been 20 shares, not 30."
> "Remove the duplicate dividend entry."
> "Reconcile my cash balance with this statement."
> "Check whether my open lots match my broker export."

The assistant will explain the proposed change before saving it.

### Import broker files

Attach the file and describe what you want:

> "Here is my broker export — please import it."
> "Import this transaction history."
> "Import this PDF statement and show me what you found before saving."
> "This file has dividends and trades; add them to my account."

Import tips:

- If you hold Taiwan-listed stocks, a Taiwan Stock Exchange export is usually the best source when available.
- If a PDF is password-protected, open it yourself and save an unlocked copy before importing.
- If a file is very large, especially a PDF, split it into smaller batches before importing.
- If an import looks ambiguous, the assistant will ask you to confirm the interpretation before saving anything.

### Research a stock, ETF, theme, or market

Ask for direct, portfolio-aware research:

> "Analyze NVDA against my current portfolio."
> "Should I buy TSM now for my strategy?"
> "Compare TSM, NVDA, and AMD."
> "What is my AI exposure now?"
> "Should I trim short-term positions before earnings?"
> "Review my Japan exposure."
> "What should I watch in semiconductors this week?"

Research notes focus on the decision: whether to buy, hold, trim, avoid, or wait; how large the position should be; what would invalidate the view; and what to track next.

### Generate a daily report

Use the daily report when you want a current decision dashboard for today:

> "Produce today’s daily report."
> "Run my pre-market report."
> "Give me today’s portfolio health check."
> "What should I do in the portfolio today?"

The daily report is designed for active review. It can include updated prices, portfolio health, important news, upcoming events, risk alerts, high-opportunity setups, suggested adjustments, and a clear action list for the day.

### Generate a portfolio report

Use the portfolio report when you want a cleaner position review without daily trading noise:

> "Generate my portfolio report."
> "Show me my portfolio allocation and performance."
> "Review my holdings, cash, and concentration."
> "How has the portfolio performed?"

The portfolio report focuses on holdings, cash, allocation, profit and loss, concentration, pacing, and portfolio structure. It is best for reviewing the shape of the book rather than making same-day decisions.

### Generate a total report across accounts

When you have more than one account, ask for a combined view:

> "Generate a total report across all accounts."
> "Show my total portfolio."
> "Combine all accounts and summarize my exposure."

The total report gives a high-level combined view across accounts while avoiding account-specific trading guidance.

### Ask for portfolio risk and exposure checks

You can ask focused portfolio questions without generating a full report:

> "What are my top concentration risks?"
> "How much cash do I have?"
> "Which positions overlap the most?"
> "Am I too exposed to AI semiconductors?"
> "Which holdings are high risk right now?"
> "What upcoming events matter for my portfolio?"

### Ask for an action plan

If you want a short decision list, say:

> "Give me today’s action list."
> "What should I buy, trim, or leave alone?"
> "Which positions need attention first?"
> "Tell me what to monitor this week."

The assistant will prefer no action over forced activity when there is no clear edge.

## Privacy

Your settings, transactions, and generated reports stay local in this workspace. They are not published by this project. You control what files you share with the assistant and what changes are saved.

## Third-party market data

Reports and research may use public market-data and currency sources, plus any data access you choose to provide. Availability, delays, rate limits, and accuracy depend on those providers.

## Disclaimer

For personal research and record-keeping only. Not investment or legal advice. Verify important facts independently before trading; you own the decisions.
