# 투자 리서치 어시스턴트 (AI 에이전트)

**README 언어** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

영문 README가 유지·관리의 기준이 되는 원본이며, 다른 언어 파일은 읽기 편을 위한 번역입니다.

이 레포는 내 PC에서 도는 **AI 투자 리서치 어시스턴트** 작업 공간입니다. **Claude Code, OpenAI Codex, Gemini CLI** 또는 파일을 읽고 터미널 명령을 실행할 수 있는 에이전트 환경에서 열고, 평소 쓰는 한국어로 요청하면 됩니다.

**모델 권장:** **Claude Sonnet 4.6**에 추론 강도 **High**를 쓰거나, 그에 버금가거나 더 나은 최신 모델을 쓰세요. 더 가벼운 모델은 단계를 건너뛰거나 분석 깊이가 부족해질 수 있습니다.

## Report Demo

**[Report Demo](https://lpopo0856.github.io/investment-research-agent/)**

## 에이전트에게 그대로 말하면 됩니다

명령어나 스키마, 폴더 구조를 미리 외울 필요 없습니다. 하고 싶은 일에 맞는 문장을 골라 붙여 넣으세요.

**처음이에요?**

> "시작하는 거 도와줘." *(또는 증권사 명세·대금내역을 PDF, CSV, JSON, XLSX, 스크린샷, 붙여넣은 텍스트 등 아무 형식으로든 첨부하고 "온보딩 해 줘"라고 하세요)*

스크립트는 활성 계정을 자동으로 사용합니다(명령줄 `--account <name>` 또는 `accounts/.active`로 설정; 기본값은 `accounts/default/`).

**여기서 뭘 할 수 있는지 알고 싶어요**

> "여기서 뭘 할 수 있어?"

**에이전트가 나처럼 판단·기록하도록 맞추기 (위험 성향, 포지션 비중, 손대지 않을 영역, 언어, 기준 통화)**

> "설정 같이 보자."
> "내 SETTINGS 검토해 줘." / "기준 통화를 TWD로 바꿔 줘."

**매매나 현금 흐름 기록**

> "어제 NVDA 30주를 주당 185달러에 샀어."
> "오늘 TSLA 10주를 주당 400달러에 팔았어."
> "GOOG 1분기 배당 80달러."
> "계좌에 5,000달러 입금했어."
> "Schwab에서 받은 CSV야 — 가져와 줘." *(다른 증권사 내보내기 파일도 `docs/` 기준으로 처리)*

**가져오기 팁:** 대만 상장 주식이 있으면 TWSE 내보내기 파일이 있을 때 함께 주세요. PDF에 비밀번호가 있으면 브라우저에서 연 뒤 **인쇄**로 비밀번호 없는 PDF를 저장한 다음 가져오세요. 파일이 매우 크면(특히 PDF) 잘게 나누어 한 번에 한 묶음씩 가져오세요.

**리서치 질문**

> "지금 포트폴리오 기준으로 NVDA 분석해 줘."
> "지금 내 AI 관련 익스포저가 얼마나 돼?"
> "실적 발표 앞두고 단기 포지션 줄일까?"

**오늘 포트폴리오 리포트 만들기**

> "오늘 포트폴리오 점검 리포트 만들어 줘."
> "장 시작 전에 볼 리포트 돌려 줘."

**모든 계정을 합친 종합 리포트 만들기 (수치만):**

> "오늘 종합 리포트 만들어 줘."
> "내 모든 계정을 하나로 합쳐서 포트폴리오 리포트 만들어 줘."

종합 리포트는 각 계정의 포지션과 현금을 합쳐 같은 수학 커널로 돌리지만, 모든 편집형 섹션(뉴스, 이벤트, 경고, 액션 목록, 심리, 테마/섹터…)은 건너뜁니다. 기본 언어는 `en`(내장: `en` / `zh-Hant` / `zh-Hans`), 기본 기준 통화는 `USD`이며 결과는 `accounts/_total/reports/` 아래에 저장됩니다.

저장된 데이터를 바꾸는 작업은 항상 먼저 확인을 거칩니다. 평소 말투로 요청하면 되고, 에이전트가 `docs/` 계약을 따라 처음부터 끝까지 처리합니다.

## 다중 계정

각 계정은 `accounts/<name>/` 아래에 설정·거래 원장·리포트를 갖습니다(예: `accounts/default/SETTINGS.md`, `accounts/default/transactions.db`, `accounts/default/reports/`).

**선택 우선순위**(높은 것부터):
1. 명령줄 `--account <name>` 플래그
2. 포인터 파일 `accounts/.active`(한 줄에 계정 이름)
3. 존재하면 `accounts/default/`

**루트 레이아웃 마이그레이션:** 저장소 루트에 `SETTINGS.md` 또는 `transactions.db`가 있고 `accounts/` 디렉터리가 없으면 스크립트가 레거시 레이아웃을 감지해 `Migrate? [y/N]`을 묻습니다. `y`를 입력하면 파일이 `accounts/default/`로 옮겨지고 `.pre-migrate-backup/`에 백업이 기록된 뒤 명령이 계속됩니다. 신규 사용자에게는 이 프롬프트가 나오지 않으며 온보딩이 바로 `accounts/default/`를 만듭니다.

**계정 범위 밖:** `market_data_cache.db`(공유 시세·환율 캐시)와 `demo/`는 저장소 루트에 두며 `accounts/`로 옮기지 않습니다.

**계정 관리 명령:**
```bash
python scripts/transactions.py account list          # 모든 계정 나열, 활성 표시
python scripts/transactions.py account use <name>    # 활성 계정 전환
python scripts/transactions.py account create <name> # 새 계정 스캐폴드
```

## 개인정보·로컬 보관

설정, 거래 데이터베이스(SQLite), 생성된 모든 리포트는 로컬의 `accounts/<name>/` 아래에 남으며 Git에 추적되지 않습니다. 버전 관리에는 에이전트 스펙, 예시 템플릿, Python 스크립트만 포함됩니다.

## 제3자 데이터

시세 워크플로는 공개 시세·환율 API(Stooq, Yahoo, Binance, CoinGecko, Frankfurter / ECB, Open ExchangeRate-API, TWSE / TPEx 등)와 사용자가 넣은 선택적 API 키를 쓸 수 있습니다. 이 프로젝트는 어떤 제공업체도 운영하거나 보증하지 않으며, 약관·호출 한도·유료 과금은 사용자가 직접 확인하고 책임집니다.

## 면책

개인 연구·기록 목적일 뿐이며 **투자 자문이나 법률 자문이 아닙니다.** 매매 전 중요한 사실은 반드시 스스로 검증하고, 투자 결정과 그 결과는 본인 책임입니다.
