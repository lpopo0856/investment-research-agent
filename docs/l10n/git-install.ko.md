# Git으로 설치하기: 초보자 안내

**가이드 언어** · [English](../git-install.md) · [繁體中文](git-install.zh-Hant.md) · [简体中文](git-install.zh-Hans.md) · [日本語](git-install.ja.md) · [Tiếng Việt](git-install.vi.md) · [한국어](git-install.ko.md)

Git을 써 본 적이 없거나 컴퓨터에 Git이 아직 설치되어 있지 않다면 이 안내를 사용하세요. 이 repo는 Git으로 설치하는 것을 권장합니다. 그래야 나중에 어시스턴트가 로컬 복사본을 안전하게 업데이트할 수 있습니다.

## 준비할 것

- 앱을 설치할 수 있는 컴퓨터.
- Codex, Claude Code 또는 폴더를 열고 파일을 수정할 수 있는 로컬 coding assistant.
- 이 repo URL: `https://github.com/lpopo0856/investment-research-agent.git`

Git을 깊게 이해할 필요는 없습니다. Git으로 설치된 repo 복사본만 있으면 됩니다.

## 가장 쉬운 방법: GitHub Desktop

터미널 명령보다 버튼으로 진행하고 싶다면 이 방법이 가장 쉽습니다.

1. 공식 다운로드 페이지에서 GitHub Desktop을 설치합니다: <https://desktop.github.com/download/>.
2. GitHub Desktop을 엽니다.
3. **Clone a repository from the Internet**을 선택합니다.
4. **URL** 탭을 선택합니다.
5. 이 URL을 붙여 넣습니다:

   ```text
   https://github.com/lpopo0856/investment-research-agent.git
   ```

6. repo를 저장할 로컬 폴더를 선택합니다.
7. **Clone**을 클릭합니다.
8. clone된 `investment-research-agent` 폴더를 어시스턴트로 엽니다.
9. “이 repo를 최신 release tag로 전환한 뒤 시작을 도와줘.”라고 말합니다.

   GitHub Desktop UI는 release tag로 바로 전환하는 기능이 없으므로 어시스턴트가 대신 처리합니다. 최신 tag는 자동으로 선택되므로 버전 번호를 알 필요는 없습니다.

나중에 업데이트하려면 같은 폴더를 어시스턴트로 열고 “이 repo를 안전하게 업그레이드해줘.”라고 말하세요.

## 터미널 방법: Git 설치 후 clone

Terminal, PowerShell 또는 Command Prompt를 열 수 있다면 이 방법도 사용할 수 있습니다.

1. Git 공식 다운로드 페이지에서 Git을 설치합니다: <https://git-scm.com/downloads>.
2. Terminal, PowerShell 또는 Command Prompt를 엽니다.
3. Documents 또는 Projects처럼 repo를 보관할 폴더로 이동합니다.
4. repo를 clone하고 최신 release tag로 전환합니다:

   ```bash
   git clone https://github.com/lpopo0856/investment-research-agent.git
   cd investment-research-agent
   git checkout "$(git tag --sort=-v:refname | head -n 1)"
   ```

   마지막 명령은 최신 release tag를 자동으로 가져오므로 버전 번호를 직접 지정할 필요가 없습니다. “detached HEAD” 메시지는 정상이며, 이후 업데이트는 어시스턴트의 업그레이드 흐름이 안전하게 처리합니다.

5. `investment-research-agent` 폴더를 어시스턴트로 엽니다.
6. “시작을 도와줘.”라고 말합니다.

## 유용한 링크

- 프로젝트 repo: <https://github.com/lpopo0856/investment-research-agent>
- 리포트 demo: <https://lpopo0856.github.io/investment-research-agent/>
- Git 공식 다운로드: <https://git-scm.com/downloads>
- GitHub Desktop 다운로드: <https://desktop.github.com/download/>
- GitHub Desktop 설치 문서: <https://docs.github.com/en/desktop/installing-and-authenticating-to-github-desktop/installing-github-desktop>
- GitHub clone 문서: <https://docs.github.com/repositories/creating-and-managing-repositories/cloning-a-repository>
