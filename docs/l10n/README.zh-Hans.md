# 投资 — 个人研究与持仓报告

**README 语言** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

**英文**[根目录 README](../../README.md) 为权威、与仓库同步更新的项目说明。其他语言仅便于阅读；如有冲突，以英文为准。

本仓库是 AI 投资研究代理的个人工作区，包含：

1. 代理说明（应如何思考与输出）。
2. 个人数据（持仓、设置）— 不纳入 git。
3. 在 `reports/` 下生成的 HTML 报告 — 也不纳入 git。
4. 持仓报告的 HTML 设计参考样例。
5. `scripts/` 下的两个 Python 模板，代理每轮直接执行，不必每次重写抓价与渲染 HTML 的逻辑。

代理在 LLM 客户端内运行（如 Cowork / Claude）。当你要求「做持仓健康检查」时，它会读说明与个人数据、运行 `scripts/fetch_prices.py` 通过市场对应来源获取最新价格并自动抓取 FX 转换汇率（按规范限速与回退），再运行 `scripts/generate_report.py` 在 `reports/` 中组装可独立打开的 HTML。

## 仓库结构

```
.
├── README.md
├── docs/
│   ├── l10n/
│   ├── portfolio_report_agent_guidelines.md
│   ├── portfolio_report_agent_guidelines/
│   └── holdings_update_agent_guidelines.md
├── AGENTS.md
├── SETTINGS.md
├── SETTINGS.example.md
├── HOLDINGS.md
├── HOLDINGS.md.bak
├── HOLDINGS.example.md
├── scripts/
│   ├── fetch_prices.py
│   ├── generate_report.py
│   └── i18n/
│       ├── report_ui.en.json
│       ├── report_ui.zh-Hant.json
│       └── report_ui.zh-Hans.json
├── .gitignore
└── reports/
    ├── _sample_redesign.html
    └── *_portfolio_report.html
```

## 首次设置

1. 复制示例并填入真实数据：

   ```sh
   cp SETTINGS.example.md SETTINGS.md
   cp HOLDINGS.example.md HOLDINGS.md
   ```

2. 编辑 `SETTINGS.md`：
   - 选择首选语言。
   - 按真实风险承受能力调整投资风格条目。
   -（可选）微调持仓代理用于提醒的规模边界。

3. 编辑 `HOLDINGS.md`：
   - 将每一行换为实际持仓。
   - 保持四桶结构（`Long Term`、`Mid Term`、`Short Term`、`Cash Holdings`）。
   - 每笔一行：`<TICKER>: 数量 股/单位 @ 成本 于 <YYYY-MM-DD> [<市场>]` — `于 YYYY-MM-DD` 为建仓日（供持仓期分析），`[<MARKET>]` 供价格代理构造 `yfinance` 代码与回退链。
   - 常见市场标签：`[US]`、`[TW]`、`[TWO]`、`[JP]`、`[HK]`、`[LSE]`、`[crypto]`、`[FX]`、`[cash]`。完整表见 `HOLDINGS.example.md` 与 `docs/portfolio_report_agent_guidelines.md` §4.1。
   - 成本或日期不明时用 `?` — 受影响项显示 `n/a`（不适用用 `—`，如现金已兑现盈亏），不杜撰。

`HOLDINGS.md`、`HOLDINGS.md.bak`、`SETTINGS.md` 在 `.gitignore` 中，不会通过 git 离开本机。

## 使用代理

**模型建议：**为获得较好的分析与报告质量，请使用**至少 Claude Sonnet 4.6（High）或同等及以上推理能力的模型**。长持仓表、规格核对与综合段落需要足够推理深度——较轻的模型可能省略步骤或漏检。

**运行环境：**在能读文件并执行命令的编码代理里打开本文件夹即可，例如 **Claude Code**、**OpenAI Codex**（CLI 或 IDE）、**Google Gemini**（CLI 或其他客户端）等类似工具。没有唯一指定产品；只要能对本仓库应用 `AGENTS.md` 与 `docs/` 下说明即可。

主要有三类用法：

### 1. 研究类问题（随时）

代理读 `SETTINGS.md` 和 `HOLDINGS.md`，按 `AGENTS.md` 的研究结构输出（先结论、基本面、估值、技术、风险、剧本、评分、总评）。

### 2. 持仓健康检查

代理依 `docs/portfolio_report_agent_guidelines.md`（及其索引所链接的分章文件）在 `reports/` 生成自洽 HTML。共 11 节：今日摘要、组合仪表盘（KPI）、含 P/L 与每笔浮层的持仓表、持仓期与节奏、主题/行业暴露、重要新闻、未来 30 日事件历、高风与高机会清单、建议调整、今日行动清单、来源与数据缺口。有高危警报时，在 11 节上方显示横幅。

实现上，代理直接执行两个 Python 模板，而非每次重写：

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

`report_context.json` 是代理的编辑层：判读、新闻、建议与行动列表；不得放手动 FX 汇率。FX 转换数据由 `scripts/fetch_prices.py` 自动写入 `prices.json["_fx"]`；数字由脚本计算。

若 `SETTINGS.md` 所需语言不在内置 UI 字典（内置：`english`、`traditional chinese`、`simplified chinese`），**执行中的代理**应将 `scripts/i18n/report_ui.en.json` 译为临时 JSON overlay，并通过 `--ui-dict`（或 context 中的 `ui_dictionary`）传给 `scripts/generate_report.py`。渲染器本身不调用外部翻译服务。

### 3. 用自然语言更新持仓

描述交易即可。规则见 `docs/holdings_update_agent_guidelines.md`：不静默覆盖、不杜撰；需你显式 `yes` 后写入，并先备份为 `HOLDINGS.md.bak`。

## 生成的报告

模式：`reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html` — 单文件、无外链资源。`scripts/generate_report.py` 从 `scripts/i18n/report_ui.en.json`、`report_ui.zh-Hant.json`、`report_ui.zh-Hans.json` 加载内置 UI 字典；其他单一语言时由执行代理从英文字典译成 overlay 传入（见上文 `--ui-dict`）。`reports/_sample_redesign.html` 为设计基准，勿删；代理与 `generate_report.py` 从其读取 CSS（默认 `--sample` 即该路径）。

## 修改说明文档

`AGENTS.md`、`docs/portfolio_report_agent_guidelines.md`（及 `docs/portfolio_report_agent_guidelines/` 下索引链接的分章文件）、`docs/holdings_update_agent_guidelines.md` 约束每次运行。要改行为就改文档；不要放入个人数据。大改后建议重跑一份报告验证。

## 隐私

持仓、设置、生成报告以及常见运行产物 `prices.json`、`report_context.json` git-ignored；可分享的是模板与说明。若 fork 仓库，真实数据仍只在本机。

## 第三方数据、API 与速率限制

**本项目并不拥有、运营或担保**任何行情或外汇 API。`scripts/fetch_prices.py` 等流程可能使用公开端点、你在 `SETTINGS.md` 配置的选用 API 密钥，以及封装第三方来源的库（如 `yfinance`）。**你必须遵守**各供应商的**服务条款**、**可接受使用政策**与**速率限制**。过度或违规请求可能导致密钥或 IP 被限流或停用。规格内含节流与回退，但**合规、合法使用由你负责**。若来源要求署名、合约或付费，请遵循该供应商规则。

## 免责

本仓库与报告仅供个人研究，不构成投资建议或买卖邀约；请自行核实后再做交易决策。代理会提示缺口与不确定性，仍可能出错。
