# Investments — 개인 리서치·포트폴리오 리포트

**README 언어** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

저장소 루트의 **영어** [README](../../README.md)이 최신·권위 있는 프로젝트 개요입니다. 다른 언어는 읽기 편의를 위한 것이며, 해석이 다르면 영어를 따르세요.

이 저장소는 AI 투자 리서치 에이전트의 개인 작업 공간입니다. 포함 항목:

1. 에이전트 사양(사고·문체).
2. 개인 데이터(보유·설정) — git에 포함되지 않음.
3. `reports/`에 생성된 HTML 보고서 — git 제외.
4. 포트폴리오 리포트 HTML 디자인 참고 샘플.
5. `scripts/`의 Python 템플릿 두 개 — 세션마다 직접 실행, 매번 가격·HTML 코드를 새로 쓸 필요 없음.

에이전트는 LLM 클라이언트(예: Cowork / Claude)에서 동작합니다. "포트폴리오 헬스체크"를 요청하면 사양과 개인 데이터를 읽고, `scripts/fetch_prices.py`로 시장별 소스에서 최신가와 FX 환산 환율을 자동으로 가져오며(사양의 페이싱·폴백), `scripts/generate_report.py`로 `reports/`에 자급자족 HTML을 씁니다.

## 저장소 구조

```
.
├── README.md
├── docs/
│   ├── l10n/
│   ├── portfolio_report_agent_guidelines.md
│   ├── portfolio_report_agent_guidelines/
│   └── holdings_update_agent_guidelines.md
├── AGENTS.md
├── SETTINGS.md
├── SETTINGS.example.md
├── HOLDINGS.md
├── HOLDINGS.md.bak
├── HOLDINGS.example.md
├── scripts/
│   ├── fetch_prices.py
│   ├── generate_report.py
│   └── i18n/
│       ├── report_ui.en.json
│       ├── report_ui.zh-Hant.json
│       └── report_ui.zh-Hans.json
├── .gitignore
└── reports/
    ├── _sample_redesign.html
    └── *_portfolio_report.html
```

## 최초 설정

1. 예제를 복사한 뒤 실제 데이터를 채웁니다:

   ```sh
   cp SETTINGS.example.md SETTINGS.md
   cp HOLDINGS.example.md HOLDINGS.md
   ```

2. `SETTINGS.md` 편집: 언어, 투자 성향(리스크에 맞게), (선택) 경고용 포지션 한도.

3. `HOLDINGS.md` 편집: 네 구획(`Long Term`, `Mid Term`, `Short Term`, `Cash Holdings`) 유지. 한 로트 한 줄: `<TICKER>: 수량 @ 단가 on <YYYY-MM-DD> [<MARKET>]` — 날짜는 보유기간 분석에, `[<MARKET>]`는 `yfinance` 심볼·폴백에 사용. 일반 태그: `[US]`, `[TW]`, `[TWO]`, `[JP]`, `[HK]`, `[LSE]`, `[crypto]`, `[FX]`, `[cash]`. 전체 표는 `HOLDINGS.example.md`와 `docs/portfolio_report_agent_guidelines.md` §4.1. 모를 때 `?` — 영향 셀은 `n/a`(해당 없음은 `—`).

`HOLDINGS*`, `SETTINGS.md`는 `.gitignore`이며 git으로 나가지 않습니다.

## 에이전트 사용

**모델:** 분석·보고 품질을 위해 **최소 Claude Sonnet 4.6(High) 또는 그에 상당하거나 더 강한 추론 모델** 사용을 권장합니다. 긴 보유 목록·체크리스트·종합 섹션에는 충분한 추론이 필요하며, 가벼운 모델은 단계 생략이나 누락이 생기기 쉽습니다.

**환경:** 파일을 읽고 명령을 실행할 수 있는 코딩 에이전트에서 이 폴더를 여세요. 예: **Claude Code**, **OpenAI Codex**(CLI 또는 IDE), **Google Gemini**(CLI 등). 특정 제품이 필수는 아니며, `AGENTS.md`와 `docs/` 규격을 이 저장소에 적용할 수 있으면 됩니다.

### 1. 리서치 질문

`SETTINGS.md`·`HOLDINGS.md`를 읽고 `AGENTS.md` 프레임(결론, 펀더멘털, 밸류에이션, 기술, 리스크, 플레이북, 점수, 판단)을 따릅니다.

### 2. 포트폴리오 헬스체크

`docs/portfolio_report_agent_guidelines.md`(및 인덱스가 링크하는 분할 파일)에 따라 `reports/`에 단일 HTML. 11절(요약, 대시보드, 보유·손익·로트 팝오버, 보유기간·페이싱, 테마/섹터, 뉴스, 30일 캘린더, 리스크/기회, 권고 조정, 액션, 출처·갭). 고우선 경고 시 상단 배너.

에이전트는 두 Python 템플릿을 실행합니다:

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

`report_context.json`은 서술층(오늘의 견해, 뉴스, 권고, 액션)이며 수동 FX 환율을 넣지 않습니다. FX 환산 데이터는 `scripts/fetch_prices.py`가 `prices.json["_fx"]`에 자동으로 기록하고, 수치는 스크립트가 기계적으로 생성합니다.

`SETTINGS.md`가 내장 UI 사전에 없는 단일 언어(`english`, `traditional chinese`, `simplified chinese` 외)를 쓰면, **실행 중인 에이전트**가 `scripts/i18n/report_ui.en.json`을 번역한 임시 JSON overlay를 `--ui-dict`(또는 context의 `ui_dictionary`)로 `scripts/generate_report.py`에 넘깁니다. 렌더러는 외부 번역 API를 호출하지 않습니다.

### 3. 자연어로 보유 업데이트

거래를 설명합니다. `docs/holdings_update_agent_guidelines.md` — 조용한 덮어쓰기 없음, 명시적 `yes` 전까지 확정 없음, `HOLDINGS.md.bak` 백업.

## 생성물

`reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html` — 외부 CSS/JS/폰트/차트 없이 단일 파일. `scripts/generate_report.py`는 `scripts/i18n/report_ui.en.json` 등 내장 UI 사전을 로드합니다(위 `--ui-dict` 참고). `reports/_sample_redesign.html`은 캐노니컬 시각 기준(삭제 금지). `generate_report.py`가 기본 `--sample` 경로로 CSS를 읽습니다.

## 사양 편집

`AGENTS.md`, `docs/portfolio_report_agent_guidelines.md`(및 `docs/portfolio_report_agent_guidelines/`에 링크된 분할 파일), `docs/holdings_update_agent_guidelines.md`가 실행을 규정합니다. 개인 데이터는 `SETTINGS`·`HOLDINGS`에. 대규모 변경 후 보고서 한 건 재생성으로 검증하세요.

## 프라이버시

보유·백업·설정·생성 HTML과 실행 시 생성되는 `prices.json`, `report_context.json`은 git-ignored. 추적되는 것은 템플릿·사양. fork·공유 시에도 실제 포지션은 로컬에만 둡니다.

## 제3자 데이터·API·속도 제한

**이 프로젝트는 시세·환율 API를 소유·운영·보증하지 않습니다.** `scripts/fetch_prices.py` 등은 공개 엔드포인트, `SETTINGS.md`에 설정한 선택적 API 키, `yfinance`처럼 제3자를 감싼 라이브러리를 사용할 수 있습니다. **각 제공자의 서비스 약관·허용 사용 정책·속도 제한을 준수해야 합니다.** 과도하거나 위반 요청은 키나 IP가 제한될 수 있습니다. 사양에 페이싱과 폴백이 있으나 **합법·약관 준수 사용은 사용자 책임**입니다. 출처가 표기·계약·유료를 요구하면 해당 규칙을 따르세요.

## 면책

이 저장소와 보고서는 개인 연구용입니다. 투자 자문·매수·매도 권유가 아니며, 거래 전에 반드시 독립적으로 검증하십시오. 데이터 공백은 드러나도 오류는 남을 수 있습니다.
