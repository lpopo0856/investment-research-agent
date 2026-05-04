# 用 Git 安裝：新手指南

**指南語言** · [English](../git-install.md) · [繁體中文](git-install.zh-Hant.md) · [简体中文](git-install.zh-Hans.md) · [日本語](git-install.ja.md) · [Tiếng Việt](git-install.vi.md) · [한국어](git-install.ko.md)

如果你從來沒用過 Git，或電腦還沒有安裝 Git，請看這份指南。建議用 Git 安裝這個 repo，因為之後助理才能安全地幫你更新本機版本。

## 你需要準備什麼

- 一台可以安裝應用程式的電腦。
- 一個本機 coding assistant，例如 Codex、Claude Code，或其他能開啟資料夾並編輯檔案的助理。
- 這個 repo URL：`https://github.com/lpopo0856/investment-research-agent.git`

你不需要深入理解 Git。你只需要有一份透過 Git 安裝的 repo。

## 最簡單方式：GitHub Desktop

如果你比較想用按鈕操作、不想開終端機，這是最適合新手的方式。

1. 從官方下載頁安裝 GitHub Desktop：<https://desktop.github.com/download/>。
2. 開啟 GitHub Desktop。
3. 選擇 **Clone a repository from the Internet**。
4. 選擇 **URL** 分頁。
5. 貼上這個 URL：

   ```text
   https://github.com/lpopo0856/investment-research-agent.git
   ```

6. 選擇你想存放 repo 的本機資料夾。
7. 點擊 **Clone**。
8. 用你的助理開啟 clone 出來的 `investment-research-agent` 資料夾。
9. 說：「請把這個 repo 切換到最新的 release tag，然後幫我開始。」

   GitHub Desktop 的介面沒有直接切換 release tag 的功能，所以由助理代勞。助理會自動選擇最新的 tag，你不需要知道版本號碼。

之後要更新時，用助理開啟同一個資料夾並說：「請幫我安全升級這個 repo。」

## 終端機方式：安裝 Git 並 clone

如果你可以接受開啟 Terminal、PowerShell 或 Command Prompt，可以用這個方式。

1. 從 Git 官方下載頁安裝 Git：<https://git-scm.com/downloads>。
2. 開啟 Terminal、PowerShell 或 Command Prompt。
3. 前往你想存放 repo 的資料夾，例如 Documents 或 Projects。
4. Clone 這個 repo 並切換到最新的 release tag：

   ```bash
   git clone https://github.com/lpopo0856/investment-research-agent.git
   cd investment-research-agent
   git checkout "$(git tag --sort=-v:refname | head -n 1)"
   ```

   最後一行會自動抓取最新的 release tag，不需要手動指定版本號碼。出現「detached HEAD」訊息是正常的，後續助理升級流程會幫你安全處理。

5. 用你的助理開啟 `investment-research-agent` 資料夾。
6. 說：「幫我開始。」

## 有用連結

- 專案 repo：<https://github.com/lpopo0856/investment-research-agent>
- 報表範例：<https://lpopo0856.github.io/investment-research-agent/>
- Git 官方下載：<https://git-scm.com/downloads>
- GitHub Desktop 下載：<https://desktop.github.com/download/>
- GitHub Desktop 安裝文件：<https://docs.github.com/en/desktop/installing-and-authenticating-to-github-desktop/installing-github-desktop>
- GitHub clone 文件：<https://docs.github.com/repositories/creating-and-managing-repositories/cloning-a-repository>
