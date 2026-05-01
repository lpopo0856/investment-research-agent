#!/usr/bin/env python3
"""
Build / refresh the synthetic demo transaction seed and optionally materialize
`demo/transactions.db`. This script only prepares fake transaction data; report
generation is handled by the normal agent workflow (see demo/README.md).

Run from repo root:
  python demo/bootstrap_demo_ledger.py --write-json
  python demo/bootstrap_demo_ledger.py --apply
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
DEMO = REPO / "demo"
JSON_PATH = DEMO / "transactions_history.json"
DB_PATH = DEMO / "transactions.db"

LT, MT, ST = "Long Term", "Mid Term", "Short Term"


def _usd_dep(d: str, amount: float, *, rationale: str = "", tags: list[str] | None = None) -> dict:
    row: dict = {
        "date": d,
        "type": "DEPOSIT",
        "amount": amount,
        "currency": "USD",
        "cash_account": "USD",
        "market": "US",
    }
    if rationale:
        row["rationale"] = rationale
    if tags:
        row["tags"] = tags
    return row


def _twd_dep(d: str, amount: float, *, rationale: str = "", tags: list[str] | None = None) -> dict:
    row: dict = {
        "date": d,
        "type": "DEPOSIT",
        "amount": amount,
        "currency": "TWD",
        "cash_account": "TWD",
        "market": "TW",
    }
    if rationale:
        row["rationale"] = rationale
    if tags:
        row["tags"] = tags
    return row


def _buy(
    d: str,
    t: str,
    q: float,
    p: float,
    bucket: str,
    market: str,
    ccy: str,
    cash: str,
    *,
    fees: float = 0.0,
    rationale: str = "",
    tags: list[str] | None = None,
) -> dict:
    row: dict = {
        "date": d,
        "type": "BUY",
        "ticker": t,
        "qty": q,
        "price": p,
        "bucket": bucket,
        "market": market,
        "currency": ccy,
        "cash_account": cash,
    }
    if fees:
        row["fees"] = fees
    if rationale:
        row["rationale"] = rationale
    if tags:
        row["tags"] = tags
    return row


def _sell(
    d: str,
    t: str,
    q: float,
    p: float,
    market: str,
    ccy: str,
    cash: str,
    *,
    fees: float = 0.0,
    rationale: str = "",
    tags: list[str] | None = None,
) -> dict:
    row: dict = {
        "date": d,
        "type": "SELL",
        "ticker": t,
        "qty": q,
        "price": p,
        "market": market,
        "currency": ccy,
        "cash_account": cash,
    }
    if fees:
        row["fees"] = fees
    if rationale:
        row["rationale"] = rationale
    if tags:
        row["tags"] = tags
    return row


def _div(
    d: str,
    ticker: str,
    amount: float,
    *,
    ccy: str = "USD",
    market: str = "US",
    rationale: str = "",
    tags: list[str] | None = None,
) -> dict:
    row: dict = {
        "date": d,
        "type": "DIVIDEND",
        "ticker": ticker,
        "amount": amount,
        "currency": ccy,
        "cash_account": ccy,
        "market": market,
    }
    if rationale:
        row["rationale"] = rationale
    if tags:
        row["tags"] = tags
    return row


def _withdraw(
    d: str,
    amount: float,
    *,
    ccy: str = "USD",
    rationale: str = "",
    tags: list[str] | None = None,
) -> dict:
    row: dict = {
        "date": d,
        "type": "WITHDRAW",
        "amount": amount,
        "currency": ccy,
        "cash_account": ccy,
        "market": "TW" if ccy == "TWD" else "US",
    }
    if rationale:
        row["rationale"] = rationale
    if tags:
        row["tags"] = tags
    return row


def _fx_convert(
    d: str,
    *,
    usd_out: float,
    twd_in: float,
    rate: float,
    rationale: str = "",
    tags: list[str] | None = None,
) -> dict:
    row: dict = {
        "date": d,
        "type": "FX_CONVERT",
        "from_amount": usd_out,
        "from_currency": "USD",
        "from_cash_account": "USD",
        "to_amount": twd_in,
        "to_currency": "TWD",
        "to_cash_account": "TWD",
        "rate": rate,
    }
    if rationale:
        row["rationale"] = rationale
    if tags:
        row["tags"] = tags
    return row


def build_transactions() -> list[dict]:
    """Synthetic multi-year ledger (2024–2026): dual-currency cash, FX, retail fees, tags."""
    tx: list[dict] = []
    f = 0.35  # per-leg equity commission (illustrative)

    # --- Funding: staggered wires / transfers (amounts intentionally non-round) ---
    tx.append(
        _usd_dep(
            "2024-01-04",
            248_760.55,
            rationale="海外券商首次匯入（留學結餘＋部分定存解約）",
            tags=["資金", "onboarding"],
        )
    )
    tx.append(
        _usd_dep(
            "2024-01-08",
            312_418.0,
            rationale="年終獎金入帳—拆兩筆降低單日匯率風險",
            tags=["資金", "salary"],
        )
    )
    tx.append(
        _usd_dep(
            "2024-01-11",
            273_921.12,
            rationale="配偶帳戶合併整理後轉入",
            tags=["資金"],
        )
    )
    tx.append(
        _twd_dep(
            "2024-01-05",
            980_000,
            rationale="台股複委託子帳戶—首期配置資金",
            tags=["資金", "TWD"],
        )
    )
    tx.append(
        _twd_dep(
            "2024-01-09",
            1_128_500.0,
            rationale="定存到期轉入（含利息）",
            tags=["資金", "TWD"],
        )
    )
    tx.append(
        _twd_dep(
            "2024-01-12",
            1_095_200.0,
            rationale="年終獎金新台幣部分",
            tags=["資金", "TWD", "salary"],
        )
    )

    # --- 2024: core book (prices are stylized but order-of-magnitude plausible) ---
    tx.append(
        _buy(
            "2024-01-16",
            "QQQ",
            120,
            427.63,
            LT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="先用大盤 ETF 建立核心，避免一開始選股過度集中",
            tags=["core", "ETF"],
        )
    )
    tx.append(
        _buy(
            "2024-01-19",
            "MSFT",
            80,
            377.42,
            LT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="雲＋企業軟體現金流可預測，當核心科技倉",
            tags=["core", "quality"],
        )
    )
    tx.append(
        _buy(
            "2024-01-26",
            "NVDA",
            140,
            56.12,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="AI 資本循環受惠，部位放在中期桶—接受波動",
            tags=["AI", "semi"],
        )
    )
    tx.append(
        _buy(
            "2024-02-02",
            "AMD",
            160,
            147.88,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="資料中心 CPU／GPU 交替敘事，與 NVDA 同主題但較高 beta",
            tags=["semi", "satellite"],
        )
    )
    tx.append(_div("2024-02-06", "MSFT", 136.4, rationale="現金股利入帳", tags=["dividend"]))
    tx.append(
        _buy(
            "2024-02-14",
            "2330.TW",
            500,
            718.5,
            LT,
            "TW",
            "TWD",
            "TWD",
            fees=0.0,
            rationale="台積長期產能／製程領先，用台幣子帳直接買進",
            tags=["core", "TW"],
        )
    )
    tx.append(
        _buy(
            "2024-02-21",
            "GOOGL",
            70,
            140.85,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="搜尋＋雲＋資本配置紀律，估值相對同業中庸",
            tags=["mega-cap"],
        )
    )
    tx.append(
        _sell(
            "2024-03-05",
            "NVDA",
            45,
            88.2,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="第一波獲利了結—降槓桿式集中，保留多數部位續抱",
            tags=["trim", "discipline"],
        )
    )
    tx.append(
        _buy(
            "2024-03-18",
            "BTC",
            1.2,
            67240.0,
            MT,
            "crypto",
            "USD",
            "USD",
            fees=2.99,
            rationale="小部位非相關資產，上限嚴格，不當主倉位",
            tags=["crypto", "satellite"],
        )
    )
    tx.append(
        _buy(
            "2024-04-02",
            "QQQ",
            50,
            435.9,
            LT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="拉回時加碼核心 beta",
            tags=["core", "DCA"],
        )
    )
    tx.append(
        _sell(
            "2024-04-16",
            "QQQ",
            30,
            447.75,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="稅前獲利了結一小段，調整現金比例",
            tags=["rebalance"],
        )
    )
    tx.append(_div("2024-04-22", "QQQ", 208.33, rationale="ETF 配息", tags=["dividend", "ETF"]))
    tx.append(
        _buy(
            "2024-05-03",
            "MSFT",
            50,
            407.65,
            LT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="財報後拉回加碼長期桶",
            tags=["core", "DCA"],
        )
    )
    tx.append(
        _buy(
            "2024-05-20",
            "NVDA",
            60,
            95.05,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="短線修正後補回衛星部位",
            tags=["AI", "DCA"],
        )
    )
    tx.append(
        _sell(
            "2024-06-07",
            "AMD",
            70,
            151.6,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="題材過熱、先降半導體衛星曝險",
            tags=["trim", "semi"],
        )
    )
    tx.append(
        _fx_convert(
            "2024-06-14",
            usd_out=8_420.0,
            twd_in=264_788.0,
            rate=31.4477,
            rationale="台股加碼前換匯—比單次大額匯出略分散",
            tags=["FX", "TWD"],
        )
    )
    tx.append(
        _buy(
            "2024-06-18",
            "2330.TW",
            350,
            867.5,
            LT,
            "TW",
            "TWD",
            "TWD",
            fees=0.0,
            rationale="除息前後波動承接，仍屬長期製程紅利",
            tags=["TW", "DCA"],
        )
    )
    tx.append(
        _div(
            "2024-07-08",
            "2330.TW",
            182_500.0,
            ccy="TWD",
            market="TW",
            rationale="2023 下半年現金股利發放（示範金額）",
            tags=["dividend", "TW"],
        )
    )
    tx.append(
        _buy(
            "2024-07-01",
            "GOOGL",
            40,
            167.55,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="Split 後流動性佳，分批建立中期倉",
            tags=["mega-cap", "DCA"],
        )
    )
    tx.append(
        _withdraw(
            "2024-07-15",
            55_000,
            rationale="大型醫療自費＋家庭現金池補強",
            tags=["life", "withdraw"],
        )
    )
    tx.append(
        _usd_dep(
            "2024-07-22",
            180_000,
            rationale="年中獎金與專案分紅",
            tags=["資金", "salary"],
        )
    )
    tx.append(
        _buy(
            "2024-08-01",
            "SMR",
            600,
            7.82,
            ST,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="小型模組化反應爐題材—嚴格放在短線桶，停損預先想好",
            tags=["speculation", "nuclear"],
        )
    )
    tx.append(
        _buy(
            "2024-08-20",
            "BTC",
            0.9,
            69750.0,
            MT,
            "crypto",
            "USD",
            "USD",
            fees=2.49,
            rationale="波動下降後小額加碼（仍遠低於股票核心）",
            tags=["crypto"],
        )
    )
    tx.append(
        _sell(
            "2024-09-03",
            "GOOGL",
            35,
            161.9,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="調整 mega-cap 集中度，轉現金觀望其他標的",
            tags=["trim"],
        )
    )
    tx.append(
        _buy(
            "2024-09-16",
            "AMD",
            100,
            157.4,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="拉回後重新進場，部位小於先前高峰",
            tags=["semi", "swing"],
        )
    )
    tx.append(_div("2024-09-30", "MSFT", 93.15, rationale="季度股利", tags=["dividend"]))
    tx.append(
        _buy(
            "2024-10-10",
            "NVDA",
            40,
            131.85,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="Blackwell 敘事前的部位微調",
            tags=["AI"],
        )
    )
    tx.append(
        _sell(
            "2024-10-28",
            "SMR",
            250,
            9.38,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="題材股第一波出場—遵守短線桶紀律",
            tags=["trim", "speculation"],
        )
    )
    tx.append(
        _buy(
            "2024-11-05",
            "QQQ",
            35,
            487.9,
            LT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="大選後波動加碼核心 beta",
            tags=["core", "event"],
        )
    )
    tx.append(
        _buy(
            "2024-12-02",
            "MSFT",
            25,
            417.3,
            LT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="年底再平衡—略增現金流標的",
            tags=["core", "year-end"],
        )
    )
    tx.append(_div("2024-12-15", "AMD", 17.5, rationale="持股配息（稅後示範）", tags=["dividend"]))

    # --- 2025 ---
    tx.append(
        _buy(
            "2025-01-08",
            "GOOGL",
            55,
            187.65,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="年初資金回流 mega-cap",
            tags=["mega-cap"],
        )
    )
    tx.append(
        _sell(
            "2025-01-20",
            "MSFT",
            40,
            433.8,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="獲利調節—MSFT 佔比過高，先降一段",
            tags=["trim", "risk"],
        )
    )
    tx.append(
        _buy(
            "2025-02-03",
            "SMR",
            450,
            14.18,
            ST,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="短線第二波（仍小部位）",
            tags=["speculation"],
        )
    )
    tx.append(
        _sell(
            "2025-02-18",
            "NVDA",
            55,
            137.9,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="波動過大先降曝險，長線多頭結構未否定",
            tags=["trim", "risk"],
        )
    )
    tx.append(
        _buy(
            "2025-03-01",
            "BTC",
            0.55,
            84180.0,
            MT,
            "crypto",
            "USD",
            "USD",
            fees=1.99,
            rationale="現金略多，小額配置非相關",
            tags=["crypto"],
        )
    )
    tx.append(
        _fx_convert(
            "2025-03-10",
            usd_out=11_200.0,
            twd_in=347_872.0,
            rate=31.06,
            rationale="台股加碼前先換台幣",
            tags=["FX", "TWD"],
        )
    )
    tx.append(
        _buy(
            "2025-03-14",
            "2330.TW",
            220,
            941.5,
            LT,
            "TW",
            "TWD",
            "TWD",
            fees=0.0,
            rationale="外資買超段拉回承接",
            tags=["TW", "DCA"],
        )
    )
    tx.append(_div("2025-03-28", "QQQ", 163.88, rationale="ETF 季配", tags=["dividend"]))
    tx.append(
        _buy(
            "2025-04-08",
            "AMD",
            120,
            143.55,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="關稅恐慌殺錯價？小試中期桶",
            tags=["semi", "contrarian"],
        )
    )
    tx.append(
        _sell(
            "2025-04-22",
            "BTC",
            0.35,
            71180.0,
            "crypto",
            "USD",
            "USD",
            fees=1.49,
            rationale="加密資產波動—先鎖利降低衛星比重",
            tags=["trim", "crypto"],
        )
    )
    tx.append(
        _usd_dep(
            "2025-05-01",
            260_000,
            rationale="專案尾款入帳",
            tags=["資金", "contract"],
        )
    )
    tx.append(
        _buy(
            "2025-05-12",
            "NVDA",
            35,
            113.9,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="修正後補回 AI 龍頭曝險",
            tags=["AI", "DCA"],
        )
    )
    tx.append(
        _sell(
            "2025-06-01",
            "QQQ",
            25,
            501.4,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="現金比率過低—賣出一小段 ETF",
            tags=["rebalance"],
        )
    )
    tx.append(
        _buy(
            "2025-06-20",
            "MSFT",
            30,
            439.25,
            LT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="Copilot 定價與 Azure 能見度改善後加碼",
            tags=["core", "cloud"],
        )
    )
    tx.append(
        _buy(
            "2025-07-08",
            "SMR",
            320,
            17.55,
            ST,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="短線動能再起—仍嚴守衛星上限",
            tags=["speculation"],
        )
    )
    tx.append(
        _sell(
            "2025-07-25",
            "AMD",
            90,
            167.8,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="半導體 beta 過高，先實現部分獲利",
            tags=["trim"],
        )
    )
    tx.append(_div("2025-08-05", "MSFT", 122.4, rationale="季度股利", tags=["dividend"]))
    tx.append(
        _buy(
            "2025-08-18",
            "GOOGL",
            30,
            163.9,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="估值回落後小額加碼",
            tags=["mega-cap", "DCA"],
        )
    )
    tx.append(
        _buy(
            "2025-09-02",
            "BTC",
            0.4,
            91480.0,
            MT,
            "crypto",
            "USD",
            "USD",
            fees=1.99,
            rationale="現金池偏高，加密維持低個位數占比",
            tags=["crypto"],
        )
    )
    tx.append(
        _sell(
            "2025-09-16",
            "SMR",
            400,
            16.75,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="題材熄火跡象—清掉大部分短線倉",
            tags=["trim", "discipline"],
        )
    )
    tx.append(
        _buy(
            "2025-10-01",
            "QQQ",
            40,
            511.6,
            LT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="季線附近加碼核心",
            tags=["core"],
        )
    )
    tx.append(
        _buy(
            "2025-11-04",
            "NVDA",
            25,
            191.85,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="財報後若拉回再加碼—此為預先小額掛單成交",
            tags=["AI"],
        )
    )
    tx.append(
        _sell(
            "2025-11-22",
            "GOOGL",
            40,
            177.95,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="調節 mega-cap 重疊（與 MSFT／NVDA 同因子）",
            tags=["trim", "factor"],
        )
    )
    tx.append(
        _buy(
            "2025-12-08",
            "AMD",
            80,
            121.65,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="年底作帳行情／評價修復博弈，小部位",
            tags=["semi", "swing"],
        )
    )
    tx.append(
        _div(
            "2025-12-18",
            "2330.TW",
            96_800.0,
            ccy="TWD",
            market="TW",
            rationale="現金股利（示範）—再投入台股長線",
            tags=["dividend", "TW"],
        )
    )

    # --- 2026 YTD ---
    tx.append(
        _buy(
            "2026-01-06",
            "MSFT",
            18,
            427.9,
            LT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="新年度再平衡—略增核心品質股",
            tags=["core", "year-open"],
        )
    )
    tx.append(
        _sell(
            "2026-01-24",
            "BTC",
            0.5,
            101850.0,
            "crypto",
            "USD",
            "USD",
            fees=2.25,
            rationale="加密衛星達標獲利—降回目標權重",
            tags=["trim", "crypto"],
        )
    )
    tx.append(
        _buy(
            "2026-02-03",
            "SMR",
            280,
            21.35,
            ST,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="波動交易—僅短線桶，與長線 thesis 分開",
            tags=["speculation"],
        )
    )
    tx.append(_div("2026-02-14", "MSFT", 86.2, rationale="股利入帳", tags=["dividend"]))
    tx.append(
        _fx_convert(
            "2026-02-24",
            usd_out=6_800.0,
            twd_in=214_080.0,
            rate=31.48235,
            rationale="台股加碼換匯",
            tags=["FX", "TWD"],
        )
    )
    tx.append(
        _buy(
            "2026-03-03",
            "2330.TW",
            150,
            987.0,
            LT,
            "TW",
            "TWD",
            "TWD",
            fees=0.0,
            rationale="長線持有不猜高點—僅機械式加碼",
            tags=["TW", "DCA"],
        )
    )
    tx.append(
        _sell(
            "2026-03-18",
            "NVDA",
            30,
            117.6,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="評價與情緒過熱—減碼但保留主倉",
            tags=["trim", "valuation"],
        )
    )
    tx.append(
        _buy(
            "2026-04-01",
            "GOOGL",
            25,
            153.85,
            MT,
            "US",
            "USD",
            "USD",
            fees=f,
            rationale="關稅／反壟斷雜音下分批接",
            tags=["mega-cap"],
        )
    )
    tx.sort(key=lambda r: r["date"])
    return tx


def _validate_replay(txns: list[dict]) -> None:
    sys.path.insert(0, str(SCRIPTS))
    from transactions import _dict_to_transaction, replay  # noqa: WPS433

    parsed = [_dict_to_transaction(d, seq=i) for i, d in enumerate(txns)]
    st = replay(parsed)
    for iss in st.issues:
        raise SystemExit(f"replay issue: {iss}")
    for ccy, bal in st.cash.items():
        if bal < -1e-2:
            raise SystemExit(f"negative cash {ccy}: {bal}")


def _apply_db() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    subprocess.check_call(
        [sys.executable, str(SCRIPTS / "transactions.py"), "db", "init", "--db", str(DB_PATH)],
        cwd=str(REPO),
    )
    subprocess.check_call(
        [
            sys.executable,
            str(SCRIPTS / "transactions.py"),
            "db",
            "import-json",
            "--input",
            str(JSON_PATH),
            "--db",
            str(DB_PATH),
        ],
        cwd=str(REPO),
    )
    subprocess.check_call(
        [sys.executable, str(SCRIPTS / "transactions.py"), "verify", "--db", str(DB_PATH)],
        cwd=str(REPO),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-json", action="store_true", help=f"Write {JSON_PATH.name}")
    ap.add_argument("--apply", action="store_true", help="Recreate demo DB from JSON")
    args = ap.parse_args()
    txns = build_transactions()
    _validate_replay(txns)

    if args.write_json or not JSON_PATH.exists():
        DEMO.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json.dumps(txns, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {JSON_PATH} ({len(txns)} txns)")

    if args.apply:
        if not JSON_PATH.exists():
            print("ERROR: run with --write-json first", file=sys.stderr)
            return 2
        _apply_db()
        print(f"Materialized {DB_PATH}")

    if not args.write_json and not args.apply:
        ap.print_help()
        print("\nTip: use --write-json and/or --apply")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
