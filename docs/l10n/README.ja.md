# 投資リサーチエージェント

**README 言語** · [English](../../README.md) · [繁體中文](README.zh-Hant.md) · [简体中文](README.zh-Hans.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [한국어](README.ko.md)

英語版 README が正式版で、他言語は読みやすさのための翻訳です。

このリポジトリは AI 投資リサーチエージェントのローカル作業環境です。実際の用途は主に 3 つです。

1. 設定と取引履歴を踏まえてリサーチ質問に答える。
2. 毎日の HTML ポートフォリオレポートを作る。
3. 自然言語メッセージ、CSV、または JSON から新規取引（BUY / SELL / DEPOSIT / WITHDRAW / DIVIDEND / FEE / FX_CONVERT）をローカル SQLite に記録する。

OpenAI Codex、Claude Code、Gemini CLI など、ファイル読取とコマンド実行ができるエージェント環境で使う前提です。

**モデル層:** 分析の信頼性と本リポジトリの契約（`AGENTS.md`、レポートおよび取引ガイドライン）への準拠のため、**Claude Sonnet 4.6** を **High** 推論負荷で使うか、同等以上の能力の新しいモデル層を選んでください。軽量モデルではチェックリストを飛ばしたり、取引を誤読したり、リサーチの深さが落ちることがあります。

## 重要ファイル

- `AGENTS.md`: リサーチエージェントの思考と文体の仕様。
- `SETTINGS.md`: 言語、完全な `Investment Style And Strategy`、基準通貨、ポジション上限。ローカル専用。
- `transactions.db`: ローカル SQLite。各取引（売買、入出金、配当、手数料、為替換算）と根拠・タグを保持。2 つの派生テーブル（`open_lots`、`cash_balances`）は INSERT のたびに自動再構築され、未決済ポジションの投影ビューとなる。**実現損益・未実現損益・損益パネルを駆動。** ローカル専用。`docs/transactions_agent_guidelines.md` を参照。
- `docs/portfolio_report_agent_guidelines.md`: レポート契約。ニュース／イベントの全件カバレッジ、Strategy readout、reviewer pass を含みます。さらに `docs/portfolio_report_agent_guidelines/` 内のリンク先分割ファイルも全て読む必要があります。
- `docs/transactions_agent_guidelines.md`: 取引台帳の単一契約——DB スキーマ、自然言語の parse → plan → confirm → write ワークフロー、CSV／JSON／メッセージ取り込み、ロット照合、損益パネル、移行。
- `scripts/fetch_prices.py`: 標準の最新価格・為替取得。`transactions.db` からポジションを読みます。
- `scripts/fetch_history.py`: 付随する日次終値＋為替履歴取得（損益パネル用。`prices.json` に `_history` / `_fx_history` を書き込み）。`transactions.db` からポジションを読みます。
- `scripts/transactions.py`: SQLite 保存と取り込み（CSV／JSON／メッセージ）、リプレイエンジン、残高再構築、実現＋未実現損益、1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME の損益パネル。
- `scripts/generate_report.py`: 標準の HTML レンダラ。`report_context.json` の `strategy_readout`、`reviewer_pass`、`profit_panel`、`realized_unrealized` を取り込みます。`transactions.db` からポジションを読みます。
- `reports/`: 出力先。ローカル専用。

## 初回セットアップ

```sh
cp SETTINGS.example.md SETTINGS.md
python scripts/transactions.py db init        # transactions.db を作成
```

次のいずれか:

- **既存の `HOLDINGS.md` からブートストラップ**（iteration-2 ユーザー）:

  ```sh
  python scripts/transactions.py migrate --holdings HOLDINGS.md
  python scripts/transactions.py verify
  rm HOLDINGS.md HOLDINGS.md.bak HOLDINGS.example.md
  ```

  `migrate` は既存ロットごとに 1 件の BUY、現金通貨ごとに 1 件の DEPOSIT を合成し、再構築後の残高がシードと一致するようにします。verify が通ったら上記 markdown は不要です。

- **または証券会社明細をインポート**（CSV または JSON）:

  ```sh
  python scripts/transactions.py db import-csv --input statements/2026-04-schwab.csv
  python scripts/transactions.py db import-json --input transactions.json
  ```

- **または**エージェントに平易な英語で取引を逐次伝える（例: "bought 30 NVDA at $185 yesterday"）。エージェントが解析し、正規 JSON を示し、`yes` で `db add`。`docs/transactions_agent_guidelines.md` §3 を参照。

書き込みのたびに `python scripts/transactions.py verify` を実行し、物化テーブル `open_lots` + `cash_balances` がログのフルリプレイと一致することを確認します。

`SETTINGS.md`、`transactions.db`、生成レポート、ランタイムファイル（`prices.json`、`report_context.json`、`temp/`）は `.gitignore` 対象です。

### `SETTINGS.md` と `transactions.db` の運用

- 言語設定、投資戦略全体、基準通貨、ポジション上限、レポート既定を変更したら `SETTINGS.md` を更新します。
- `Investment Style And Strategy` 全体には、エージェントに演じてほしい投資家像を書きます。気質、ドローダウン許容度、サイズ配分、保有期間、エントリー規律、逆張り許容度、誇張表現への許容度、禁止領域、意思決定スタイルを含めます。
- `transactions.db` をライブポジションと現金の単一ソースとして扱います。新規フローはエージェントまたは CSV／JSON インポート経由でここに入り、派生ビュー `open_lots` + `cash_balances` は自動更新されます。
- 約定が終わるたびに、分析精度を保つためすぐエージェントへ記帳を依頼します。
- レポート生成前に `SETTINGS.md` を軽く確認し、`transactions.py db stats` で古いデータがないか見ます。

## よく使うワークフロー

通常は、次の 3 つのどれかをエージェントに頼めば足ります。

### 1. リサーチ

例:

- "NVDA を今のポートフォリオ目線で分析して。"
- "今の AI エクスポージャーはどれくらい？"
- "決算前に短期ポジションを減らすべき？"

エージェントは `SETTINGS.md` の `Investment Style And Strategy` 全体と、`transactions.db`（`open_lots` + `cash_balances`）からポジションを読み、`AGENTS.md` に従って、あなたの戦略を一人称で実行する形で回答します。

### 2. ポートフォリオレポート

例:

- "今日のポートフォリオ健診を作って。"
- "プレマーケット用レポートを出して。"

成果物は `reports/` 配下の単一 self-contained HTML です。

`auto mode`、`routine`、またはその他の無人環境でレポートを生成する場合、保有ティッカーを外部の市場データソースへ送信して価格を取得する前に、エージェントが明確な同意を得ることを推奨します。明確な同意文の例: `保有ティッカーを外部の市場データソースに送信して価格を取得し、今日のレポートを生成することに同意します。` 英語では: `I agree to let you send my holdings tickers to external market data sources to retrieve prices and generate today's report.`

完全なレポート実行は 4 フェーズです。まず Gather でデータを集め、価格・指標・ニュース・イベントが揃ってから Think で判断を作り、レンダリング前にシニア PM として Review し、最後に Render します。Gather では非現金の全保有銘柄について最新ニュースと 30 日以内の予定イベントを検索し、上位ウェイトだけに絞りません。Review は有用な指摘を注記するだけで、ユーザー側の判断を書き換えません。

エージェントは毎回作り直さず、標準スクリプトを使うべきです。3 本とも自動的に `transactions.db` からポジションを読みます。

```sh
python scripts/fetch_prices.py --settings SETTINGS.md --output prices.json
# いずれかの行に agent_web_search:TODO_required が残る場合、fetch_prices は非ゼロで終了します。
# レンダリング前に tier 3 / tier 4 の価格フォールバックを完了してください。

# 損益パネル用: 日次終値と為替履歴を取得
python scripts/fetch_history.py \
    --settings SETTINGS.md \
    --merge-into prices.json --output prices_history.json

# 生涯実現＋未実現スナップショット
python scripts/transactions.py pnl \
    --prices prices.json --settings SETTINGS.md \
    > realized_unrealized.json

# 期間損益パネル（1D / 7D / MTD / 1M / YTD / 1Y / ALLTIME）
python scripts/transactions.py profit-panel \
    --prices prices.json \
    --settings SETTINGS.md --output profit_panel.json

# レンダリング前に profit_panel.json と realized_unrealized.json を
# report_context.json のキー "profit_panel" と "realized_unrealized" にマージする。

python scripts/generate_report.py \
    --settings SETTINGS.md \
    --prices prices.json --context report_context.json \
    --output reports/2026-04-28_1330_portfolio_report.html
```

要求言語が組み込み UI 辞書 `english`、`traditional chinese`、`simplified chinese` 以外なら、実行中のエージェントが `scripts/i18n/report_ui.en.json` を一時 overlay に翻訳し、`--ui-dict` で渡します。

`report_context.json` には、一人称の Strategy readout 用に `strategy_readout`、レビュー注記やサマリー用に `reviewer_pass` を入れられます。旧 `style_readout` キーもレンダリングされますが、新しい context では `strategy_readout` を使ってください。

### 3. 取引の記録

例:

- "昨日 NVDA を 185 ドルで 30 株買った。"
- "今日 TSLA を 400 ドルで 10 株売った。"
- "GOOG の Q1 配当、80 ドル。"
- "次の買いのために 5,000 ドル入金した。"
- "Schwab の CSV があるのでインポートして。"

厳守ルール: エージェントは解析プランと正規 JSON blob を示し、同一ターンで明示的な `yes` を受け取るまで `transactions.db` に INSERT してはいけません。書き込み前には毎回 `transactions.db.bak` にバックアップし、その後自動残高再構築と `verify` を行います。`docs/transactions_agent_guidelines.md` §3 を参照。

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
- `docs/transactions_agent_guidelines.md`

個人データは仕様ファイルに入れないでください。

## プライバシー

git で追跡されるもの:

- エージェント仕様
- サンプルテンプレート
- Python スクリプト
- README
- デザイン参照ファイル

git で追跡されないもの:

- `SETTINGS.md`
- `transactions.db`
- `transactions.db.bak`
- 生成レポート
- `prices.json`、`prices_history.json`、`report_context.json`、`temp/` などの実行生成物

## サードパーティデータ

このプロジェクトは、相場データや為替ソースを所有も保証もしません。価格取得では公開エンドポイント（Stooq JSON、Yahoo v8 chart、Binance、CoinGecko、Frankfurter／ECB、Open ExchangeRate-API、TWSE／TPEx MIS）、任意の API キー（Twelve Data、Finnhub、Alpha Vantage、FMP、Tiingo、Polygon、J-Quants、CoinGecko Demo）、`yfinance` のようなラッパーを使うことがあります。台湾銘柄では、トークン不要の MIS fallback が上場 (`tse_`) と OTC (`otc_`) の両チャネルを試し、`[TW]` / `[TWO]` の分類ミスによる価格漏れを減らします。利用規約、レート制限、帰属表示、課金条件の順守は利用者の責任です。

## 免責

このリポジトリは個人リサーチ専用であり、投資助言ではありません。売買前に重要情報を必ず独自に確認してください。
