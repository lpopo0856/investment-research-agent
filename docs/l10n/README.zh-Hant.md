# 投資研究代理

**README 語言** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

英文版 README 為正式版本，其他語言為方便閱讀之翻譯。

本倉庫是 AI 投資研究代理的本機工作區。實際上主要做三件事：

1. 依你的設定與交易紀錄回答研究問題。
2. 產出每日 HTML 持倉報表。
3. 將自然語言訊息、CSV 或 JSON 檔中的新交易（BUY / SELL / DEPOSIT / WITHDRAW / DIVIDEND / FEE / FX_CONVERT）寫入本機 SQLite 資料庫。

最適合在可讀檔並可執行指令的代理工具中使用，例如 OpenAI Codex、Claude Code、Gemini CLI 或類似環境。

**模型層級：** 若要分析可靠並遵守本倉庫合約（`AGENTS.md`、報表與交易指引），請使用 **Claude Sonnet 4.6** 並開啟 **High** 推理強度，或任何同等或更高能力的較新模型層級。較輕量的模型可能略過檢核步驟、誤讀交易，或削弱研究深度。

## 重要檔案

- `AGENTS.md`：研究代理的思考與寫作方式。
- `SETTINGS.md`：語言、完整 `Investment Style And Strategy`、基準貨幣與部位上限。僅存本機。
- `transactions.db`：本機 SQLite，儲存每筆交易（買賣、存提款、股息、手續費、換匯）及理由與標籤。內含兩個衍生表（`open_lots`、`cash_balances`），每次 INSERT 後自動重建，作為預估未平倉視圖。**驅動已實現損益、未實現損益與損益面板。** 僅存本機。見 `docs/transactions_agent_guidelines.md`。
- `docs/portfolio_report_agent_guidelines.md`：報表合約，含完整新聞／事件覆蓋、Strategy readout 與 reviewer pass；代理也必須讀取 `docs/portfolio_report_agent_guidelines/` 下所有連結分章。
- `docs/transactions_agent_guidelines.md`：唯一交易帳本合約——資料庫結構、自然語言解析 → 計畫 → 確認 → 寫入流程、CSV／JSON／訊息匯入路徑、lot 配對、損益面板、遷移。
- `scripts/fetch_prices.py`：標準最新價與匯率抓取。從 `transactions.db` 讀取部位。
- `scripts/fetch_history.py`：搭配用的歷史收盤與匯率歷史抓取（供損益面板使用，將 `_history` / `_fx_history` 寫入 prices.json）。從 `transactions.db` 讀取部位。
- `scripts/transactions.py`：SQLite 儲存與匯入（CSV／JSON／訊息）、重播引擎、餘額重建、已實現＋未實現損益、1D／7D／MTD／1M／YTD／1Y／ALLTIME 損益面板。
- `scripts/generate_report.py`：標準 HTML 報表渲染；讀取 `report_snapshot.json` 與已驗證的 `report_context.json`，不再於渲染階段重算投組數字。
- `reports/`：產出目錄。僅存本機。

## 首次設定

```sh
cp SETTINGS.example.md SETTINGS.md
python scripts/transactions.py db init        # 建立 transactions.db
```

接著擇一：

- **從既有 `HOLDINGS.md` 啟動**（iteration-2 使用者）：

  ```sh
  python scripts/transactions.py migrate --holdings HOLDINGS.md
  python scripts/transactions.py verify
  rm HOLDINGS.md HOLDINGS.md.bak HOLDINGS.example.md
  ```

  `migrate` 會為每個既有 lot 合成一筆 BUY、為每種現金貨幣合成一筆 DEPOSIT，使重建後餘額與你種下的資料一致。verify 通過後即可刪除上述 markdown，不再需要。

- **或匯入券商對帳單**（CSV 或 JSON）：

  ```sh
  python scripts/transactions.py db import-csv --input statements/2026-04-schwab.csv
  python scripts/transactions.py db import-json --input transactions.json
  ```

- **或**透過代理以純英文逐筆餵入交易（例如「昨天 185 美元買了 30 股 NVDA」）。代理解析後會顯示計畫與正式 JSON，你回覆 `yes` 後再執行 `db add`。見 `docs/transactions_agent_guidelines.md` §3。

每次寫入後執行 `python scripts/transactions.py verify`，確認物化表 `open_lots` 與 `cash_balances` 與完整 log 重播一致。

`SETTINGS.md`、`transactions.db`、產生的報表與執行期檔案（`prices.json`、`report_context.json`、`temp/`）皆在 `.gitignore`。

### 使用 `SETTINGS.md` 與 `transactions.db`

- 偏好語言、完整投資策略、基準貨幣、部位上限或報表預設變更時，請更新 `SETTINGS.md`。
- 將 `Investment Style And Strategy` 整段寫成你希望代理扮演的投資人：性格、回撤容忍、部位大小、持有期間、進場紀律、逆勢意願、誇大敘事容忍度、禁區與決策風格。
- 將 `transactions.db` 視為即時部位與現金的唯一事實來源；新金流皆經由代理或 CSV／JSON 匯入，衍生視圖 `open_lots` + `cash_balances` 會自動更新。
- 每次交易完成後，立即請代理記帳，分析才會準確。
- 產生報表前快速檢視 `SETTINGS.md`，並執行 `transactions.py db stats` 檢查是否有過時資料。

## 常用工作流

大多數情況，只要叫代理做以下三件事之一。

### 1. 研究分析

例子：

- 「分析 NVDA 對我目前投組的意義。」
- 「我現在 AI 曝險有多高？」
- 「財報前要不要減碼短線部位？」

代理會讀完整的 `SETTINGS.md` 中 `Investment Style And Strategy`、從 `transactions.db`（`open_lots` + `cash_balances`）載入部位，並依 `AGENTS.md` 以你的策略第一人稱輸出。

### 2. 持倉報表

例子：

- 「產出今天的持倉健檢。」
- 「幫我跑盤前報表。」

交付物是 `reports/` 下的單一自含 HTML。

若在 `auto mode`、`routine` 或其他無人看守環境下生成報表，建議代理先取得明確同意，再把持倉代號送到外部市場資料來源取價。清楚的同意例句可寫成：`我同意請把持倉代號送到外部市場資料來源來取得價格並生成今天的報表`。英文可寫為：`I agree to let you send my holdings tickers to external market data sources to retrieve prices and generate today's report.`

完整報表流程分成四階段：先 Gather 蒐集資料；價格、指標、新聞與事件完成後才 Think 形成判斷；渲染前以資深 PM 身分 Review；最後 Render。Gather 階段要對每個非現金持倉做即時新聞與未來 30 天事件搜尋，不只看最大權重部位。Review 階段只加上審稿備註，不改寫你的原始判斷。

代理應直接使用標準腳本，而不是每次重寫流程；會讀取交易資料的步驟預設使用根目錄 `transactions.db`。

```sh
python scripts/fetch_prices.py --settings SETTINGS.md --output prices.json
# 若任何列仍含 agent_web_search:TODO_required，fetch_prices 會以非零碼停止。
# 渲染前必須完成 tier 3 / tier 4 報價備援。

python scripts/fetch_history.py \
    --settings SETTINGS.md \
    --merge-into prices.json --output prices_history.json

# 產生單一數字快照；profit panel、realized/unrealized、transaction analytics 都在其中。
python scripts/transactions.py snapshot \
    --prices prices.json --settings SETTINGS.md --output report_snapshot.json

# 代理接著依 snapshot、最新公開資料、SETTINGS 與 guidelines 撰寫 report_context.json。
# context 必須包含 theme_sector_audit、research_coverage、trading_psychology、
# Strategy readout、reviewer_pass、actions / adjustments 等 editorial 欄位。
python scripts/validate_report_context.py \
    --snapshot report_snapshot.json --context report_context.json

python scripts/generate_report.py \
    --settings SETTINGS.md --snapshot report_snapshot.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

若報表語言不是內建 UI 字典 `english`、`traditional chinese`、`simplified chinese` 之一，執行中的代理應把 `scripts/i18n/report_ui.en.json` 翻成暫存 overlay，並用 `--ui-dict` 傳入。

`report_context.json` 必須通過 `validate_report_context.py`；舊的 `style_readout` key 仍會渲染，但新的 context 應使用 `strategy_readout`。

### 3. 交易記帳

例子：

- 「昨天我用 185 美元買了 30 股 NVDA。」
- 「今天 400 美元賣出 10 股 TSLA。」
- 「GOOG Q1 股息 80 美元。」
- 「入金 5,000 美元準備下一輪買進。」
- 「這是我的 Schwab CSV，請匯入。」

硬性規則：代理在顯示解析計畫、正式 JSON blob，並於同一輪取得明確 `yes` 之前，不得 INSERT `transactions.db`。每次寫入前先備份 `transactions.db.bak`，接著自動重建餘額，再執行 `verify`。見 `docs/transactions_agent_guidelines.md` §3。

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
- `docs/transactions_agent_guidelines.md`

不要把個人資料放進規格檔。

## 隱私

會被 git 追蹤的內容：

- 代理規格
- 範例範本
- Python 腳本
- README
- 視覺參考檔

不會被 git 追蹤的內容：

- `SETTINGS.md`
- `transactions.db`
- `transactions.db.bak`
- 產生的報表
- 常見執行檔，如 `prices.json`、`prices_history.json`、`report_context.json`、`temp/`

## 第三方資料

本專案不擁有也不保證任何行情或匯率來源。價格流程可能使用公開端點（Stooq JSON、Yahoo v8 chart、Binance、CoinGecko、Frankfurter／ECB、Open ExchangeRate-API、TWSE／TPEx MIS）、選用 API 金鑰（Twelve Data、Finnhub、Alpha Vantage、FMP、Tiingo、Polygon、J-Quants、CoinGecko Demo）以及 `yfinance` 等封裝。台股無 token 的 MIS fallback 會同時探測上市（`tse_`）與上櫃（`otc_`）通道，以降低 `[TW]` / `[TWO]` 分類錯誤造成的漏價。供應商條款、速率限制、署名與付費授權，均由使用者自行負責。

## 免責聲明

本倉庫僅供個人研究，非投資建議。交易前請自行驗證重要資訊。
