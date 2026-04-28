# 투자 리서치 에이전트

**README 언어** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

영문 README가 공식판이며, 다른 언어는 읽기 편의를 위한 번역입니다.

이 저장소는 AI 투자 리서치 에이전트를 위한 로컬 작업공간입니다. 실제 용도는 주로 세 가지입니다.

1. 설정과 보유 종목을 바탕으로 리서치 질문에 답한다.
2. 매일 HTML 포트폴리오 리포트를 만든다.
3. 자연어 거래 지시를 바탕으로 `HOLDINGS.md`를 업데이트한다.

OpenAI Codex, Claude Code, Gemini CLI처럼 파일을 읽고 명령을 실행할 수 있는 에이전트 환경에서 사용하는 전제를 둡니다.

**모델 권장:** 분석 품질을 안정적으로 유지하고 이 저장소 규격(`AGENTS.md`, 리포트 및 보유 가이드라인)을 따르려면 **Claude Sonnet 4.6**에 **High** 추론 강도를 사용하거나, 그 이상 수준의 최신 모델을 쓰세요. 더 가벼운 모델은 체크리스트를 건너뛰거나 보유를 잘못 읽거나 연구 깊이가 약해질 수 있습니다.

## 핵심 파일

- `AGENTS.md`: 리서치 에이전트의 사고 방식과 문체 규격
- `SETTINGS.md`: 언어, 리스크 스타일, 기준 통화. 로컬 전용
- `HOLDINGS.md`: 보유 종목. 로컬 전용
- `docs/portfolio_report_agent_guidelines.md`: 리포트 메인 규격. `docs/portfolio_report_agent_guidelines/` 아래 링크된 분할 파일도 모두 읽어야 함
- `docs/holdings_update_agent_guidelines.md`: 보유 업데이트 규격
- `scripts/fetch_prices.py`: 표준 가격/환율 수집 스크립트
- `scripts/generate_report.py`: 표준 HTML 렌더러
- `reports/`: 출력 폴더. 로컬 전용

## 최초 설정

```sh
cp SETTINGS.example.md SETTINGS.md
cp HOLDINGS.example.md HOLDINGS.md
```

이후:

- `SETTINGS.md`를 채운다.
- `HOLDINGS.md`를 채운다.
- `HOLDINGS.md`의 네 구획 `Long Term`, `Mid Term`, `Short Term`, `Cash Holdings`를 유지한다.
- 한 로트당 한 줄: `<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]`
- 취득단가나 날짜를 모르면 `?`를 사용한다.

자주 쓰는 시장 태그: `[US]`, `[TW]`, `[TWO]`, `[JP]`, `[HK]`, `[LSE]`, `[crypto]`, `[FX]`, `[cash]`

`SETTINGS.md`, `HOLDINGS.md`, `HOLDINGS.md.bak`, 생성 리포트, 일반 실행 산출물은 `.gitignore` 대상입니다.

### `SETTINGS.md`와 `HOLDINGS.md` 운용

- 선호 언어, 리스크 스타일, 기준 통화, 리포트 기본값이 바뀌면 `SETTINGS.md`를 갱신합니다.
- 리서치나 리포트를 요청하기 전 기준 데이터로 `HOLDINGS.md`를 최신 보유의 단일 소스로 유지합니다.
- 체결이 끝날 때마다 분석 정확도를 위해 즉시 에이전트에 `HOLDINGS.md` 업데이트를 요청합니다.
- 리포트를 생성하기 전에 오래된 가정이 없는지 `SETTINGS.md`와 `HOLDINGS.md`를 빠르게 점검합니다.

## 자주 쓰는 워크플로

보통은 아래 세 가지 중 하나만 에이전트에 요청하면 됩니다.

### 1. 리서치

예시:

- "NVDA를 현재 포트폴리오 기준으로 분석해줘."
- "지금 내 AI 익스포저가 얼마나 돼?"
- "실적 발표 전에 단기 포지션을 줄여야 할까?"

에이전트는 `SETTINGS.md`와 `HOLDINGS.md`를 읽고 `AGENTS.md`에 따라 답합니다.

### 2. 포트폴리오 리포트

예시:

- "오늘 포트폴리오 헬스체크 만들어줘."
- "프리마켓 리포트 돌려줘."

결과물은 `reports/` 아래의 단일 self-contained HTML 파일입니다.

`auto mode`, `routine` 또는 기타 무인 환경에서 리포트를 생성할 때는, 보유 종목 티커를 외부 시장 데이터 소스로 보내 가격을 조회하기 전에 에이전트가 명시적인 동의를 받는 것을 권장합니다. 명확한 동의 문구 예시는 다음과 같습니다: `내 보유 티커를 외부 시장 데이터 소스로 보내 가격을 조회하고 오늘의 리포트를 생성하는 데 동의합니다.` 영어 문구는 다음과 같습니다: `I agree to let you send my holdings tickers to external market data sources to retrieve prices and generate today's report.`

에이전트는 매번 새로 쓰지 말고 표준 스크립트를 사용해야 합니다.

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

요청 언어가 내장 UI 사전 `english`, `traditional chinese`, `simplified chinese` 외라면, 실행 중인 에이전트가 `scripts/i18n/report_ui.en.json`을 임시 overlay로 번역해 `--ui-dict`로 넘깁니다.

### 3. 자연어 보유 업데이트

예시:

- "어제 NVDA를 185달러에 30주 샀어."
- "오늘 TSLA를 400달러에 10주 팔았어."
- "작년 9월 GOOG 로트를 75주가 아니라 70주로 고쳐줘."

강한 규칙: 에이전트는 파싱 결과와 unified diff를 보여주고, 같은 턴에서 명시적 `yes`를 받기 전까지 `HOLDINGS.md`를 쓰면 안 됩니다. 쓰기 전에는 항상 `HOLDINGS.md.bak`를 만들어야 합니다.

## 리포트 출력

파일명 형식:

```text
reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html
```

HTML은 단일 파일이며 외부 CSS, JS, 폰트, 차트 라이브러리에 의존하지 않습니다.

`reports/_sample_redesign.html`은 디자인 기준 파일이므로 삭제하면 안 됩니다.

## 규격을 바꿀 때

에이전트 동작을 바꾸려면 다음을 수정합니다.

- `AGENTS.md`
- `docs/portfolio_report_agent_guidelines.md`
- `docs/portfolio_report_agent_guidelines/` 아래 링크된 모든 분할 파일
- `docs/holdings_update_agent_guidelines.md`

개인 데이터는 규격 파일에 넣지 마세요.

## 프라이버시

git에 추적되는 것:

- 에이전트 규격
- 템플릿
- Python 스크립트
- README
- 디자인 참고 파일

git에 추적되지 않는 것:

- `SETTINGS.md`
- `HOLDINGS.md`
- `HOLDINGS.md.bak`
- 생성 리포트
- `prices.json`, `report_context.json` 같은 실행 산출물

## 서드파티 데이터

이 프로젝트는 시세나 환율 소스를 소유하거나 보장하지 않습니다. 가격 수집 과정은 공개 엔드포인트, 선택적 API 키, `yfinance` 같은 래퍼를 사용할 수 있습니다. 약관, 속도 제한, 출처 표기, 유료 조건 준수는 사용자 책임입니다.

## 면책

이 저장소는 개인 리서치 전용이며 투자 자문이 아닙니다. 매매 전 중요한 정보는 반드시 별도로 검증하세요.
