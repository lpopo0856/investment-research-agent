# 投資リサーチエージェント

**README 言語** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

英語版 README が正式版で、他言語は読みやすさのための翻訳です。

このリポジトリは AI 投資リサーチエージェントのローカル作業環境です。実際の用途は主に 3 つです。

1. 設定と保有銘柄を踏まえてリサーチ質問に答える。
2. 毎日の HTML ポートフォリオレポートを作る。
3. 自然言語の売買指示から `HOLDINGS.md` を更新する。

OpenAI Codex、Claude Code、Gemini CLI など、ファイル読取とコマンド実行ができるエージェント環境で使う前提です。

**モデル:** 分析の安定性と本リポジトリの仕様（`AGENTS.md`、レポートおよび保有銘柄のガイドライン）への準拠のため、**Claude Sonnet 4.6** を **High** 推論負荷で使うか、同等以上の能力の新しいモデルを選んでください。軽量モデルではチェックリストを飛ばしたり、保有を誤読したり、リサーチの深さが落ちることがあります。

## 重要ファイル

- `AGENTS.md`: リサーチエージェントの思考と文体の仕様。
- `SETTINGS.md`: 言語、リスクスタイル、基準通貨。ローカル専用。
- `HOLDINGS.md`: 保有銘柄。ローカル専用。
- `docs/portfolio_report_agent_guidelines.md`: レポートの主仕様。さらに `docs/portfolio_report_agent_guidelines/` 内のリンク先分割ファイルも全て読む必要があります。
- `docs/holdings_update_agent_guidelines.md`: 保有更新の仕様。
- `scripts/fetch_prices.py`: 標準の価格・為替取得スクリプト。
- `scripts/generate_report.py`: 標準の HTML レンダラ。
- `reports/`: 出力先。ローカル専用。

## 初回セットアップ

```sh
cp SETTINGS.example.md SETTINGS.md
cp HOLDINGS.example.md HOLDINGS.md
```

その後:

- `SETTINGS.md` を埋める。
- `HOLDINGS.md` を埋める。
- `HOLDINGS.md` の 4 バケット `Long Term`、`Mid Term`、`Short Term`、`Cash Holdings` を維持する。
- 1 ロット 1 行: `<TICKER>: <quantity> shares @ <cost basis> on <YYYY-MM-DD> [<MARKET>]`
- 取得単価や日付が不明なら `?` を使う。

よく使う市場タグ: `[US]`, `[TW]`, `[TWO]`, `[JP]`, `[HK]`, `[LSE]`, `[crypto]`, `[FX]`, `[cash]`

`SETTINGS.md`、`HOLDINGS.md`、`HOLDINGS.md.bak`、生成レポート、よくある実行生成物は `.gitignore` 対象です。

## よく使うワークフロー

通常は、次の 3 つのどれかをエージェントに頼めば足ります。

### 1. リサーチ

例:

- "NVDA を今のポートフォリオ目線で分析して。"
- "今の AI エクスポージャーはどれくらい？"
- "決算前に短期ポジションを減らすべき？"

エージェントは `SETTINGS.md` と `HOLDINGS.md` を読み、`AGENTS.md` に従って回答します。

### 2. ポートフォリオレポート

例:

- "今日のポートフォリオ健診を作って。"
- "プレマーケット用レポートを出して。"

成果物は `reports/` 配下の単一 self-contained HTML です。

エージェントは毎回作り直さず、標準スクリプトを使うべきです:

```sh
python scripts/fetch_prices.py --holdings HOLDINGS.md --settings SETTINGS.md --output prices.json

python scripts/generate_report.py \
    --holdings HOLDINGS.md --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

要求言語が組み込み UI 辞書 `english`、`traditional chinese`、`simplified chinese` 以外なら、実行中のエージェントが `scripts/i18n/report_ui.en.json` を一時 overlay に翻訳し、`--ui-dict` で渡します。

### 3. 自然言語で保有更新

例:

- "昨日 NVDA を 185 ドルで 30 株買った。"
- "今日 TSLA を 400 ドルで 10 株売った。"
- "昨年 9 月の GOOG ロットを 75 株ではなく 70 株に直して。"

厳守ルール: エージェントは解析結果と unified diff を示し、同一ターンで明示的な `yes` を受け取るまで `HOLDINGS.md` を書き換えてはいけません。書き込み前には毎回 `HOLDINGS.md.bak` を作成します。

## レポート出力

ファイル名:

```text
reports/<YYYY-MM-DD>_<HHMM>_portfolio_report.html
```

HTML は単一ファイルで、外部 CSS、JS、フォント、チャートライブラリに依存しません。

`reports/_sample_redesign.html` はデザイン参照なので削除しないでください。

## 仕様を変えるとき

エージェントの挙動を変えたいなら、次を編集します。

- `AGENTS.md`
- `docs/portfolio_report_agent_guidelines.md`
- `docs/portfolio_report_agent_guidelines/` 配下のリンクされた全分割ファイル
- `docs/holdings_update_agent_guidelines.md`

個人データは仕様ファイルに入れないでください。

## プライバシー

git で追跡されるもの:

- エージェント仕様
- テンプレート
- Python スクリプト
- README
- デザイン参照ファイル

git で追跡されないもの:

- `SETTINGS.md`
- `HOLDINGS.md`
- `HOLDINGS.md.bak`
- 生成レポート
- `prices.json` や `report_context.json` などの実行生成物

## サードパーティデータ

このプロジェクトは、相場データや為替ソースを所有も保証もしません。価格取得では公開エンドポイント、任意の API キー、`yfinance` のようなラッパーを使うことがあります。利用規約、レート制限、帰属表示、課金条件の順守は利用者の責任です。

## 免責

このリポジトリは個人リサーチ専用であり、投資助言ではありません。売買前に重要情報を必ず独自に確認してください。
