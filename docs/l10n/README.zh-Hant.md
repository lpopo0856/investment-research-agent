# Investments — AI 投資研究工作區

**README 語言** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

英文版 README 為正式版本，其他語言為方便閱讀之翻譯。

這個倉庫是 AI 投資研究代理的本機工作區。實際上主要做三件事：

1. 依你的設定與持倉回答研究問題。
2. 產出每日 HTML 持倉報表。
3. 根據自然語言交易指令更新 `HOLDINGS.md`。

最適合在可讀檔並可執行指令的代理工具中使用，例如 OpenAI Codex、Claude Code、Gemini CLI 或類似環境。

**模型建議：** 若要分析品質穩定，並能遵守本倉庫規格（`AGENTS.md`、報表與持倉指引），請至少使用 **Claude Sonnet 4.6** 並開啟 **High** 推理強度，或任何同等或更高能力的較新模型。較輕量的模型可能略過檢核步驟、誤讀持倉，或削弱研究深度。

## 重要檔案

- `AGENTS.md`：研究代理的思考與寫作規格。
- `SETTINGS.md`：語言、風險風格、基準貨幣。僅存本機。
- `HOLDINGS.md`：你的持倉。僅存本機。
- `docs/portfolio_report_agent_guidelines.md`：報表主規格；代理也必須讀取 `docs/portfolio_report_agent_guidelines/` 下所有連結分章。
- `docs/holdings_update_agent_guidelines.md`：持倉更新規格。
- `scripts/fetch_prices.py`：標準價格與匯率抓取腳本。
- `scripts/generate_report.py`：標準 HTML 報表渲染腳本。
- `reports/`：產出目錄。僅存本機。

## 首次設定

```sh
cp SETTINGS.example.md SETTINGS.md
cp HOLDINGS.example.md HOLDINGS.md
```

接著：

- 填寫 `SETTINGS.md`。
- 填寫 `HOLDINGS.md`。
- `HOLDINGS.md` 保留四個桶：`Long Term`、`Mid Term`、`Short Term`、`Cash Holdings`。
- 每筆 lot 一行：`<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]`。
- 若成本或日期不明，用 `?`。

常用市場標籤：`[US]`、`[TW]`、`[TWO]`、`[JP]`、`[HK]`、`[LSE]`、`[crypto]`、`[FX]`、`[cash]`。

`SETTINGS.md`、`HOLDINGS.md`、`HOLDINGS.md.bak`、產生的報表與常見執行產物皆在 `.gitignore`。

## 常用工作流

大多數情況，只要叫代理做以下三件事之一。

### 1. 研究分析

例子：

- 「分析 NVDA 對我目前投組的意義。」
- 「我現在 AI 曝險有多高？」
- 「財報前要不要減碼短線部位？」

代理會讀 `SETTINGS.md`、`HOLDINGS.md`，並依 `AGENTS.md` 輸出。

### 2. 持倉報表

例子：

- 「產出今天的持倉健檢。」
- 「幫我跑盤前報表。」

交付物是 `reports/` 下的單一自含 HTML。

代理應直接使用標準腳本，而不是每次重寫流程：

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

若報表語言不是內建 UI 字典 `english`、`traditional chinese`、`simplified chinese` 之一，執行中的代理應把 `scripts/i18n/report_ui.en.json` 翻成暫存 overlay，並用 `--ui-dict` 傳入。

### 3. 自然語言更新持倉

例子：

- 「昨天我用 185 美元買了 30 股 NVDA。」
- 「今天 400 美元賣出 10 股 TSLA。」
- 「把去年九月那筆 GOOG 改成 70 股，不是 75 股。」

硬性規則：代理在顯示解析結果與 unified diff、並取得你同一輪明確 `yes` 之前，不得寫入 `HOLDINGS.md`。每次寫入前都必須先建立 `HOLDINGS.md.bak`。

## 報表輸出

檔名格式：

```text
reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html
```

HTML 為單一檔案，不依賴外部 CSS、JS、字型或圖表函式庫。

`reports/_sample_redesign.html` 是視覺參考檔，請勿刪除。

## 何時修改規格

若你要改變代理行為，請修改：

- `AGENTS.md`
- `docs/portfolio_report_agent_guidelines.md`
- `docs/portfolio_report_agent_guidelines/` 下所有被連結的分章
- `docs/holdings_update_agent_guidelines.md`

不要把個人資料放進規格檔。

## 隱私

會被 git 追蹤的內容：

- 代理規格
- 範本檔
- Python 腳本
- README
- 視覺參考檔

不會被 git 追蹤的內容：

- `SETTINGS.md`
- `HOLDINGS.md`
- `HOLDINGS.md.bak`
- 產生的報表
- 常見執行檔，如 `prices.json`、`report_context.json`

## 第三方資料

本專案不擁有也不保證任何行情或匯率來源。價格流程可能使用公開端點、選用 API key 與 `yfinance` 等封裝來源。供應商條款、速率限制、署名與付費授權，均由使用者自行負責。

## 免責聲明

本倉庫僅供個人研究，非投資建議。交易前請自行驗證重要資訊。
