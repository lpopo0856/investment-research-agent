# Investments — 個人リサーチとポートフォリオレポート

**README 言語** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

リポジトリ直下の**英語** [README](../../README.md) が正式かつ随時更新されるプロジェクト概要です。他言語は閲覧の補助であり、解釈に相違があれば英語に従ってください。

このリポジトリは、AI 投資リサーチ用エージェントの個人用ワークスペースです。含まれるもの:

1. エージェント仕様（思考と出力の仕方）。
2. 個人データ（保有銘柄・設定）— git には含めません。
3. `reports/` 配下の生成 HTML レポート — 同様に git 対象外。
4. ポートフォリオレポート用の HTML デザイン参照。
5. `scripts/` 内の Python テンプレート2本。毎回ゼロから価格取得・HTML 生成を書かず、エージェントがそのまま実行する。

エージェントは LLM クライアント内で動作します（例: Cowork / Claude）。「ポートフォリオのヘルスチェックを出して」と依頼すると、仕様と個人データを読み、`scripts/fetch_prices.py` で市場別ソースから最新価格と FX 換算レートを自動取得（仕様のペース制御とフォールバック付き）、`scripts/generate_report.py` で `reports/` に自己完結 HTML を書き出します。

## リポジトリ構成

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

## 初回セットアップ

1. 例のファイルをコピーし、実データを入れます:

   ```sh
   cp SETTINGS.example.md SETTINGS.md
   cp HOLDINGS.example.md HOLDINGS.md
   ```

2. `SETTINGS.md` を編集: 言語、リスクに合った投資スタイルの箇条書き、（任意）警告用のポジション規模の目安。

3. `HOLDINGS.md` を編集: 4 バケット（`Long Term`, `Mid Term`, `Short Term`, `Cash Holdings`）を維持。1 ロット 1 行: `<TICKER>: 数量 @ 取得単価 on <YYYY-MM-DD> [<MARKET>]`。日付は保有期間分析用、`[<MARKET>]` は `yfinance` シンボルとフォールバック階層用。市場タグ例: `[US]`, `[TW]`, `[TWO]`, `[JP]`, `[HK]`, `[LSE]`, `[crypto]`, `[FX]`, `[cash]`。不明は `?` — 影響する欄は `n/a`（該当しない欄は `—`）。詳細は `HOLDINGS.example.md` および `docs/portfolio_report_agent_guidelines.md` §4.1。

`HOLDINGS.md`、バックアップ、`SETTINGS.md` は `.gitignore` され、git 経由で外に出ません。

## 使い方

**モデル：**分析・レポート品質のため、**少なくとも Claude Sonnet 4.6（High）、またはそれ以上の推論能力を持つモデル**の利用を推奨します。長い保有一覧やチェックリスト順守には十分な推論が必要で、軽量モデルでは手順省略や漏れが起きやすくなります。

**環境：**ファイルを読みコマンドを実行できるコーディングエージェントでこのフォルダを開いてください（例：**Claude Code**、**OpenAI Codex**（CLI または IDE）、**Google Gemini**（CLI など））。特定製品は必須ではなく、`AGENTS.md` と `docs/` の仕様を適用できれば構いません。

### 1. リサーチ質問

`SETTINGS.md` と `HOLDINGS.md` を読み、`AGENTS.md` の枠組みで回答（結論、ファンダ、バリュエーション、テクニカル、リスク、プレイブック、スコア、結論）。

### 2. ポートフォリオ・ヘルスチェック

`docs/portfolio_report_agent_guidelines.md`（およびインデックスからリンクされる分割ファイル）に従い `reports/` に単一 HTML。11 セクション（要約、ダッシュボード、保有表と P/L・ロット別ポップオーバー、保有期間とペース、テーマ/セクター、ニュース、30 日カレンダー、高リスク/高オポチュニティ、推奨調整、アクション、ソースとギャップ）。高優先アラート時はその上にバナー。

エージェントは次の2本の Python テンプレを実行:

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

`report_context.json` は編集層（本日の見解、ニュース、推奨、アクション）であり、手動 FX レートは入れない。FX 換算データは `scripts/fetch_prices.py` が `prices.json["_fx"]` に自動出力する。数値はスクリプトが機械的に生成。

組み込み以外の単一言語を `SETTINGS.md` で指定する場合、**実行中のエージェント** は `scripts/i18n/report_ui.en.json` を訳した一時 overlay を `--ui-dict`（または context の `ui_dictionary`）で `scripts/generate_report.py` に渡す。レンダラーが外部翻訳 API を呼ぶことはない。

### 3. 自然言語で保有を更新

取引を言語化する。`docs/holdings_update_agent_guidelines.md` の全ルールに従い、上書きは同じターン内の明示的 `yes` まで行わない。`HOLDINGS.md.bak` にバックアップしてから書き込み。

## 生成物

`reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html` — 単一ファイル、外部 CSS/JS/フォント/チャートなし。`scripts/generate_report.py` は `scripts/i18n/report_ui.en.json` など組み込み UI 辞書を読み込む（上記 `--ui-dict`）。`reports/_sample_redesign.html` はカノニカルなデザイン参照。削除禁止。`generate_report.py` が CSS ソースとして読み取る（既定 `--sample` がこのパス）。

## 仕様の編集

`AGENTS.md`、`docs/portfolio_report_agent_guidelines.md`（および `docs/portfolio_report_agent_guidelines/` 内の分割ファイル）、`docs/holdings_update_agent_guidelines.md` はエージェント挙動の契約。個人データは `SETTINGS` / `HOLDINGS` へ。大きな変更後はレポートを1本再生成して確認。

## プライバシー

保有、設定、生成 HTML、実行時に生成する `prices.json` と `report_context.json` は git-ignored。追跡されるのはテンプレと仕様類。fork 共有時も実ポジはローカルに留まる。

## 第三者データ・API・レート制限

**本プロジェクトはいかなる相場・為替 API も所有・運営・保証しません。** `scripts/fetch_prices.py` 等は公開エンドポイント、`SETTINGS.md` で設定したオプションの API キー、`yfinance` のような第三者を経由するライブラリを利用する場合があります。**各提供者の利用規約・許容される利用・レート制限を遵守してください。** 過度・不当なリクエストではキーや IP が制限されることがあります。仕様にペーシングとフォールバックがありますが、**適法かつ規約に沿った利用は利用者の責任**です。署名・契約・有料が必要なソースは、その提供者のルールに従ってください。

## 免責

本リポジトリとレポートは個人リサーチ用です。投資助言・売買勧誘ではありません。取引前に必ず独立して検証してください。データ欠損は示されますが、誤り得ます。
