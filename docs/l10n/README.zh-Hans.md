# 投资研究代理

**README 语言** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

英文版 README 为正式版本，其他语言仅为方便阅读的翻译。

本仓库是 AI 投资研究代理的本地工作区。实际主要做三件事：

1. 根据你的设置与交易记录回答研究问题。
2. 生成每日 HTML 持仓报告。
3. 将自然语言消息、CSV 或 JSON 文件中的新交易（BUY / SELL / DEPOSIT / WITHDRAW / DIVIDEND / FEE / FX_CONVERT）写入本地 SQLite 数据库。

最适合在能读文件并执行命令的代理工具中使用，例如 OpenAI Codex、Claude Code、Gemini CLI 或类似环境。

**模型层级：** 若要分析可靠并遵守本仓库合约（`AGENTS.md`、报表与交易指引），请使用 **Claude Sonnet 4.6** 并开启 **High** 推理强度，或任何同等或更高能力的较新模型层级。较轻量的模型可能略过稽核步骤、误读交易，或削弱研究深度。

## 关键文件

- `AGENTS.md`：研究代理的思考与写作方式。
- `SETTINGS.md`：语言、完整 `Investment Style And Strategy`、基准货币与仓位上限。仅保存在本机。
- `transactions.db`：本地 SQLite，存储每笔交易（买卖、存取款、股息、手续费、换汇）及理由与标签。内含两个派生表（`open_lots`、`cash_balances`），每次 INSERT 后自动重建，作为预估未平仓视图。**驱动已实现损益、未实现损益与损益面板。** 仅保存在本机。见 `docs/transactions_agent_guidelines.md`。
- `docs/portfolio_report_agent_guidelines.md`：报表合约，含完整新闻／事件覆盖、Strategy readout 与 reviewer pass；代理还必须读取 `docs/portfolio_report_agent_guidelines/` 下所有链接分章。
- `docs/transactions_agent_guidelines.md`：唯一交易账本合约——数据库结构、自然语言解析 → 计划 → 确认 → 写入流程、CSV／JSON／消息导入路径、lot 匹配、损益面板、迁移。
- `scripts/fetch_prices.py`：标准最新价与汇率抓取。从 `transactions.db` 读取仓位。
- `scripts/fetch_history.py`：配套的历史收盘与汇率历史抓取（供损益面板使用，将 `_history` / `_fx_history` 写入 prices.json）。从 `transactions.db` 读取仓位。
- `scripts/transactions.py`：SQLite 存储与导入（CSV／JSON／消息）、重放引擎、余额重建、已实现＋未实现损益、1D／7D／MTD／1M／YTD／1Y／ALLTIME 损益面板。
- `scripts/generate_report.py`：标准 HTML 报表渲染；读取 `report_snapshot.json` 与已验证的 `report_context.json`，不再在渲染阶段重算组合数字。
- `reports/`：输出目录。仅保存在本机。

## 首次设置

```sh
cp SETTINGS.example.md SETTINGS.md
python scripts/transactions.py db init        # 创建 transactions.db
```

然后任选其一：

- **从既有 `HOLDINGS.md` 引导**（iteration-2 用户）：

  ```sh
  python scripts/transactions.py migrate --holdings HOLDINGS.md
  python scripts/transactions.py verify
  rm HOLDINGS.md HOLDINGS.md.bak HOLDINGS.example.md
  ```

  `migrate` 会为每个既有 lot 合成一笔 BUY、为每种现金货币合成一笔 DEPOSIT，使重建后余额与你种下的数据一致。verify 通过后即可删除上述 markdown，不再需要。

- **或导入券商对账单**（CSV 或 JSON）：

  ```sh
  python scripts/transactions.py db import-csv --input statements/2026-04-schwab.csv
  python scripts/transactions.py db import-json --input transactions.json
  ```

- **或**通过代理以纯英文逐笔录入交易（例如「昨天 185 美元买了 30 股 NVDA」）。代理解析后会显示计划与正式 JSON，你回复 `yes` 后再执行 `db add`。见 `docs/transactions_agent_guidelines.md` §3。

每次写入后运行 `python scripts/transactions.py verify`，确认物化表 `open_lots` 与 `cash_balances` 与完整 log 重放一致。

`SETTINGS.md`、`transactions.db`、生成的报告与运行时文件（`prices.json`、`report_context.json`、`temp/`）均在 `.gitignore` 中。

### 使用 `SETTINGS.md` 与 `transactions.db`

- 当你的偏好语言、完整投资策略、基准货币、仓位上限或报告默认项变化时，及时更新 `SETTINGS.md`。
- 将 `Investment Style And Strategy` 整段写成你希望代理扮演的投资人：性格、回撤容忍、仓位大小、持有周期、进场纪律、逆势意愿、夸大叙事容忍度、禁区与决策风格。
- 将 `transactions.db` 视为实时仓位与现金的唯一事实来源；新资金流均经由代理或 CSV／JSON 导入，派生视图 `open_lots` + `cash_balances` 会自动更新。
- 每次交易成交后，立即让代理记账，以保证后续分析准确。
- 生成报告前快速检查 `SETTINGS.md`，并运行 `transactions.py db stats` 查看是否有过时数据。

## 常用工作流

大多数情况下，只需让代理做以下三件事之一。

### 1. 研究分析

例子：

- “分析 NVDA 对我当前组合的意义。”
- “我现在 AI 暴露有多高？”
- “财报前要不要减掉短线仓位？”

代理会读取完整的 `SETTINGS.md` 中 `Investment Style And Strategy`、从 `transactions.db`（`open_lots` + `cash_balances`）加载仓位，并按 `AGENTS.md` 以你的策略第一人称输出。

### 2. 持仓报告

例子：

- “生成今天的持仓体检。”
- “帮我跑盘前报告。”

交付物是 `reports/` 下的单个自包含 HTML。

若在 `auto mode`、`routine` 或其他无人看守环境下生成报告，建议代理先取得明确同意，再把持仓代号发送到外部市场数据来源取价。清晰的同意例句可写为：`我同意请把持仓代号送到外部市场资料来源来取得价格并生成今天的报告`。英文可写为：`I agree to let you send my holdings tickers to external market data sources to retrieve prices and generate today's report.`

完整报告流程分为四阶段：先 Gather 收集数据；价格、指标、新闻与事件完成后才 Think 形成判断；渲染前以资深 PM 身份 Review；最后 Render。Gather 阶段要对每个非现金持仓做实时新闻与未来 30 天事件搜索，而不只看最大权重仓位。Review 阶段只添加审稿备注，不改写你的原始判断。

代理应直接使用标准脚本，而不是每次重写流程；会读取交易数据的步骤默认使用根目录 `transactions.db`。

```sh
python scripts/fetch_prices.py --settings SETTINGS.md --output prices.json
# 若任何行仍含 agent_web_search:TODO_required，fetch_prices 会以非零码停止。
# 渲染前必须完成 tier 3 / tier 4 报价备用路径。

python scripts/fetch_history.py \
    --settings SETTINGS.md \
    --merge-into prices.json --output prices_history.json

# 生成单一数字快照；profit panel、realized/unrealized、transaction analytics 都在其中。
python scripts/transactions.py snapshot \
    --prices prices.json --settings SETTINGS.md --output report_snapshot.json

# 代理接着依 snapshot、最新公开资料、SETTINGS 与 guidelines 撰写 report_context.json。
# context 必须包含 theme_sector_audit、research_coverage、trading_psychology、
# Strategy readout、reviewer_pass、actions / adjustments 等 editorial 字段。
python scripts/validate_report_context.py \
    --snapshot report_snapshot.json --context report_context.json

python scripts/generate_report.py \
    --settings SETTINGS.md --snapshot report_snapshot.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

若报告语言不是内建 UI 字典 `english`、`traditional chinese`、`simplified chinese` 之一，执行中的代理应将 `scripts/i18n/report_ui.en.json` 翻成临时 overlay，并通过 `--ui-dict` 传入。

`report_context.json` 必须通过 `validate_report_context.py`；旧的 `style_readout` key 仍会渲染，但新的 context 应使用 `strategy_readout`。

### 3. 交易记账

例子：

- “昨天我在 185 美元买了 30 股 NVDA。”
- “今天 400 美元卖出 10 股 TSLA。”
- “GOOG Q1 股息 80 美元。”
- “入金 5000 美元准备下一轮买进。”
- “这是我的 Schwab CSV，请导入。”

硬规则：代理在展示解析计划、正式 JSON blob，并在同一轮获得明确 `yes` 之前，不得 INSERT `transactions.db`。每次写入前先备份 `transactions.db.bak`，接着自动重建余额，再执行 `verify`。见 `docs/transactions_agent_guidelines.md` §3。

## 报告输出

文件名格式：

```text
reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html
```

HTML 为单文件，不依赖外部 CSS、JS、字体或图表库。

`reports/_sample_redesign.html` 是视觉参考文件，请不要删除。

## 何时修改规范

如果你要改变代理行为，请修改：

- `AGENTS.md`
- `docs/portfolio_report_agent_guidelines.md`
- `docs/portfolio_report_agent_guidelines/` 下所有被链接的分章
- `docs/transactions_agent_guidelines.md`

不要把个人数据放进规范文件。

## 隐私

会被 git 跟踪的内容：

- 代理规范
- 示例模板
- Python 脚本
- README
- 视觉参考文件

不会被 git 跟踪的内容：

- `SETTINGS.md`
- `transactions.db`
- `transactions.db.bak`
- 生成的报告
- 常见运行文件，如 `prices.json`、`prices_history.json`、`report_context.json`、`temp/`

## 第三方数据

本项目不拥有也不保证任何行情或汇率来源。价格流程可能使用公开端点（Stooq JSON、Yahoo v8 chart、Binance、CoinGecko、Frankfurter／ECB、Open ExchangeRate-API、TWSE／TPEx MIS）、可选 API 密钥（Twelve Data、Finnhub、Alpha Vantage、FMP、Tiingo、Polygon、J-Quants、CoinGecko Demo）以及 `yfinance` 等封装。台股无 token 的 MIS fallback 会同时探测上市（`tse_`）与上柜（`otc_`）通道，以降低 `[TW]` / `[TWO]` 分类错误造成的漏价。供应商条款、速率限制、署名和付费授权，均由使用者自行负责。

## 免责声明

本仓库仅供个人研究，不构成投资建议。交易前请自行核实重要信息。
