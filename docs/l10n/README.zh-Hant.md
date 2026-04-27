# 投資專案 — 個人研究與持倉報表

**README 語言** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

以**英文**撰寫的[根目錄 README](../../README.md)為權威、隨倉庫更新之專案說明。其餘語言僅供方便閱讀；如有歧義，以英文為準。

本倉庫是 AI 投資研究代理的個人工作區，內容包含：

1. 代理規格（如何思考與產出）。
2. 個人資料（持倉、設定）— 不納入 git。
3. `reports/` 下產生的 HTML 報表 — 亦不納入 git。
4. 作為持倉報表視覺參考的 HTML 範例。
5. `scripts/` 內的兩個 Python 樣板，代理每回合直接執行，無需每次重寫抓價或產生 HTML 的邏輯。

代理在 LLM 用戶端內執行（如 Cowork / Claude）。當你請它「產出持倉健檢」時，它會讀取規格與個人資料、執行 `scripts/fetch_prices.py` 透過 `yfinance` 取得最新價格（依規格之節流與備援），再執行 `scripts/generate_report.py` 在 `reports/` 組出單一自洽的 HTML。

## 倉庫結構

```
.
├── README.md
├── docs/l10n/                             ← 本檔等：非英文 README
├── AGENTS.md
├── /docs/portfolio_report_agent_guidelines.md
├── /docs/holdings_update_agent_guidelines.md
├── SETTINGS.md
├── SETTINGS.example.md
├── HOLDINGS.md
├── HOLDINGS.md.bak
├── HOLDINGS.example.md
├── /scripts/
│   ├── fetch_prices.py
│   └── generate_report.py
├── .gitignore
└── reports/
    ├── _sample_redesign.html
    └── *_portfolio_report.html
```

## 首次設定

1. 複製範例檔並填入實際資料：

   ```sh
   cp SETTINGS.example.md SETTINGS.md
   cp HOLDINGS.example.md HOLDINGS.md
   ```

2. 編輯 `SETTINGS.md`：
   - 選擇慣用語言。
   - 依實際風險承受度調整投資風格條列。
   - （選填）微調持倉代理用於警告的部位規模界線。

3. 編輯 `HOLDINGS.md`：
   - 各行改為實際部位。
   - 維持四個桶子結構（`Long Term`、`Mid Term`、`Short Term`、`Cash Holdings`）。
   - 每筆一列：`<TICKER>: 數量 股/單位 @ 成本 於 <YYYY-MM-DD> [<市場>]` — `於 YYYY-MM-DD` 為建倉日（用於持倉期分析），`[<MARKET>]` 讓價格代理能組出正確的 `yfinance` 代號與備援順序。
   - 常見市場標籤：`[US]`、`[TW]`、`[TWO]`、`[JP]`、`[HK]`、`[LSE]`、`[crypto]`、`[FX]`、`[cash]`。完整表列見 `HOLDINGS.example.md` 與 `docs/portfolio_report_agent_guidelines.md` §4.1。
   - 成本或日期不確定時用 `?` — 受影響欄位顯示 `n/a`（不適用欄位用 `—`，例如現金已實現損益），不臆測。

`HOLDINGS.md`、`HOLDINGS.md.bak`、`SETTINGS.md` 在 `.gitignore` 內，不會經由 git 離開本機。

## 如何使用代理

在 LLM 用戶端中開啟本資料夾。大致有三類請求：

### 1. 研究問題（隨時）

- 「分析 NVDA 對我目前持倉的意義。」
- 「我現在在 AI 主題上的曝險如何？」
- 「本週財報前是否應先減碼短線部位？」

代理讀 `SETTINGS.md` 把握語氣、讀 `HOLDINGS.md` 看部位，再依 `AGENTS.md` 之研究架構產出（先結論、基本面、估價、技術、風險、劇本、評分、結語）。

### 2. 持倉健檢

- 「產出今天的持倉健檢。」
- 「幫我跑盤前戰情。」

代理依 `/docs/portfolio_report_agent_guidelines.md` 在 `reports/` 產生單一自洽 HTML。共 11 小節（依序）：今日摘要、持倉儀表板（KPI）、含損益與每筆彈層的持倉表、持倉期與建倉節奏、主題／產業曝險、最新重要新聞、未來 30 日事件曆、高風險與高機會清單、建議調整、今日行動清單、資料來源與缺漏。若有高優先警示，會在 11 小節之上顯示橫幅。

實作上，代理執行兩個慣用 Python 樣板，而非每回合從零撰寫：

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

`report_context.json` 是代理的編輯層：今日判讀、網路搜尋到的新聞、建議調整與行動清單。數字（合計、權重、損益、持倉期、節奏分佈、來源查核等）由兩支腳本機械產生。

### 3. 以自然語言更新持倉

直接描述交易。例如：

- 昨日以 $185 買 30 股 NVDA。

代理會：解析交易並覆述假設、顯示 `HOLDINGS.md` 的 unified diff 與桶子合計、（若為賣出）每筆已實現損益、在同一輪內等你的明確 `yes`、先備份至 `HOLDINGS.md.bak` 再寫入、重讀驗證後回覆路徑。不靜默覆寫、不虛構欄位。規剀見 `/docs/holdings_update_agent_guidelines.md`。

## 產生之報表

寫入 `reports/`，檔名：

```
reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html
```

HTML 為單一自含檔（無外連 CSS/JS/字型/圖表庫），可於瀏覽器直接開啟、分享或封存。不再附帶 Markdown 摘要。`reports/_sample_redesign.html` 為慣用視覺參考（去識別示範資料），勿刪；持倉代理與 `scripts/generate_report.py` 自該檔讀取 CSS 作為唯一樣式來源。

## 修改代理規格

`AGENTS.md`、`/docs/portfolio_report_agent_guidelines.md`、`/docs/holdings_update_agent_guidelines.md` 形塑每次執行。作為版本化之「提示合約」：要改行為就改它們；不要放個人資料。重大修改後，請代理重產一則報表以驗證。

## 隱私

- `HOLDINGS.md`、其備份、`SETTINGS.md`、產生之 `*_portfolio_report.html` 皆 git-ignored。
- 追蹤於版本庫的僅有規格、範本、`/scripts/` 內的樣式與本 README 等參考檔。若 fork 或分享，實際部位、備份與報表仍只留在本機。

## 免責聲明

本倉庫與其產出僅供個人研究。非投資建議、非買賣要約，交易前請自行查證。代理會指出資料缺漏與不確定，仍可能出錯 — 行動前請驗證。
