# 투자 리서치 에이전트

**README 언어** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

영문 README가 공식판이며, 다른 언어는 읽기 편의를 위한 번역입니다.

이 저장소는 AI 투자 리서치 에이전트를 위한 로컬 작업공간입니다. 실제 용도는 주로 세 가지입니다.

1. 설정과 거래 내역을 바탕으로 리서치 질문에 답한다.
2. 매일 HTML 포트폴리오 리포트를 만든다.
3. 자연어 메시지, CSV 또는 JSON 파일의 신규 거래(BUY / SELL / DEPOSIT / WITHDRAW / DIVIDEND / FEE / FX_CONVERT)를 로컬 SQLite DB에 기록한다.

OpenAI Codex, Claude Code, Gemini CLI처럼 파일을 읽고 명령을 실행할 수 있는 에이전트 환경에서 사용하는 전제를 둡니다.

**모델 등급:** 분석의 신뢰성과 이 저장소 계약(`AGENTS.md`, 리포트 및 거래 가이드라인) 준수를 위해 **Claude Sonnet 4.6**에 **High** 추론 강도를 사용하거나, 그에 버금가거나 더 능력 있는 최신 모델 등급을 쓰세요. 더 가벼운 모델은 체크리스트를 건너뛰거나 거래를 잘못 읽거나 연구 깊이가 약해질 수 있습니다.

## 핵심 파일

- `AGENTS.md`: 리서치 에이전트의 사고 방식과 문체 규격
- `SETTINGS.md`: 언어, 전체 `Investment Style And Strategy`, 기준 통화, 포지션 한도. 로컬 전용
- `transactions.db`: 로컬 SQLite. 모든 거래(매매, 입출금, 배당, 수수료, 환전)와 근거·태그를 보관합니다. 두 개의 파생 테이블(`open_lots`, `cash_balances`)은 INSERT마다 자동 재구축되며 미결제 포지션 투영 뷰입니다.**실현 손익·미실현 손익·손익 패널을 구동합니다.** 로컬 전용. `docs/transactions_agent_guidelines.md` 참조.
- `docs/portfolio_report_agent_guidelines.md`: 리포트 계약. 전체 뉴스/이벤트 커버리지, Strategy readout, reviewer pass를 포함하며, `docs/portfolio_report_agent_guidelines/` 아래 링크된 분할 파일도 모두 읽어야 함
- `docs/transactions_agent_guidelines.md`: 단일 거래 원장 계약——DB 스키마, 자연어 parse → plan → confirm → write 워크플로, CSV/JSON/메시지 수집 경로, 로트 매칭, 손익 패널, 마이그레이션
- `scripts/fetch_prices.py`: 표준 최신 가격/환율 수집. `transactions.db`에서 포지션을 읽음
- `scripts/fetch_history.py`: 보조 일봉 종가+환율 이력 수집(손익 패널용, `prices.json`에 `_history` / `_fx_history` 기록). `transactions.db`에서 포지션을 읽음
- `scripts/transactions.py`: SQLite 저장 및 수집(CSV/JSON/메시지), 리플레이 엔진, 잔액 재구축, 실현+미실현 손익, 1D/7D/MTD/1M/YTD/1Y/ALLTIME 손익 패널
- `scripts/generate_report.py`: 표준 HTML 렌더러. `report_context.json`의 `strategy_readout`, `reviewer_pass`, `profit_panel`, `realized_unrealized`를 읽음. `transactions.db`에서 포지션을 읽음
- `reports/`: 출력 폴더. 로컬 전용

## 최초 설정

```sh
cp SETTINGS.example.md SETTINGS.md
python scripts/transactions.py db init        # transactions.db 생성
```

이후 다음 중 하나:

- **기존 `HOLDINGS.md`에서 부트스트랩**(iteration-2 사용자):

  ```sh
  python scripts/transactions.py migrate --holdings HOLDINGS.md
  python scripts/transactions.py verify
  rm HOLDINGS.md HOLDINGS.md.bak HOLDINGS.example.md
  ```

  `migrate`는 기존 로트마다 BUY 한 건, 현금 통화마다 DEPOSIT 한 건을 합성해 재구축 잔액이 시드와 일치하도록 합니다. verify 통과 후 위 markdown은 더 이상 필요 없습니다.

- **또는 증권사 명세 가져오기**(CSV 또는 JSON):

  ```sh
  python scripts/transactions.py db import-csv --input statements/2026-04-schwab.csv
  python scripts/transactions.py db import-json --input transactions.json
  ```

- **또는** 에이전트에게 평이한 영어로 거래를 건네기(예: "bought 30 NVDA at $185 yesterday"). 에이전트가 파싱·정규 JSON을 보여주고, `yes` 후 `db add`. `docs/transactions_agent_guidelines.md` §3 참조.

모든 쓰기 후 `python scripts/transactions.py verify`를 실행해 물질화된 `open_lots` + `cash_balances`가 전체 로그 리플레이와 일치하는지 확인합니다.

`SETTINGS.md`, `transactions.db`, 생성 리포트, 런타임 파일(`prices.json`, `report_context.json`, `temp/`)은 `.gitignore` 대상입니다.

### `SETTINGS.md`와 `transactions.db` 운용

- 선호 언어, 전체 투자 전략, 기준 통화, 포지션 한도, 리포트 기본값이 바뀌면 `SETTINGS.md`를 갱신합니다.
- `Investment Style And Strategy` 전체에는 에이전트가 따라야 할 투자자상을 씁니다. 성향, 손실폭 허용도, 포지션 크기, 보유 기간, 진입 규율, 역발상 허용도, 과장된 서사에 대한 허용도, 금지 영역, 의사결정 스타일을 포함합니다.
- `transactions.db`를 라이브 포지션과 현금의 단일 소스로 둡니다. 새 흐름은 에이전트 또는 CSV/JSON 가져오기로 여기에 들어가며, 파생 뷰 `open_lots` + `cash_balances`는 자동으로 갱신됩니다.
- 체결이 끝날 때마다 분석 정확도를 위해 즉시 에이전트에 거래 기록을 요청합니다.
- 리포트를 생성하기 전에 `SETTINGS.md`를 빠르게 검토하고 `transactions.py db stats`로 오래된 데이터가 없는지 확인합니다.

## 자주 쓰는 워크플로

보통은 아래 세 가지 중 하나만 에이전트에 요청하면 됩니다.

### 1. 리서치

예시:

- "NVDA를 현재 포트폴리오 기준으로 분석해줘."
- "지금 내 AI 익스포저가 얼마나 돼?"
- "실적 발표 전에 단기 포지션을 줄여야 할까?"

에이전트는 `SETTINGS.md`의 `Investment Style And Strategy` 전체와 `transactions.db`(`open_lots` + `cash_balances`)에서 포지션을 읽고, `AGENTS.md`에 따라 당신의 전략을 1인칭으로 실행하는 형태로 답합니다.

### 2. 포트폴리오 리포트

예시:

- "오늘 포트폴리오 헬스체크 만들어줘."
- "프리마켓 리포트 돌려줘."

결과물은 `reports/` 아래의 단일 self-contained HTML 파일입니다.

`auto mode`, `routine` 또는 기타 무인 환경에서 리포트를 생성할 때는, 보유 종목 티커를 외부 시장 데이터 소스로 보내 가격을 조회하기 전에 에이전트가 명시적인 동의를 받는 것을 권장합니다. 명확한 동의 문구 예시는 다음과 같습니다: `내 보유 티커를 외부 시장 데이터 소스로 보내 가격을 조회하고 오늘의 리포트를 생성하는 데 동의합니다.` 영어 문구는 다음과 같습니다: `I agree to let you send my holdings tickers to external market data sources to retrieve prices and generate today's report.`

완전한 리포트 실행은 네 단계입니다. 먼저 Gather에서 데이터를 수집하고, 가격/지표/뉴스/이벤트가 모인 뒤 Think에서 판단을 만들며, 렌더링 전에 시니어 PM 관점으로 Review하고, 마지막으로 Render합니다. Gather 단계는 현금이 아닌 모든 보유 종목에 대해 최신 뉴스와 30일 이내 이벤트를 검색하며, 비중 상위 종목만 보지 않습니다. Review 단계는 필요한 경우 검토 메모를 붙일 뿐, 사용자의 분석 내용을 대체하지 않습니다.

에이전트는 매번 새로 쓰지 말고 표준 스크립트를 사용해야 합니다. 세 스크립트 모두 자동으로 `transactions.db`에서 포지션을 읽습니다.

```sh
python scripts/fetch_prices.py --settings SETTINGS.md --output prices.json
# 어떤 행에 agent_web_search:TODO_required가 남아 있으면 fetch_prices는 0이 아닌 코드로 종료합니다.
# 렌더링 전에 tier 3 / tier 4 가격 폴백을 완료해야 합니다.

# 손익 패널용: 일봉 종가 및 환율 이력 수집
python scripts/fetch_history.py \
    --settings SETTINGS.md \
    --merge-into prices.json --output prices_history.json

# 평생 실현+미실현 스냅샷
python scripts/transactions.py pnl \
    --prices prices.json --settings SETTINGS.md \
    > realized_unrealized.json

# 기간 손익 패널(1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME)
python scripts/transactions.py profit-panel \
    --prices prices.json \
    --settings SETTINGS.md --output profit_panel.json

# 렌더링 전에 profit_panel.json과 realized_unrealized.json을
# report_context.json의 키 "profit_panel"과 "realized_unrealized"로 병합합니다.

python scripts/generate_report.py \
    --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

요청 언어가 내장 UI 사전 `english`, `traditional chinese`, `simplified chinese` 외라면, 실행 중인 에이전트가 `scripts/i18n/report_ui.en.json`을 임시 overlay로 번역해 `--ui-dict`로 넘깁니다.

`report_context.json`에는 1인칭 Strategy readout용 `strategy_readout`과 검토 메모/요약용 `reviewer_pass`를 넣을 수 있습니다. 기존 `style_readout` 키도 렌더링되지만, 새 context는 `strategy_readout`을 사용해야 합니다.

### 3. 거래 기록

예시:

- "어제 NVDA를 185달러에 30주 샀어."
- "오늘 TSLA를 400달러에 10주 팔았어."
- "GOOG Q1 배당 80달러."
- "다음 매수를 위해 5,000달러 입금했어."
- "여기 Schwab CSV야 — 가져와 줘."

강한 규칙: 에이전트는 파싱 계획과 정규 JSON blob을 보여주고, 같은 턴에서 명시적 `yes`를 받기 전까지 `transactions.db`에 INSERT하면 안 됩니다. 쓰기 전에는 항상 `transactions.db.bak`로 백업한 뒤 자동 잔액 재구축과 `verify`를 수행합니다. `docs/transactions_agent_guidelines.md` §3 참조.

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
- `docs/transactions_agent_guidelines.md`

개인 데이터는 규격 파일에 넣지 마세요.

## 프라이버시

git에 추적되는 것:

- 에이전트 규격
- 예시 템플릿
- Python 스크립트
- README
- 디자인 참고 파일

git에 추적되지 않는 것:

- `SETTINGS.md`
- `transactions.db`
- `transactions.db.bak`
- 생성 리포트
- `prices.json`, `prices_history.json`, `report_context.json`, `temp/` 같은 실행 산출물

## 서드파티 데이터

이 프로젝트는 시세나 환율 소스를 소유하거나 보장하지 않습니다. 가격 수집 과정은 공개 엔드포인트(Stooq JSON, Yahoo v8 chart, Binance, CoinGecko, Frankfurter/ECB, Open ExchangeRate-API, TWSE/TPEx MIS), 선택적 API 키(Twelve Data, Finnhub, Alpha Vantage, FMP, Tiingo, Polygon, J-Quants, CoinGecko Demo), `yfinance` 같은 래퍼를 사용할 수 있습니다. 대만 종목은 토큰 없는 MIS fallback이 상장(`tse_`)과 OTC(`otc_`) 채널을 모두 시도해 `[TW]` / `[TWO]` 분류 오류로 인한 가격 누락을 줄입니다. 약관, 속도 제한, 출처 표기, 유료 조건 준수는 사용자 책임입니다.

## 면책

이 저장소는 개인 리서치 전용이며 투자 자문이 아닙니다. 매매 전 중요한 정보는 반드시 별도로 검증하세요.
