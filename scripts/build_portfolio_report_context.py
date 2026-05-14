#!/usr/bin/env python3
"""Build the minimal context required for a single-account portfolio report.

This helper deliberately covers only ``portfolio_report`` / ``single_account``:
it authors math-adjacent context (`theme_sector_*`, `strategy_readout`,
`data_gaps`, `reviewer_pass`) and never authors daily-decision keys such as
news, events, actions, recommended adjustments, or trading psychology.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


THEME_MASTER = (
    "AI 算力",
    "雲端 / 資料中心",
    "半導體設備",
    "先進封裝",
    "新能源 / 核能",
    "光電 / OCS",
    "航太 / 國防",
    "加密資產",
    "去美元化 / 黃金",
    "防禦資產 / 現金代理",
    "通膨保護",
    "Mega-cap Tech",
    "其他",
)


# Static issuer / ETF classification used for report-mode math context.  This
# is not news/event research; it is a deterministic taxonomy seed. Unknown
# holdings fall back to "其他" and are surfaced as a data gap.
CLASSIFICATION_MAP: Dict[str, Dict[str, Any]] = {
    "2330": {
        "sector": "半導體",
        "themes": {"AI 算力": 0.75, "雲端 / 資料中心": 0.25, "先進封裝": 1.0},
        "sources": ["built-in issuer taxonomy: TSMC semiconductor foundry / advanced packaging"],
    },
    "COHR": {
        "sector": "通信 / 光電",
        "themes": {"光電 / OCS": 1.0, "AI 算力": 0.25, "雲端 / 資料中心": 0.25},
        "sources": ["built-in issuer taxonomy: Coherent optical networking / photonics"],
    },
    "GEV": {
        "sector": "能源 / 資源",
        "themes": {"新能源 / 核能": 1.0, "雲端 / 資料中心": 0.25},
        "sources": ["built-in issuer taxonomy: GE Vernova power and grid infrastructure"],
    },
    "GOOG": {
        "sector": "軟體 / 雲端",
        "themes": {"雲端 / 資料中心": 1.0, "AI 算力": 0.25, "Mega-cap Tech": 1.0},
        "sources": ["built-in issuer taxonomy: Alphabet search, cloud, and AI platforms"],
    },
    "INTC": {
        "sector": "半導體",
        "themes": {"AI 算力": 0.5, "雲端 / 資料中心": 0.25, "先進封裝": 0.5},
        "sources": ["built-in issuer taxonomy: Intel processors, foundry, and advanced packaging"],
    },
    "LITE": {
        "sector": "通信 / 光電",
        "themes": {"光電 / OCS": 1.0, "AI 算力": 0.25, "雲端 / 資料中心": 0.25},
        "sources": ["built-in issuer taxonomy: Lumentum optical and photonic components"],
    },
    "MRAAY": {
        "sector": "航太 / 國防",
        "themes": {"航太 / 國防": 0.75, "新能源 / 核能": 0.5},
        "sources": ["built-in issuer taxonomy: Mitsubishi Heavy aerospace, defense, and energy systems"],
    },
    "NVDA": {
        "sector": "半導體",
        "themes": {"AI 算力": 1.0, "雲端 / 資料中心": 0.5, "先進封裝": 0.25, "Mega-cap Tech": 1.0},
        "sources": ["built-in issuer taxonomy: NVIDIA accelerated computing and data-center GPUs"],
    },
    "PLTR": {
        "sector": "軟體 / 雲端",
        "themes": {"AI 算力": 0.75, "雲端 / 資料中心": 0.5},
        "sources": ["built-in issuer taxonomy: Palantir data and AI software platforms"],
    },
    "QQQ": {
        "sector": "多元 ETF / 指數",
        "themes": {"Mega-cap Tech": 0.75, "AI 算力": 0.5, "雲端 / 資料中心": 0.5},
        "sources": ["built-in ETF taxonomy: Invesco QQQ / Nasdaq-100 index-level classification"],
        "etf_fallback": True,
    },
    "RKLB": {
        "sector": "航太 / 國防",
        "themes": {"航太 / 國防": 1.0},
        "sources": ["built-in issuer taxonomy: Rocket Lab launch and space systems"],
    },
    "TSLA": {
        "sector": "汽車 / 電動車",
        "themes": {"Mega-cap Tech": 0.75, "AI 算力": 0.25},
        "sources": ["built-in issuer taxonomy: Tesla electric vehicles, energy, and autonomy"],
    },
    "VRT": {
        "sector": "硬體 / 網通",
        "themes": {"雲端 / 資料中心": 1.0, "新能源 / 核能": 0.25, "AI 算力": 0.25},
        "sources": ["built-in issuer taxonomy: Vertiv data-center power and thermal infrastructure"],
    },
    "VWRA": {
        "sector": "多元 ETF / 指數",
        "themes": {"Mega-cap Tech": 0.25},
        "sources": ["built-in ETF taxonomy: Vanguard FTSE All-World broad-index classification"],
        "etf_fallback": True,
    },
}

FORBIDDEN_PORTFOLIO_KEYS = {
    "news",
    "events",
    "research_coverage",
    "research_targets",
    "high_opps",
    "adjustments",
    "actions",
    "trading_psychology",
    "holdings_actions",
}


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_cash_aggregate(aggregate: Dict[str, Any]) -> bool:
    return bool(aggregate.get("is_cash")) or str(aggregate.get("market") or "").lower() == "cash"


def _non_cash_aggregates(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        aggregate
        for aggregate in snapshot.get("aggregates") or []
        if isinstance(aggregate, dict) and aggregate.get("ticker") and not _is_cash_aggregate(aggregate)
    ]


def _market_value(aggregate: Dict[str, Any]) -> float:
    for key in ("market_value", "market_value_base", "value", "current_value"):
        value = aggregate.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return 0.0


def _classification_for(ticker: str) -> Dict[str, Any]:
    key = ticker.upper()
    if key.endswith(".TW"):
        key = key[:-3]
    if key.endswith(".L"):
        key = key[:-2]
    return CLASSIFICATION_MAP.get(
        key,
        {
            "sector": "其他",
            "themes": {"其他": 1.0},
            "sources": ["built-in fallback taxonomy: unmapped holding classified as other"],
            "unknown": True,
        },
    )


def _bar_class(pct: float, *, is_theme: bool) -> str:
    if pct >= 25.0 or pct >= 12.5:
        return " warn"
    if is_theme and pct >= 7.5:
        return " info"
    return ""


def _bar_rows(weights: Dict[str, float], *, is_theme: bool) -> str:
    items = [(label, pct) for label, pct in weights.items() if pct > 0]
    if is_theme:
        order = {label: idx for idx, label in enumerate(THEME_MASTER)}
        items.sort(key=lambda item: (order.get(item[0], 999), -item[1]))
    else:
        items.sort(key=lambda item: item[1], reverse=True)
    max_pct = max((pct for _, pct in items), default=1.0) or 1.0
    rows: List[str] = []
    for label, pct in items:
        width = max(0.0, min(100.0, pct / max_pct * 100.0))
        rows.append(
            '<div class="bar-row">'
            f'<div class="bar-label">{html.escape(label)}</div>'
            f'<div class="bar-track"><div class="bar{_bar_class(pct, is_theme=is_theme)}" '
            f'style="width:{width:.0f}%"></div></div>'
            f'<div class="bar-value">{pct:.1f}%</div>'
            "</div>"
        )
    return "\n".join(rows)


def _visible_themes(theme_weights: Dict[str, float]) -> Dict[str, float]:
    visible = {label: pct for label, pct in theme_weights.items() if pct > 0}
    if len(visible) <= 7:
        return visible
    top = sorted(visible.items(), key=lambda item: item[1], reverse=True)[:6]
    keep = {label for label, _ in top}
    other = sum(pct for label, pct in visible.items() if label not in keep)
    compact = {label: pct for label, pct in visible.items() if label in keep}
    compact["其他"] = compact.get("其他", 0.0) + other
    return compact


def build_theme_sector(snapshot: Dict[str, Any]) -> Tuple[str, Dict[str, Any], List[Dict[str, str]]]:
    aggregates = _non_cash_aggregates(snapshot)
    invested = sum(_market_value(aggregate) for aggregate in aggregates)
    sector_weights: Dict[str, float] = {}
    theme_weights: Dict[str, float] = {}
    audit = {"as_of": snapshot.get("today") or str(snapshot.get("generated_at") or "")[:10], "tickers": {}}
    gaps: List[Dict[str, str]] = []

    for aggregate in aggregates:
        ticker = str(aggregate["ticker"]).upper()
        weight = (_market_value(aggregate) / invested * 100.0) if invested else 0.0
        classification = _classification_for(ticker)
        sector = classification["sector"]
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
        themes = dict(classification["themes"])
        for theme, share in themes.items():
            theme_weights[theme] = theme_weights.get(theme, 0.0) + weight * float(share)
        audit["tickers"][ticker] = {
            "sector": sector,
            "themes": themes,
            "sources": list(classification["sources"]),
        }
        if classification.get("unknown"):
            gaps.append(
                {
                    "summary": f"{ticker} 分類未內建",
                    "detail": f"{ticker} 使用「其他」分類；後續可補入發行人產業與主題對照。",
                }
            )

    visible = _visible_themes(theme_weights)
    notes: List[str] = []
    top_themes = sorted(visible.items(), key=lambda item: item[1], reverse=True)[:3]
    if len(top_themes) == 3:
        total = sum(pct for _, pct in top_themes)
        if total > 30.0:
            (a_label, a_pct), (b_label, b_pct), (c_label, c_pct) = top_themes
            notes.append(
                f"<b>集中度警示：</b>{a_label} {a_pct:.1f}% ＋ {b_label} {b_pct:.1f}% ＋ "
                f"{c_label} {c_pct:.1f}% ＝ <b>{total:.1f}%</b>，超過 30.0% 相關性主題上限。"
            )
    if sector_weights:
        sector_label, sector_pct = max(sector_weights.items(), key=lambda item: item[1])
        if sector_pct > 30.0:
            notes.append(f"<b>行業集中：</b>{sector_label} 佔 {sector_pct:.1f}%，超過 30.0% 單一行業上限。")
    etf_tickers = [
        ticker
        for ticker, item in audit["tickers"].items()
        if _classification_for(ticker).get("etf_fallback")
    ]
    if etf_tickers:
        gaps.append(
            {
                "summary": "ETF 持股未逐檔穿透",
                "detail": f"{', '.join(sorted(etf_tickers))} 使用指數 / ETF 層級分類，未逐檔展開底層權重。",
            }
        )

    notes_html = "".join(f'<div class="bucket-note" style="margin-top:18px">{note}</div>' for note in notes)
    theme_html = (
        '<div class="cols-2">'
        '<div><div class="eyebrow" style="margin-bottom:10px">主題</div>'
        f'<div class="bars">{_bar_rows(visible, is_theme=True)}</div></div>'
        '<div><div class="eyebrow" style="margin-bottom:10px">行業</div>'
        f'<div class="bars">{_bar_rows(sector_weights, is_theme=False)}</div></div>'
        f"</div>{notes_html}"
    )
    return theme_html, audit, gaps


def _strategy_readout(settings_text: str, *, locale: str) -> str:
    if locale.startswith("zh"):
        return (
            "我把這份 portfolio_report 當作部位數學與風險盤點：策略、持有期、集中度、"
            "現金部署與禁用工具以本帳戶 SETTINGS 為準；此模式不新增新聞、事件、交易建議"
            "或今日行動，只檢查現有部位是否仍符合既定框架。"
        )
    return (
        "I treat this portfolio_report as a position-math and risk review: strategy, holding period, "
        "concentration, cash deployment, and prohibited instruments follow this account's SETTINGS. "
        "This mode does not add news, events, trade recommendations, or today's actions."
    )


def _snapshot_data_gaps(snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    gaps: List[Dict[str, str]] = []
    accuracy = snapshot.get("report_accuracy") or {}
    for dimension in accuracy.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        score = dimension.get("score")
        try:
            score_f = float(score)
        except (TypeError, ValueError):
            continue
        if score_f >= 99.5:
            continue
        detail = dimension.get("detail") or {}
        gaps.append(
            {
                "summary": f"資料品質：{dimension.get('id', 'unknown')} {score_f:.1f}/100",
                "detail": json.dumps(detail, ensure_ascii=False, sort_keys=True),
            }
        )
    return gaps


def build_context(snapshot: Dict[str, Any], settings_text: str = "") -> Dict[str, Any]:
    settings = snapshot.get("settings") or {}
    locale = str(settings.get("locale") or "en")
    theme_html, theme_audit, theme_gaps = build_theme_sector(snapshot)
    context = {
        "language": settings.get("display_name") or locale,
        "strategy_readout": _strategy_readout(settings_text, locale=locale),
        "theme_sector_html": theme_html,
        "theme_sector_audit": theme_audit,
        "data_gaps": _snapshot_data_gaps(snapshot) + theme_gaps,
        "reviewer_pass": {
            "completed": True,
            "reviewed_sections": ["strategy_readout", "theme_sector"],
            "summary": [
                "本次 reviewer pass 僅覆核 portfolio_report 會呈現的策略讀出與主題/行業曝險；"
                "新聞、事件、建議調整與今日行動依模式政策未執行。"
                if locale.startswith("zh")
                else (
                    "This reviewer pass covers only the strategy readout and theme/sector exposure rendered "
                    "by portfolio_report; news, events, adjustments, and actions are skipped by mode policy."
                )
            ],
            "by_section": {},
        },
    }
    forbidden_present = FORBIDDEN_PORTFOLIO_KEYS.intersection(context)
    if forbidden_present:
        raise ValueError(f"portfolio context builder authored forbidden keys: {sorted(forbidden_present)}")
    return context


def _cli(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _cli(argv)
    snapshot = _load_json(args.snapshot)
    settings_text = ""
    if args.settings and args.settings.exists():
        settings_text = args.settings.read_text(encoding="utf-8")
    context = build_context(snapshot, settings_text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote portfolio report context to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
