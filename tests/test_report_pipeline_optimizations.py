import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_report_html import check_html_text  # noqa: E402
from build_portfolio_report_context import build_context  # noqa: E402
from fetch_prices import (  # noqa: E402
    MarketType,
    PriceResult,
    _currency_from_history_cache,
    _is_valid_latest_price,
    _verify_currency_via_internet,
    _try_no_token_twse_stock_day,
)
from transactions import load_fetch_universe_lots_markdown  # noqa: E402
from validate_report_context import validate_report_context  # noqa: E402


def _write_event(ledger_dir: Path, name: str, body: str) -> None:
    path = ledger_dir / "events" / "2026" / "05" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip() + "\n", encoding="utf-8")


def test_fetch_universe_skips_reversed_typo_transactions(tmp_path: Path):
    ledger = tmp_path / "ledger"
    _write_event(
        ledger,
        "txn-20260512-000001-buy-marry.md",
        """
        # txn-20260512-000001-buy-marry
        ## 2026-05-12 BUY MARRY
        - schema: investment-ledger-event/v1
        - id: txn-20260512-000001-buy-marry
        - date: 2026-05-12
        - type: BUY
        - ticker: MARRY
        - qty: 100
        - price: 19.13
        - currency: USD
        - cash_account: USD
        - bucket: Mid Term (1y+)
        - market: US
        """,
    )
    _write_event(
        ledger,
        "txn-20260512-000002-reversal-cash.md",
        """
        # txn-20260512-000002-reversal-cash
        ## 2026-05-12 REVERSAL
        - schema: investment-ledger-event/v1
        - id: txn-20260512-000002-reversal-cash
        - date: 2026-05-12
        - type: REVERSAL
        - target_event_id: txn-20260512-000001-buy-marry
        - rationale: Correction: ticker typo MARRY should be MRAAY
        """,
    )
    _write_event(
        ledger,
        "txn-20260512-000003-buy-mraay.md",
        """
        # txn-20260512-000003-buy-mraay
        ## 2026-05-12 BUY MRAAY
        - schema: investment-ledger-event/v1
        - id: txn-20260512-000003-buy-mraay
        - date: 2026-05-12
        - type: BUY
        - ticker: MRAAY
        - qty: 100
        - price: 19.13
        - currency: USD
        - cash_account: USD
        - bucket: Mid Term (1y+)
        - market: US
        """,
    )

    tickers = {lot.ticker for lot in load_fetch_universe_lots_markdown(ledger)}

    assert "MRAAY" in tickers
    assert "MARRY" not in tickers


def test_twse_stock_day_fallback_parses_official_latest_close():
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "stat": "OK",
                "data": [
                    ["2026/05/12", "0", "0", "0", "0", "0", "2,255.00"],
                    ["2026/05/13", "0", "0", "0", "0", "0", "2,220.00"],
                ],
            }

    class Session:
        @staticmethod
        def get(*_args, **_kwargs):
            return Response()

    result = _try_no_token_twse_stock_day("2330", Session())

    assert result is not None
    assert result["latest_price"] == 2220.0
    assert result["prior_close"] == 2255.0
    assert result["price_source"] == "no_token:twse_stock_day"
    assert result["currency"] == "TWD"


def test_invalid_latest_prices_are_rejected():
    assert _is_valid_latest_price(1.0)
    assert not _is_valid_latest_price(float("nan"))
    assert not _is_valid_latest_price(None)
    assert not _is_valid_latest_price(0)


def test_currency_verify_uses_twd_for_taiwan_without_network():
    class FailingSession:
        @staticmethod
        def get(*_args, **_kwargs):
            raise AssertionError("Taiwan currency should not hit network")

    pr = PriceResult(ticker="2330", market=MarketType.TW, yfinance_symbol="2330.TW")

    _verify_currency_via_internet(pr, FailingSession(), pacer=None)  # type: ignore[arg-type]

    assert pr.currency == "TWD"
    assert "currency_verify:taiwan_market_twd" in pr.fallback_chain


def test_currency_from_history_cache_reads_newest_cached_currency(tmp_path):
    cache = tmp_path / "market_data_cache.json"
    cache.write_text(
        """
        {
          "price_history": {
            "VWRA|LSE": [
              {"date": "2026-05-01", "close": 100, "currency": null},
              {"date": "2026-05-02", "close": 101, "currency": "usd"}
            ]
          },
          "fx_history": {}
        }
        """,
        encoding="utf-8",
    )

    assert _currency_from_history_cache("VWRA", MarketType.LSE, cache) == "USD"


def test_report_html_check_catches_external_assets_and_nan():
    html = '<html lang="zh-Hant"><head><script src="x.js"></script></head><body>NaN</body></html>'

    errors = check_html_text(html, require_lang="zh-Hant")

    assert any("external script" in error for error in errors)
    assert any("raw NaN" in error for error in errors)


def test_portfolio_context_builder_authors_only_portfolio_keys():
    snapshot = {
        "today": "2026-05-14",
        "settings": {"locale": "zh-Hant", "display_name": "繁體中文"},
        "aggregates": [
            {"ticker": "NVDA", "market": "US", "market_value": 16000, "lots": []},
            {"ticker": "QQQ", "market": "US", "market_value": 10000, "lots": []},
            {"ticker": "USD", "market": "cash", "is_cash": True, "market_value": 5000, "lots": []},
        ],
        "totals": {"total_assets": 31000},
        "report_accuracy": {
            "dimensions": [
                {"id": "quote_coverage", "score": 100, "detail": {}},
                {"id": "profit_reconciliation", "score": 92.5, "detail": {"max_abs_gap": 12.3}},
            ]
        },
    }

    context = build_context(snapshot, "## Investment Style And Strategy\n- test")

    assert validate_report_context(context, snapshot, report_type="portfolio_report") == []
    assert "我" in context["strategy_readout"]
    assert "theme_sector_html" in context
    assert "theme_sector_audit" in context
    assert set(context["theme_sector_audit"]["tickers"]) == {"NVDA", "QQQ"}
    assert any(gap["summary"].startswith("資料品質") for gap in context["data_gaps"])
    assert any("ETF" in gap["summary"] for gap in context["data_gaps"])
    for forbidden in [
        "news",
        "events",
        "research_coverage",
        "research_targets",
        "high_opps",
        "adjustments",
        "actions",
        "trading_psychology",
        "holdings_actions",
    ]:
        assert forbidden not in context
