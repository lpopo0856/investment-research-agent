# Git でインストールする：初心者向けガイド

**ガイド言語** · [English](../git-install.md) · [繁體中文](git-install.zh-Hant.md) · [简体中文](git-install.zh-Hans.md) · [日本語](git-install.ja.md) · [Tiếng Việt](git-install.vi.md) · [한국어](git-install.ko.md)

Git を使ったことがない場合、またはまだ Git をインストールしていない場合は、このガイドを使ってください。この repo は Git でインストールすることをおすすめします。あとでアシスタントがローカルコピーを安全に更新できるからです。

## 用意するもの

- アプリをインストールできるコンピューター。
- Codex、Claude Code、またはフォルダを開いてファイルを編集できるローカル coding assistant。
- この repo URL：`https://github.com/lpopo0856/investment-research-agent.git`

Git を深く理解する必要はありません。Git でインストールされた repo があれば十分です。

## いちばん簡単な方法：GitHub Desktop

ターミナルではなくボタン操作で進めたい場合は、この方法がおすすめです。

1. 公式ダウンロードページから GitHub Desktop をインストールします：<https://desktop.github.com/download/>。
2. GitHub Desktop を開きます。
3. **Clone a repository from the Internet** を選びます。
4. **URL** タブを選びます。
5. この URL を貼り付けます：

   ```text
   https://github.com/lpopo0856/investment-research-agent.git
   ```

6. repo を置きたいローカルフォルダを選びます。
7. **Clone** をクリックします。
8. clone された `investment-research-agent` フォルダをアシスタントで開きます。
9. 「この repo を最新の release tag に切り替えて、はじめるのを手伝ってください。」と伝えます。

   GitHub Desktop の UI からは release tag に直接切り替えられないため、アシスタントに任せます。アシスタントは最新の tag を自動で選ぶので、バージョン番号を知っている必要はありません。

今後更新したいときは、同じフォルダをアシスタントで開いて「この repo を安全にアップグレードしてください。」と伝えてください。

## ターミナル方式：Git をインストールして clone する

Terminal、PowerShell、Command Prompt を開くことに抵抗がなければ、この方法も使えます。

1. Git 公式ダウンロードページから Git をインストールします：<https://git-scm.com/downloads>。
2. Terminal、PowerShell、または Command Prompt を開きます。
3. Documents や Projects など、repo を置きたいフォルダへ移動します。
4. repo を clone し、最新の release tag に切り替えます：

   ```bash
   git clone https://github.com/lpopo0856/investment-research-agent.git
   cd investment-research-agent
   git checkout "$(git tag --sort=-v:refname | head -n 1)"
   ```

   最後の行は最新の release tag を自動で取得するので、バージョン番号を手で指定する必要はありません。「detached HEAD」のメッセージは正常です。今後の更新はアシスタントのアップグレードフローが安全に処理します。

5. `investment-research-agent` フォルダをアシスタントで開きます。
6. 「はじめるのを手伝って。」と伝えます。

## 役立つリンク

- プロジェクト repo：<https://github.com/lpopo0856/investment-research-agent>
- レポート例：<https://lpopo0856.github.io/investment-research-agent/>
- Git 公式ダウンロード：<https://git-scm.com/downloads>
- GitHub Desktop ダウンロード：<https://desktop.github.com/download/>
- GitHub Desktop インストール docs：<https://docs.github.com/en/desktop/installing-and-authenticating-to-github-desktop/installing-github-desktop>
- GitHub clone docs：<https://docs.github.com/repositories/creating-and-managing-repositories/cloning-a-repository>
