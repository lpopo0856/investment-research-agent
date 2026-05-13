import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_report_html import check_html_text  # noqa: E402
from fetch_prices import _is_valid_latest_price, _try_no_token_twse_stock_day  # noqa: E402
from transactions import load_fetch_universe_lots_markdown  # noqa: E402


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


def test_report_html_check_catches_external_assets_and_nan():
    html = '<html lang="zh-Hant"><head><script src="x.js"></script></head><body>NaN</body></html>'

    errors = check_html_text(html, require_lang="zh-Hant")

    assert any("external script" in error for error in errors)
    assert any("raw NaN" in error for error in errors)
