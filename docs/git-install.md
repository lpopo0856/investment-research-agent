# Install with Git: beginner guide

**Guide languages** · [English](git-install.md) · [繁體中文](l10n/git-install.zh-Hant.md) · [简体中文](l10n/git-install.zh-Hans.md) · [日本語](l10n/git-install.ja.md) · [Tiếng Việt](l10n/git-install.vi.md) · [한국어](l10n/git-install.ko.md)

Use this guide if you have never used Git before, or if Git is not installed on your computer yet. Git is the recommended way to install this repo because it lets the assistant update your local copy safely later.

## What you need

- A computer where you can install apps.
- A local coding assistant such as Codex, Claude Code, or another assistant that can open a folder and edit files.
- This repo URL: `https://github.com/lpopo0856/investment-research-agent.git`

You do **not** need to understand Git deeply. You only need a Git-installed copy of the repo.

## Easiest path: GitHub Desktop

This is the most beginner-friendly path if you prefer buttons over terminal commands.

1. Install GitHub Desktop from the official download page: <https://desktop.github.com/download/>.
2. Open GitHub Desktop.
3. Choose **Clone a repository from the Internet**.
4. Select the **URL** tab.
5. Paste this URL:

   ```text
   https://github.com/lpopo0856/investment-research-agent.git
   ```

6. Choose a local folder where you want the repo to live.
7. Click **Clone**.
8. Open the cloned `investment-research-agent` folder with your assistant.
9. Say: “Switch this repo to the latest release tag, then help me get started.”

   GitHub Desktop’s UI does not switch to release tags directly, so the assistant handles it for you. It picks the newest tag automatically — you do not need to know the version number.

For future updates, open the same folder with your assistant and say: “Help me upgrade this repo safely.”

## Terminal path: install Git and clone

Use this path if you are comfortable opening Terminal, PowerShell, or Command Prompt.

1. Install Git from the official Git downloads page: <https://git-scm.com/downloads>.
2. Open Terminal, PowerShell, or Command Prompt.
3. Go to the folder where you want to keep the repo, such as Documents or Projects.
4. Clone the repo and switch to the latest release tag:

   ```bash
   git clone https://github.com/lpopo0856/investment-research-agent.git
   cd investment-research-agent
   git checkout "$(git tag --sort=-v:refname | head -n 1)"
   ```

   The last command moves you to the newest published release instead of the in-progress `main` branch. A “detached HEAD” notice is normal — the assistant’s upgrade flow will handle future updates safely.

5. Open the `investment-research-agent` folder with your assistant.
6. Say: “Help me get started.”

## If you already downloaded the ZIP

A ZIP download is fine for a quick demo, but it is a standalone copy. It has no Git history, so the assistant cannot safely align branches or release tags for automatic upgrades.

For long-term use:

1. Keep your ZIP copy until you are sure any private portfolio files are safe.
2. Install the repo again using Git or GitHub Desktop.
3. If the ZIP copy already contains real portfolio data, do **not** delete it. Open it with your assistant and ask: “Help me move this ZIP install to a Git install safely.”

## Useful links

- Project repository: <https://github.com/lpopo0856/investment-research-agent>
- Report demo: <https://lpopo0856.github.io/investment-research-agent/>
- Git official downloads: <https://git-scm.com/downloads>
- GitHub Desktop download: <https://desktop.github.com/download/>
- GitHub Desktop install docs: <https://docs.github.com/en/desktop/installing-and-authenticating-to-github-desktop/installing-github-desktop>
- GitHub clone docs: <https://docs.github.com/repositories/creating-and-managing-repositories/cloning-a-repository>
