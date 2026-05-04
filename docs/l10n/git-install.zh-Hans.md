# 用 Git 安装：新手指南

**指南语言** · [English](../git-install.md) · [繁體中文](git-install.zh-Hant.md) · [简体中文](git-install.zh-Hans.md) · [日本語](git-install.ja.md) · [Tiếng Việt](git-install.vi.md) · [한국어](git-install.ko.md)

如果你从来没用过 Git，或电脑还没有安装 Git，请看这份指南。建议用 Git 安装这个 repo，因为之后助手才能安全地帮你更新本地版本。

## 你需要准备什么

- 一台可以安装应用程序的电脑。
- 一个本地 coding assistant，例如 Codex、Claude Code，或其他能打开文件夹并编辑文件的助手。
- 这个 repo URL：`https://github.com/lpopo0856/investment-research-agent.git`

你不需要深入理解 Git。你只需要有一份通过 Git 安装的 repo。

## 最简单方式：GitHub Desktop

如果你更想用按钮操作、不想打开终端，这是最适合新手的方式。

1. 从官方下载页安装 GitHub Desktop：<https://desktop.github.com/download/>。
2. 打开 GitHub Desktop。
3. 选择 **Clone a repository from the Internet**。
4. 选择 **URL** 标签页。
5. 粘贴这个 URL：

   ```text
   https://github.com/lpopo0856/investment-research-agent.git
   ```

6. 选择你想存放 repo 的本地文件夹。
7. 点击 **Clone**。
8. 用你的助手打开 clone 出来的 `investment-research-agent` 文件夹。
9. 说：“请把这个 repo 切换到最新的 release tag，然后帮我开始。”

   GitHub Desktop 界面无法直接切换到 release tag，因此由助手代办。助手会自动选最新的 tag，你不需要知道版本号。

之后要更新时，用助手打开同一个文件夹并说：“请帮我安全升级这个 repo。”

## 终端方式：安装 Git 并 clone

如果你可以接受打开 Terminal、PowerShell 或 Command Prompt，可以用这个方式。

1. 从 Git 官方下载页安装 Git：<https://git-scm.com/downloads>。
2. 打开 Terminal、PowerShell 或 Command Prompt。
3. 前往你想存放 repo 的文件夹，例如 Documents 或 Projects。
4. Clone 这个 repo 并切换到最新的 release tag：

   ```bash
   git clone https://github.com/lpopo0856/investment-research-agent.git
   cd investment-research-agent
   git checkout "$(git tag --sort=-v:refname | head -n 1)"
   ```

   最后一行会自动选取最新的 release tag，不需要手动指定版本号。出现 “detached HEAD” 提示是正常的，之后助手的升级流程会帮你安全处理。

5. 用你的助手打开 `investment-research-agent` 文件夹。
6. 说：“帮我开始。”

## 有用链接

- 项目 repo：<https://github.com/lpopo0856/investment-research-agent>
- 报告示例：<https://lpopo0856.github.io/investment-research-agent/>
- Git 官方下载：<https://git-scm.com/downloads>
- GitHub Desktop 下载：<https://desktop.github.com/download/>
- GitHub Desktop 安装文档：<https://docs.github.com/en/desktop/installing-and-authenticating-to-github-desktop/installing-github-desktop>
- GitHub clone 文档：<https://docs.github.com/repositories/creating-and-managing-repositories/cloning-a-repository>
