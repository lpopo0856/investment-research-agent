# 投資研究助理（AI Agent）

**README 語言** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

英文 README 為主要維護版本；其他語言檔為協助閱讀的翻譯。

這個 repo 是在你電腦本機運作的 **AI 投資研究助理**工作區。用 **Claude Code、OpenAI Codex、Gemini CLI**，或任何能讀檔、跑終端機指令的 Agent 環境開啟後，直接用對話下指令即可。

**建議模型：** 使用 **Claude Sonnet 4.6** 並將推理強度設為 **High**，或改用同等或更新的強模型。較輕的模型較容易跳過步驟或拉低分析深度。

## Report Demo

**[Report Demo](https://lpopo0856.github.io/investment-research-agent/)**

## 直接跟助理講就好

不必先背指令、格式或檔案結構。依你想做的事，複製下面任一區塊貼給助理即可。

**第一次用？**

> 「幫我開始。」*（或附上券商對帳單／交割資料——PDF、CSV、JSON、XLSX、截圖、貼上的文字皆可——並說「帶我做 onboarding」）*

腳本會自動使用你的使用中帳戶（透過命令列 `--account <name>` 或 `accounts/.active` 設定；預設為 `accounts/default/`）。

**想知道這裡能幹嘛？**

> 「這裡能做什麼？」

**調整助理怎麼扮演你（風險承受、部位大小、禁區、語言、記帳幣別）：**

> 「帶我過一遍設定。」
> 「看一下我的 SETTINGS。」／「把我的基準貨幣改成 TWD。」

**記一筆買賣或資金進出：**

> 「昨天用 185 美元買了 30 股 NVDA。」
> 「今天用 400 美元賣掉 10 股 TSLA。」
> 「GOOG 第一季配息 80 美元。」
> 「匯入 5,000 美元到帳戶。」／「入金 5,000 美元。」
> 「這是我從 Schwab 匯出的 CSV——請幫我匯入。」（亦適用其他券商匯出格式，依 `docs/` 合約處理）

**匯入小提示：** 持有台股時，若有台灣證券交易所（TWSE）匯出檔，請優先附上。PDF 設有密碼時，請先用瀏覽器開啟，再以瀏覽器的**列印**另存為無密碼的 PDF，再交給助理匯入。交易檔很大時（尤其是 PDF），請拆成較小檔案，分批匯入。

**問研究／部位問題：**

> 「對照我現在的持股分析 NVDA。」
> 「我現在和 AI 相關的曝險有多高？」
> 「財報公布前要不要先調降短線部位？」

**產出今天的投組報表：**

> 「產出今天的投組健檢。」
> 「跑我的盤前報表。」

會改動你已存資料的動作，都會先請你確認。用平常講話的方式說需求即可；助理會依 `docs/` 合約從頭跑到尾並處理細節。

## 多帳戶

每個帳戶各自擁有設定、交易帳本與報表，路徑在 `accounts/<name>/`（例如 `accounts/default/SETTINGS.md`、`accounts/default/transactions.db`、`accounts/default/reports/`）。

**選擇優先順序**（由高到低）：
1. 命令列 `--account <name>`
2. 指標檔 `accounts/.active`（單行帳戶名稱）
3. 若存在則為 `accounts/default/`

**根目錄版式遷移：** 若 repo 根目錄有 `SETTINGS.md` 或 `transactions.db`，且沒有 `accounts/` 目錄，任何腳本會偵測舊版配置並提示 `Migrate? [y/N]`。輸入 `y` 會將檔案移入 `accounts/default/`、備份寫入 `.pre-migrate-backup/`，並繼續執行你的指令。全新使用者不會看到此提示——onboarding 會直接建立 `accounts/default/`。

**不屬帳戶範圍：** `market_data_cache.db`（共用報價／匯率快取）與 `demo/` 留在 repo 根目錄，**不會**移入 `accounts/`。

**帳戶管理指令：**
```bash
python scripts/transactions.py account list          # 列出所有帳戶並標示使用中
python scripts/transactions.py account use <name>    # 切換使用中帳戶
python scripts/transactions.py account create <name> # 建立新帳戶骨架
```

## 隱私

你的設定、交易資料庫（SQLite）與每一份產出的報表都留在本機 `accounts/<name>/` 底下——**不會**被 Git 追蹤。版控裡只有助理規格、範例模板與 Python 腳本。

## 第三方資料

報價流程可能呼叫公開行情與匯率 API（例如 Stooq、Yahoo、Binance、CoinGecko、Frankfurter／歐央行、Open ExchangeRate-API，以及 **台股證交所 TWSE／櫃買 TPEx** 等），外加你自行填入的選用 API 金鑰。本專案不經營也不替任何資料商背書——使用條款、呼叫頻率與付費方案請自行確認並負責。

## 免責聲明

僅供個人研究與紀錄之用，**不是**投資建議或法令上的建議。下單或調整部位前，請自行核實重要資訊並承擔決策責任。
