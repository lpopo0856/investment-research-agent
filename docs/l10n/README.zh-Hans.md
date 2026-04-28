# 投资研究代理

**README 语言** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

英文版 README 为正式版本，其他语言仅为方便阅读的翻译。

这个仓库是 AI 投资研究代理的本地工作区。实际主要做三件事：

1. 根据你的设置与持仓回答研究问题。
2. 生成每日 HTML 持仓报告。
3. 按自然语言交易指令更新 `HOLDINGS.md`。

最适合在能读文件并执行命令的代理工具中使用，例如 OpenAI Codex、Claude Code、Gemini CLI 或类似环境。

**模型建议：** 若要分析质量稳定，并能遵守本仓库规格（`AGENTS.md`、报表与持仓指引），请至少使用 **Claude Sonnet 4.6** 并开启 **High** 推理强度，或任何同等或更高能力的较新模型。较轻量的模型可能略过稽核步骤、误读持仓，或削弱研究深度。

## 关键文件

- `AGENTS.md`：研究代理的思考与写作规范。
- `SETTINGS.md`：语言、风险风格、基准货币。仅保存在本机。
- `HOLDINGS.md`：你的持仓。仅保存在本机。
- `docs/portfolio_report_agent_guidelines.md`：报告主规范；代理还必须读取 `docs/portfolio_report_agent_guidelines/` 下所有链接分章。
- `docs/holdings_update_agent_guidelines.md`：持仓更新规范。
- `scripts/fetch_prices.py`：标准价格与汇率抓取脚本。
- `scripts/generate_report.py`：标准 HTML 报告渲染脚本。
- `reports/`：输出目录。仅保存在本机。

## 首次设置

```sh
cp SETTINGS.example.md SETTINGS.md
cp HOLDINGS.example.md HOLDINGS.md
```

然后：

- 填写 `SETTINGS.md`。
- 填写 `HOLDINGS.md`。
- `HOLDINGS.md` 保留四个桶：`Long Term`、`Mid Term`、`Short Term`、`Cash Holdings`。
- 每笔 lot 一行：`<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]`。
- 若成本或日期不明，使用 `?`。

常用市场标签：`[US]`、`[TW]`、`[TWO]`、`[JP]`、`[HK]`、`[LSE]`、`[crypto]`、`[FX]`、`[cash]`。

`SETTINGS.md`、`HOLDINGS.md`、`HOLDINGS.md.bak`、生成报告与常见运行产物都在 `.gitignore` 中。

### `SETTINGS.md` 与 `HOLDINGS.md` 的使用

- 当你的偏好语言、风险风格、基准货币或报告默认项变化时，及时更新 `SETTINGS.md`。
- 在发起研究或报告请求前，将 `HOLDINGS.md` 作为当前持仓的唯一事实来源并保持最新。
- 每次交易成交后，立即让代理更新 `HOLDINGS.md`，以保证后续分析准确。
- 生成报告前快速检查这两个文件，避免沿用过时假设。

## 常用工作流

大多数情况下，只需让代理做以下三件事之一。

### 1. 研究分析

例子：

- “分析 NVDA 对我当前组合的意义。”
- “我现在 AI 暴露有多高？”
- “财报前要不要减掉短线仓位？”

代理会读取 `SETTINGS.md`、`HOLDINGS.md`，并按 `AGENTS.md` 输出。

### 2. 持仓报告

例子：

- “生成今天的持仓体检。”
- “帮我跑盘前报告。”

交付物是 `reports/` 下的单个自包含 HTML。

若在 `auto mode`、`routine` 或其他无人看守环境下生成报告，建议代理先取得明确同意，再把持仓代号发送到外部市场数据来源取价。清晰的同意例句可写为：`我同意请把持仓代号送到外部市场资料来源来取得价格并生成今天的报告`。英文可写为：`I agree to let you send my holdings tickers to external market data sources to retrieve prices and generate today's report.`

代理应直接使用标准脚本，而不是每次重写流程：

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

若报告语言不是内建 UI 字典 `english`、`traditional chinese`、`simplified chinese` 之一，执行中的代理应将 `scripts/i18n/report_ui.en.json` 翻成临时 overlay，并通过 `--ui-dict` 传入。

### 3. 自然语言更新持仓

例子：

- “昨天我在 185 美元买了 30 股 NVDA。”
- “今天 400 美元卖出 10 股 TSLA。”
- “把去年九月那笔 GOOG 改成 70 股，不是 75 股。”

硬规则：代理在展示解析结果与 unified diff，并获得你在同一轮明确 `yes` 之前，不得写入 `HOLDINGS.md`。每次写入前都必须先创建 `HOLDINGS.md.bak`。

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
- `docs/holdings_update_agent_guidelines.md`

不要把个人数据放进规范文件。

## 隐私

会被 git 跟踪的内容：

- 代理规范
- 模板文件
- Python 脚本
- README
- 视觉参考文件

不会被 git 跟踪的内容：

- `SETTINGS.md`
- `HOLDINGS.md`
- `HOLDINGS.md.bak`
- 生成的报告
- 常见运行文件，如 `prices.json`、`report_context.json`

## 第三方数据

本项目不拥有也不保证任何行情或汇率来源。价格流程可能使用公开端点、可选 API key 与 `yfinance` 等封装来源。供应商条款、速率限制、署名和付费授权，均由使用者自行负责。

## 免责声明

本仓库仅供个人研究，不构成投资建议。交易前请自行核实重要信息。
