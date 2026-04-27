#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_report.py — Portfolio HTML report renderer template.

Implements the structural and visual contract of `docs/portfolio_report_agent_guidelines.md`:

  §10  — 11 HTML sections in order, plus High-priority alerts banner
  §13  — Symbol & Price popovers
  §14  — Visual design standard (tokens, typography, RWA, anti-patterns)

The script is **deterministic for the structural / numeric parts** (totals, weights, P&L,
holding period, period-strip buckets, fallbacks) and **agent-driven for the editorial
parts** (today's verdict, news prose, action list, recommended adjustments).
Editorial content comes from a JSON context file the agent prepares per-run.

USAGE
-----
    python scripts/generate_report.py \
        --holdings HOLDINGS.md \
        --settings SETTINGS.md \
        --prices prices.json \
        --context report_context.json \
        --output reports/2026-04-28_1330_portfolio_report.html

The CSS / layout chrome is read from `reports/_sample_redesign.html` (the canonical
visual reference per §14.9). To change the look, edit that file — never duplicate the
styles here.

CONTEXT FILE SHAPE  (report_context.json)
-----------------------------------------
    {
      "language":      "繁體中文",
      "title":         "投資組合健康檢查 · 2026-04-28",
      "subtitle":      "...",
      "fx":            {"USD/TWD": 30.0},
      "next_event":    "01-03 央行決議",
      "today_summary": ["paragraph 1", "paragraph 2"],
      "alerts":        ["bullet 1", "bullet 2"],
      "news":          [{"ticker": "DELT", "date": "2026-04-27", "headline": "...",
                          "url": "...", "source": "Reuters", "impact": "neg"}, ...],
      "events":        [{"date": "01-08", "topic": "DELT", "event": "本季財報",
                          "impact_label": "高", "impact_class": "warn", "watch": "..."},
                         ...],
      "high_opps":     [{"ticker": "ZETA", "why": "...", "trigger": "260 突破加碼"}, ...],
      "adjustments":   [{"ticker": "KAPA", "current_pct": 4.5, "action": "trim",
                          "action_label": "減碼 20%", "why": "...", "trigger": "..."},
                         ...],
      "actions":       {"must_do": ["..."], "may_do": ["..."],
                         "avoid": ["..."],  "need_data": ["..."]},
      "data_gaps":     [{"summary": "ALPH 成本基礎缺失",
                          "detail": "<HOLDINGS.md → Long Term> 內 ALPH 1 @ ? on ..."}, ...],
      "spec_update_note": "..."
    }

Every field is optional; missing fields render as `n/a` per §9.6 with no guesses.

The "Sources & data gaps" audit table is built mechanically from `prices.json` —
the agent does not need to author it.

DEPENDENCIES
------------
    Python 3.10+. No external packages required. (yfinance is only used by
    `fetch_prices.py`; the renderer reads its JSON output.)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Reuse the parser + market routing from the sister script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_prices import (                                    # noqa: E402
    Lot,
    MarketType,
    parse_holdings,
)


# ----------------------------------------------------------------------------- #
# Defaults — mirror SETTINGS.example.md "Position sizing rails" so warnings fire.
# ----------------------------------------------------------------------------- #

DEFAULTS = {
    "single_name_weight_warn_pct": 15.0,    # §11 special check #1
    "theme_concentration_warn_pct": 25.0,   # §11 #2
    "high_vol_bucket_warn_pct": 30.0,       # §11 #3
    "single_day_move_alert_pct": 8.0,       # §10.6 alert #4
    "earnings_within_days": 7,              # §10.6 alert #5
    "earnings_weight_pct": 5.0,             # §10.6 alert #5
    "above_target_pct": 20.0,               # §10.6 alert #7
}


# ----------------------------------------------------------------------------- #
# CSS extraction from the canonical sample (§14.9)
# ----------------------------------------------------------------------------- #

_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)


def load_canonical_css(sample_path: Path) -> str:
    """Read the <style>...</style> block from `reports/_sample_redesign.html`."""
    if not sample_path.exists():
        raise FileNotFoundError(
            f"Canonical sample not found at {sample_path}. The sample is the "
            "single source of styles per §14.9 — restore it before generating reports."
        )
    text = sample_path.read_text(encoding="utf-8")
    m = _STYLE_RE.search(text)
    if not m:
        raise ValueError(f"No <style> block found in {sample_path}")
    return m.group(1)


# ----------------------------------------------------------------------------- #
# Metrics
# ----------------------------------------------------------------------------- #

@dataclass
class TickerAggregate:
    """Per-ticker rollup used by the holdings table and the popovers."""
    ticker: str
    market: MarketType
    bucket: str                       # representative bucket (highest seniority)
    total_qty: float
    weighted_avg_cost: Optional[float]      # None if all lots have ? cost
    total_cost_known: float                 # sum of cost*qty over lots with known cost
    earliest_date: Optional[str]            # for hold period
    lots: List[Lot] = field(default_factory=list)

    # Filled in after price merge
    latest_price: Optional[float] = None
    move_pct: Optional[float] = None
    market_value: Optional[float] = None
    pnl_amount: Optional[float] = None
    pnl_pct: Optional[float] = None
    is_cash: bool = False


@dataclass
class BookPacing:
    """§9.5 book-wide aggregates for the Holding period & pacing block."""
    avg_hold_years: Optional[float]
    oldest: Optional[Tuple[str, str, str]]    # (ticker, date, duration_label)
    newest: Optional[Tuple[str, str, str]]
    pct_held_over_1y: Optional[float]
    distribution_pct: Dict[str, float]        # buckets: <1m, 1-6m, 6-12m, 1-3y, 3y+


def _bucket_priority(name: str) -> int:
    order = {"long term": 0, "mid term": 1, "short term": 2, "cash holdings": 99}
    for k, v in order.items():
        if name.lower().startswith(k):
            return v
    return 50


def aggregate(lots: List[Lot]) -> Dict[str, TickerAggregate]:
    """One row per distinct ticker, picking the most senior bucket if a ticker spans multiple."""
    buckets: Dict[str, TickerAggregate] = {}
    for lot in lots:
        agg = buckets.get(lot.ticker)
        is_cash = lot.market == MarketType.CASH or _bucket_priority(lot.bucket) == 99
        if agg is None:
            agg = TickerAggregate(
                ticker=lot.ticker,
                market=lot.market,
                bucket=lot.bucket,
                total_qty=0.0,
                weighted_avg_cost=None,
                total_cost_known=0.0,
                earliest_date=None,
                is_cash=is_cash,
            )
            buckets[lot.ticker] = agg
        # Promote bucket if a more senior one shows up
        if _bucket_priority(lot.bucket) < _bucket_priority(agg.bucket):
            agg.bucket = lot.bucket

        agg.lots.append(lot)
        agg.total_qty += lot.quantity
        if lot.cost is not None:
            agg.total_cost_known += lot.cost * lot.quantity
        if lot.date:
            if agg.earliest_date is None or lot.date < agg.earliest_date:
                agg.earliest_date = lot.date

    # Compute weighted average cost over lots with known cost only
    for agg in buckets.values():
        known_qty = sum(l.quantity for l in agg.lots if l.cost is not None)
        if known_qty > 0:
            agg.weighted_avg_cost = agg.total_cost_known / known_qty
    return buckets


def merge_prices(aggs: Dict[str, TickerAggregate], prices: Dict[str, Any]) -> None:
    for ticker, agg in aggs.items():
        if agg.is_cash:
            agg.market_value = agg.total_qty           # cash: qty in its own currency
            continue
        pr = prices.get(ticker, {}) or {}
        agg.latest_price = pr.get("latest_price")
        agg.move_pct = pr.get("move_pct")
        if agg.latest_price is not None:
            agg.market_value = agg.latest_price * agg.total_qty
            if agg.weighted_avg_cost not in (None, 0):
                cost_basis = agg.weighted_avg_cost * agg.total_qty
                agg.pnl_amount = agg.market_value - cost_basis
                agg.pnl_pct = (agg.pnl_amount / cost_basis) * 100.0 if cost_basis else None


def hold_period_label(earliest_date: Optional[str], today: _dt.date) -> str:
    if not earliest_date:
        return "n/a"
    try:
        d0 = _dt.date.fromisoformat(earliest_date)
    except ValueError:
        return "n/a"
    days = (today - d0).days
    if days < 0:
        return "n/a"
    if days < 30:
        return f"{days}d"
    months = days // 30
    if months < 12:
        return f"{months}m"
    years = months // 12
    rem = months % 12
    return f"{years}y {rem}m" if rem else f"{years}y"


def book_pacing(aggs: Dict[str, TickerAggregate], today: _dt.date) -> BookPacing:
    """§9.5 — risk-asset only, cost-weighted."""
    buckets = {"<1m": 0.0, "1-6m": 0.0, "6-12m": 0.0, "1-3y": 0.0, "3y+": 0.0}
    risk_value = 0.0
    over_1y_value = 0.0
    weighted_days = 0.0
    cost_total = 0.0
    oldest: Optional[Tuple[str, str, int]] = None
    newest: Optional[Tuple[str, str, int]] = None

    for agg in aggs.values():
        if agg.is_cash or agg.market_value in (None, 0):
            continue
        risk_value += agg.market_value
        for lot in agg.lots:
            if not lot.date or lot.cost is None:
                continue
            try:
                d0 = _dt.date.fromisoformat(lot.date)
            except ValueError:
                continue
            days = (today - d0).days
            cost = lot.cost * lot.quantity
            cost_total += cost
            weighted_days += cost * days
            if days >= 365:
                over_1y_value += (agg.market_value or 0) * (lot.quantity / agg.total_qty)
            if oldest is None or days > oldest[2]:
                oldest = (agg.ticker, lot.date, days)
            if newest is None or days < newest[2]:
                newest = (agg.ticker, lot.date, days)

            # Distribution by hold period (value-weighted using lot share of agg market value)
            value_share = (agg.market_value or 0) * (lot.quantity / agg.total_qty)
            if days < 30:
                buckets["<1m"] += value_share
            elif days < 180:
                buckets["1-6m"] += value_share
            elif days < 365:
                buckets["6-12m"] += value_share
            elif days < 365 * 3:
                buckets["1-3y"] += value_share
            else:
                buckets["3y+"] += value_share

    if risk_value > 0:
        dist_pct = {k: round(v / risk_value * 100.0, 1) for k, v in buckets.items()}
    else:
        dist_pct = {k: 0.0 for k in buckets}

    avg_years = (weighted_days / cost_total / 365.0) if cost_total > 0 else None
    pct_over_1y = round(over_1y_value / risk_value * 100.0, 1) if risk_value > 0 else None

    def _wrap(node: Optional[Tuple[str, str, int]]) -> Optional[Tuple[str, str, str]]:
        if node is None:
            return None
        ticker, date, days = node
        return (ticker, date, _days_label(days))

    return BookPacing(
        avg_hold_years=round(avg_years, 1) if avg_years is not None else None,
        oldest=_wrap(oldest),
        newest=_wrap(newest),
        pct_held_over_1y=pct_over_1y,
        distribution_pct=dist_pct,
    )


def _days_label(days: int) -> str:
    if days < 30:
        return f"{days}d"
    months = days // 30
    if months < 12:
        return f"{months}m"
    years = months // 12
    rem = months % 12
    return f"{years}y {rem}m" if rem else f"{years}y"


# ----------------------------------------------------------------------------- #
# §11 special checks — runs against the merged data
# ----------------------------------------------------------------------------- #

@dataclass
class CheckResult:
    label: str
    triggered: bool
    detail: str


def special_checks(
    aggs: Dict[str, TickerAggregate],
    total_assets: float,
    config: Dict[str, float],
) -> List[CheckResult]:
    """Returns one CheckResult per §11 item — both passes and triggers."""
    if total_assets <= 0:
        return []
    results: List[CheckResult] = []
    # 1. Single asset > 15%
    for agg in aggs.values():
        if agg.is_cash or agg.market_value is None:
            continue
        weight = agg.market_value / total_assets * 100.0
        if weight > config["single_name_weight_warn_pct"]:
            results.append(CheckResult(
                "Concentration: single asset",
                True,
                f"{agg.ticker} 權重 {weight:.1f}% > {config['single_name_weight_warn_pct']:.0f}%",
            ))
            break
    else:
        results.append(CheckResult("Concentration: single asset", False, "通過 — 無單一標的超過上限"))

    # 6. Recent buying spree — 3+ adds in last 30 days per ticker
    today = _dt.date.today()
    spree: List[str] = []
    for agg in aggs.values():
        recent = [l for l in agg.lots if l.date and (today - _dt.date.fromisoformat(l.date)).days <= 30]
        if len(recent) >= 3:
            spree.append(agg.ticker)
    results.append(CheckResult(
        "Recent buying spree (3+ adds in 30 days)",
        bool(spree),
        ", ".join(spree) if spree else "通過 — 無近期密集加碼",
    ))

    # 8. Bucket misclassification — Short Term lot held > 12 months
    misclassified: List[Tuple[str, str]] = []
    for agg in aggs.values():
        for lot in agg.lots:
            if "short" in lot.bucket.lower() and lot.date:
                try:
                    days = (today - _dt.date.fromisoformat(lot.date)).days
                except ValueError:
                    continue
                if days > 365:
                    misclassified.append((agg.ticker, lot.date))
    results.append(CheckResult(
        "Bucket misclassification (Short Term > 12m)",
        bool(misclassified),
        ", ".join(f"{t} ({d})" for t, d in misclassified) if misclassified else "通過 — 短線桶內無持有 > 12 月之批次",
    ))

    # 9. Averaging up — most recent lot > 1.1× older weighted avg
    averaging_up: List[str] = []
    for agg in aggs.values():
        if len(agg.lots) < 2 or agg.weighted_avg_cost is None:
            continue
        sorted_lots = sorted([l for l in agg.lots if l.date and l.cost is not None], key=lambda l: l.date or "")
        if len(sorted_lots) < 2:
            continue
        older = sorted_lots[:-1]
        latest = sorted_lots[-1]
        older_qty = sum(l.quantity for l in older)
        if older_qty == 0:
            continue
        older_avg = sum(l.cost * l.quantity for l in older) / older_qty
        if latest.cost > older_avg * 1.1:
            averaging_up.append(f"{agg.ticker} (latest {latest.cost:.2f} vs older avg {older_avg:.2f})")
    results.append(CheckResult(
        "Averaging up (latest lot > 1.1× older avg)",
        bool(averaging_up),
        "; ".join(averaging_up) if averaging_up else "通過 — 無加碼追高情形",
    ))

    # 10. Open cost-basis or date gaps
    gaps = [agg.ticker for agg in aggs.values()
            if any(l.cost is None or l.date is None for l in agg.lots)]
    results.append(CheckResult(
        "Open cost-basis / date gaps",
        bool(gaps),
        ", ".join(sorted(set(gaps))) if gaps else "通過 — 所有批次皆有完整成本與日期",
    ))
    return results


# ----------------------------------------------------------------------------- #
# HTML helpers
# ----------------------------------------------------------------------------- #

def _esc(s: Any) -> str:
    return html.escape(str(s) if s is not None else "")


def _fmt_money(value: Optional[float], currency_prefix: str = "$") -> str:
    if value is None:
        return '<span class="na">n/a</span>'
    sign = "−" if value < 0 else ""
    return f"{sign}{currency_prefix}{abs(value):,.0f}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return '<span class="na">n/a</span>'
    return f"{value:+.1f}%"


def _fmt_signed(value: Optional[float], pct: Optional[float]) -> str:
    if value is None:
        return '<span class="na">n/a</span>'
    cls = "pos-txt" if value >= 0 else "neg-txt"
    sign = "+" if value >= 0 else "−"
    pct_str = f" / {sign}{abs(pct):.1f}%" if pct is not None else ""
    return f'<span class="{cls}">{sign}${abs(value):,.0f}{pct_str}</span>'


# ----------------------------------------------------------------------------- #
# Section renderers
#
# Each function returns a string of HTML for its section. Order is preserved by
# the master `render_html` function. Anything the agent must author appears in
# `context`; numeric / structural content comes from `aggs`, `prices`, `config`.
# ----------------------------------------------------------------------------- #

def render_masthead(context: Dict[str, Any]) -> str:
    lang = _esc(context.get("language", "繁體中文"))
    title = _esc(context.get("title", "投資組合健康檢查"))
    subtitle = _esc(context.get("subtitle", ""))
    fx_str = " · ".join(f"{k} {v}" for k, v in (context.get("fx") or {}).items()) or "n/a"
    next_event = _esc(context.get("next_event", "n/a"))
    generated = context.get("generated_at") or _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""\
  <header class="masthead">
    <div class="eyebrow">Portfolio Research Note · {lang}</div>
    <h1>{title}</h1>
    <p class="dek">{subtitle}</p>
    <div class="masthead-meta">
      <span><b>產生時間</b>　{_esc(generated)}</span>
      <span><b>基準匯率</b>　{_esc(fx_str)}</span>
      <span><b>下個事件</b>　{next_event}</span>
    </div>
  </header>"""


def render_alerts(context: Dict[str, Any]) -> str:
    alerts = context.get("alerts") or []
    if not alerts:
        return ""
    items = "\n      ".join(f"<li>{_esc(a)}</li>" for a in alerts)
    return f"""\
  <section class="callout">
    <div class="ctitle"><span class="badge">高優先</span>本日須立即關注</div>
    <ul>
      {items}
    </ul>
  </section>"""


def render_today_summary(context: Dict[str, Any]) -> str:
    paragraphs = context.get("today_summary") or ["（今日總結待補）"]
    cols = ["<div>" + "".join(f"<p>{_esc(p)}</p>" for p in paragraphs[:1]) + "</div>"]
    if len(paragraphs) > 1:
        cols.append("<div>" + "".join(f"<p>{_esc(p)}</p>" for p in paragraphs[1:]) + "</div>")
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>今日總結</h2>
      <span class="sub">總體 × 持股 × 風險</span>
    </div>
    <div class="prose cols-2">{''.join(cols)}</div>
  </section>"""


def render_dashboard(
    aggs: Dict[str, TickerAggregate],
    total_assets: float,
    invested: float,
    cash: float,
    pnl: Optional[float],
) -> str:
    if total_assets <= 0:
        return ""
    invested_pct = invested / total_assets * 100.0
    cash_pct = cash / total_assets * 100.0
    pnl_html = (f'<div class="delta {"pos" if pnl >= 0 else "neg"}">{"+" if pnl >= 0 else "−"}${abs(pnl):,.0f}</div>'
                if pnl is not None else '<div class="delta">n/a</div>')
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>投資組合儀表板</h2>
      <span class="sub">總體 KPI · USD 基準</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="k">總資產</div><div class="v">${total_assets:,.0f}</div><div class="delta">含現金、加密、股票</div></div>
      <div class="kpi"><div class="k">投資部位</div><div class="v">${invested:,.0f}</div><div class="delta">{invested_pct:.1f}% 風險資產</div></div>
      <div class="kpi"><div class="k">現金與類現金</div><div class="v">${cash:,.0f}</div><div class="delta">{cash_pct:.1f}% 防守彈藥</div></div>
      <div class="kpi"><div class="k">已知損益</div><div class="v">{_fmt_money(pnl)}</div>{pnl_html}</div>
    </div>

    <div style="margin-top:22px">
      <div class="cash-bar" aria-label="現金與風險資產比例">
        <span class="seg risk" style="width:{invested_pct:.1f}%"></span>
        <span class="seg cash" style="width:{cash_pct:.1f}%"></span>
      </div>
      <div class="cash-legend">
        <span><i style="background:var(--ink)"></i>風險資產 {invested_pct:.1f}% · ${invested:,.0f}</span>
        <span><i style="background:var(--accent-warm)"></i>現金與類現金 {cash_pct:.1f}% · ${cash:,.0f}</span>
      </div>
    </div>
  </section>"""


def render_holdings_table(
    aggs: Dict[str, TickerAggregate],
    total_assets: float,
    prices: Dict[str, Any],
    today: _dt.date,
) -> str:
    rows: List[str] = []
    sorted_aggs = sorted(aggs.values(), key=lambda a: -(a.market_value or 0))
    for agg in sorted_aggs:
        weight_pct = (agg.market_value / total_assets * 100.0) if (agg.market_value and total_assets) else None
        weight_html = f"{weight_pct:.1f}%" if weight_pct is not None else '<span class="na">n/a</span>'
        value_html = _fmt_money(agg.market_value)
        pnl_html = "—" if agg.is_cash else _fmt_signed(agg.pnl_amount, agg.pnl_pct)
        price_html, price_sub_html = _price_cell_pieces(agg, prices)
        sym_pop = _symbol_popover(agg, today)
        price_pop = _price_popover(agg, prices)
        action = "—"  # editorial; agent-authored adjustments live in §9
        rows.append(f"""\
          <tr>
            <td><div class="sym-trigger" tabindex="0" role="button">{_esc(agg.ticker)}{sym_pop}</div></td>
            <td>{_category_chip(agg)}</td>
            <td class="num price-cell"><div class="price-trigger" tabindex="0" role="button">{price_html}{price_sub_html}{price_pop}</div></td>
            <td class="num">{weight_html}</td>
            <td class="num">{value_html}</td>
            <td class="num">{pnl_html}</td>
            <td>{action}</td>
          </tr>""")
    body = "\n".join(rows)
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>持股損益與權重</h2>
      <span class="sub">產出時靜態快照 · 滑鼠移到代號或價格可看細節</span>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>代號</th>
            <th>類別</th>
            <th class="num">最新價</th>
            <th class="num">比重</th>
            <th class="num">市值</th>
            <th class="num">損益</th>
            <th>行動</th>
          </tr>
        </thead>
        <tbody>
{body}
        </tbody>
      </table>
    </div>
  </section>"""


def _price_cell_pieces(agg: TickerAggregate, prices: Dict[str, Any]) -> Tuple[str, str]:
    if agg.is_cash:
        return '<span class="na">—</span>', ""
    if agg.latest_price is None:
        return '<span class="na">n/a</span>', ""
    price = f'<span class="price-num">${agg.latest_price:,.2f}</span>'
    if agg.move_pct is None:
        return price, ""
    cls = "pos" if agg.move_pct >= 0 else "neg"
    sign = "+" if agg.move_pct >= 0 else "−"
    sub = f'<span class="price-sub {cls}">較前收 {sign}{abs(agg.move_pct):.2f}%</span>'
    return price, sub


def _category_chip(agg: TickerAggregate) -> str:
    if agg.is_cash:
        return '現金<span class="tag">現金</span>'
    chips = {
        MarketType.US: ("個股 / ETF", ""),
        MarketType.CRYPTO: ("加密資產", "warn"),
        MarketType.TW: ("台股", ""),
        MarketType.JP: ("日股", ""),
        MarketType.HK: ("港股", ""),
        MarketType.LSE: ("英股", ""),
    }.get(agg.market, ("資產", ""))
    label, cls = chips
    bucket_chip = {
        "long term": '<span class="tag pos">長線</span>',
        "mid term":  '<span class="tag">中線</span>',
        "short term": '<span class="tag warn">短線</span>',
    }.get(agg.bucket.lower().split()[0] + " " + agg.bucket.lower().split()[1] if len(agg.bucket.split()) >= 2 else agg.bucket.lower(), "")
    return f"{label}{bucket_chip}"


def _symbol_popover(agg: TickerAggregate, today: _dt.date) -> str:
    hold = hold_period_label(agg.earliest_date, today)
    since = (agg.earliest_date or "").rsplit("-", 1)[0] if agg.earliest_date else "n/a"
    return f"""<div class="pop pop-sym" role="tooltip">
                <h4>{_esc(agg.ticker)} · {_esc(agg.bucket)}</h4>
                <div class="pop-sub">{_esc(agg.market.value)}</div>
                <div class="pop-row"><span class="k">建倉時間</span><span class="v">{_esc(since)} · {hold}</span></div>
                <div class="pop-row"><span class="k">批次數</span><span class="v">{len(agg.lots)} 批</span></div>
              </div>"""


def _price_popover(agg: TickerAggregate, prices: Dict[str, Any]) -> str:
    if agg.is_cash:
        return ""
    pr = prices.get(agg.ticker, {}) or {}
    src = _esc(pr.get("price_source", "n/a"))
    as_of = _esc(pr.get("price_as_of", "n/a"))
    fresh = _esc(pr.get("price_freshness", "n/a"))
    price_str = f"${agg.latest_price:,.2f}" if agg.latest_price is not None else "n/a"
    rows: List[str] = []
    for lot in sorted(agg.lots, key=lambda l: l.date or ""):
        date = _esc(lot.date or "?")
        if lot.cost is None:
            cost = '<span class="pop-neg">n/a</span>'
            pnl = '<span class="pop-neg">n/a</span>'
        else:
            cost = f"${lot.cost:,.2f}"
            if agg.latest_price is not None:
                p = (agg.latest_price - lot.cost) * lot.quantity
                p_cls = "pop-pos" if p >= 0 else "pop-neg"
                p_sign = "+" if p >= 0 else "−"
                pnl = f'<span class="{p_cls}">{p_sign}${abs(p):,.0f}</span>'
            else:
                pnl = '<span class="pop-neg">n/a</span>'
        qty = f"{lot.quantity:g}"
        rows.append(f'<tr><td>{date}</td><td class="num">{cost}</td><td class="num">{qty}</td><td class="num">{pnl}</td></tr>')
    foot_avg = f"${agg.weighted_avg_cost:,.2f}" if agg.weighted_avg_cost is not None else "n/a"
    foot_total_cost = f"${agg.total_cost_known:,.0f}" if agg.total_cost_known else "n/a"
    foot_pnl = '<span class="pop-neg">n/a</span>' if agg.pnl_amount is None else (
        f'<span class="pop-{"pos" if agg.pnl_amount>=0 else "neg"}">'
        f'{"+" if agg.pnl_amount>=0 else "−"}${abs(agg.pnl_amount):,.0f}</span>'
    )
    return f"""<div class="pop pop-px" role="tooltip">
                <h4>{_esc(agg.ticker)} · 每批損益</h4>
                <div class="pop-sub">最新價 {price_str} · 來源：{src} · {fresh} · {as_of}</div>
                <table>
                  <thead><tr><th>取得日</th><th class="num">成本</th><th class="num">數量</th><th class="num">損益</th></tr></thead>
                  <tbody>{''.join(rows)}</tbody>
                  <tfoot class="summary"><tr><td>平均成本 {foot_avg}</td><td class="num">{foot_total_cost}</td><td class="num">{agg.total_qty:g}</td><td class="num">{foot_pnl}</td></tr></tfoot>
                </table>
              </div>"""


def render_pnl_ranking(aggs: Dict[str, TickerAggregate]) -> str:
    items = [a for a in aggs.values() if a.pnl_amount is not None]
    if not items:
        return ""
    items.sort(key=lambda a: -(a.pnl_amount or 0))
    max_abs = max(abs(a.pnl_amount or 0) for a in items) or 1.0
    rows = []
    for a in items[:10]:
        width = abs(a.pnl_amount) / max_abs * 100.0
        cls = "pos" if a.pnl_amount >= 0 else "neg"
        sign = "+" if a.pnl_amount >= 0 else "−"
        txt_cls = "pos-txt" if a.pnl_amount >= 0 else "neg-txt"
        rows.append(
            f'<div class="bar-row"><div class="bar-label">{_esc(a.ticker)}</div>'
            f'<div class="bar-track"><div class="bar {cls}" style="width:{width:.1f}%"></div></div>'
            f'<div class="bar-value {txt_cls}">{sign}${abs(a.pnl_amount):,.0f}</div></div>'
        )
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>持股損益排序</h2>
      <span class="sub">已實現＋未實現損益（USD）</span>
    </div>
    <div class="bars">{''.join(rows)}</div>
  </section>"""


def render_holding_period(pacing: BookPacing) -> str:
    if pacing.avg_hold_years is None:
        return ""
    oldest = pacing.oldest or ("n/a", "n/a", "n/a")
    newest = pacing.newest or ("n/a", "n/a", "n/a")
    over_1y = "n/a" if pacing.pct_held_over_1y is None else f"{pacing.pct_held_over_1y:.0f}%"
    d = pacing.distribution_pct
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>持有期間與節奏</h2>
      <span class="sub">成本加權，不含現金</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="k">平均持有</div><div class="v">{pacing.avg_hold_years} 年</div><div class="delta">成本加權</div></div>
      <div class="kpi"><div class="k">最舊批次</div><div class="v">{_esc(oldest[0])}</div><div class="delta">{_esc(oldest[1])} · {_esc(oldest[2])}</div></div>
      <div class="kpi"><div class="k">最新批次</div><div class="v">{_esc(newest[0])}</div><div class="delta">{_esc(newest[1])} · {_esc(newest[2])}</div></div>
      <div class="kpi"><div class="k">持有 &gt; 1 年</div><div class="v">{over_1y}</div><div class="delta">佔風險資產市值</div></div>
    </div>

    <div style="margin-top:18px">
      <div class="period-strip" aria-label="持有期間分布">
        <span style="width:{d['<1m']}%;background:#b15309"  title="< 1 月"></span>
        <span style="width:{d['1-6m']}%;background:#8a5a1c" title="1–6 月"></span>
        <span style="width:{d['6-12m']}%;background:#1d4690" title="6–12 月"></span>
        <span style="width:{d['1-3y']}%;background:#1f2937" title="1–3 年"></span>
        <span style="width:{d['3y+']}%;background:#15703d" title="3 年以上"></span>
      </div>
      <div class="period-legend">
        <span><i style="background:#b15309"></i>&lt; 1 月 · {d['<1m']}%</span>
        <span><i style="background:#8a5a1c"></i>1–6 月 · {d['1-6m']}%</span>
        <span><i style="background:#1d4690"></i>6–12 月 · {d['6-12m']}%</span>
        <span><i style="background:#1f2937"></i>1–3 年 · {d['1-3y']}%</span>
        <span><i style="background:#15703d"></i>3 年以上 · {d['3y+']}%</span>
      </div>
    </div>
  </section>"""


def render_theme_sector(context: Dict[str, Any]) -> str:
    """§10.1 #5 — Theme / sector exposure.

    Theme/sector classification is editorial (spec §4.3 — auto-classify each run); the
    agent computes it from current data and passes pre-rendered HTML via
    `context["theme_sector_html"]`. If absent, we still emit the section header so the
    11-section ordering contract holds (per spec §10.1) and surface a TODO.
    """
    body = context.get("theme_sector_html") or (
        '<div class="prose"><p>（主題與行業暴險待補 — 由 agent 在執行時依 §4.3 自動分類後注入）</p></div>'
    )
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>主題與行業暴險</h2>
      <span class="sub">USD 基準 · 含 ETF 穿透分配</span>
    </div>
    {body}
  </section>"""


def render_news(context: Dict[str, Any]) -> str:
    items = context.get("news") or []
    if not items:
        body = '<div class="prose"><p>（最新重大新聞待補 — 由 agent 在執行時擷取 1–3 則／核心部位）</p></div>'
    else:
        rows = []
        for n in items:
            impact = n.get("impact", "neu")
            label = {"pos": "正面", "neg": "負面", "neu": "中性"}.get(impact, "中性")
            url = _esc(n.get("url", "#"))
            rows.append(f"""\
      <div class="item">
        <div class="meta"><span class="tk">{_esc(n.get('ticker', '—'))}</span>{_esc(n.get('date', ''))}</div>
        <div class="body">
          <div class="head">{_esc(n.get('headline', ''))}</div>
          <div class="src">來源：<a href="{url}">{_esc(n.get('source', ''))}</a></div>
        </div>
        <span class="impact {impact}">{label}</span>
      </div>""")
        body = '<div class="news">' + "".join(rows) + "</div>"
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>最新重大新聞</h2>
      <span class="sub">每核心部位 1–3 則</span>
    </div>
    {body}
  </section>"""


def render_events(context: Dict[str, Any]) -> str:
    events = context.get("events") or []
    rows = []
    for e in events:
        rows.append(f"""\
          <tr>
            <td>{_esc(e.get('date', ''))}</td>
            <td>{_esc(e.get('topic', ''))}</td>
            <td>{_esc(e.get('event', ''))}</td>
            <td><span class="tag {_esc(e.get('impact_class', ''))}">{_esc(e.get('impact_label', ''))}</span></td>
            <td>{_esc(e.get('watch', ''))}</td>
          </tr>""")
    body = "\n".join(rows) if rows else '<tr><td colspan="5" class="na" style="text-align:center;padding:14px">（30 天內無已知事件）</td></tr>'
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>未來 30 天事件曆</h2>
      <span class="sub">財報、股東會、除息、產品、政策、央行、總體</span>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr><th>日期</th><th>標的 / 主題</th><th>事件</th><th>影響</th><th>關注重點</th></tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
    </div>
  </section>"""


def render_high_risk_opp(aggs: Dict[str, TickerAggregate], total_assets: float, context: Dict[str, Any]) -> str:
    risk_cells = []
    for agg in sorted([a for a in aggs.values() if not a.is_cash], key=lambda a: -(a.market_value or 0))[:10]:
        mv = agg.market_value or 0
        weight = (mv / total_assets * 100.0) if total_assets else 0.0
        # crude risk score: high vol bucket / large weight → high
        score = 0
        if agg.market == MarketType.CRYPTO:
            score += 6
        if "short" in agg.bucket.lower():
            score += 2
        if weight > 10:
            score += 2
        if agg.move_pct is not None and abs(agg.move_pct) > 8:
            score += 2
        score = min(score, 10)
        cls = "r-high" if score >= 6 else "r-mid" if score >= 3 else "r-low"
        move_str = f"{agg.move_pct:+.1f}%" if agg.move_pct is not None else "n/a"
        risk_cells.append(
            f'<div class="risk {cls}"><div class="t">{_esc(agg.ticker)}</div>'
            f'<div class="s">風險 {score} / 10</div>'
            f'<div class="m">{weight:.1f}% · {move_str}</div></div>'
        )

    opps = context.get("high_opps") or []
    opp_rows = []
    for o in opps:
        opp_rows.append(f"""\
          <div class="item">
            <div class="tk">{_esc(o.get('ticker', '—'))}</div>
            <div class="why">{_esc(o.get('why', ''))}</div>
            <div class="trig">{_esc(o.get('trigger', ''))}</div>
          </div>""")
    opp_html = "".join(opp_rows) or '<div class="prose"><p>（無高機會清單）</p></div>'
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>高風險與高機會</h2>
      <span class="sub">左：風險熱圖 ／ 右：機會清單</span>
    </div>
    <div class="cols-2">
      <div>
        <div class="eyebrow" style="margin-bottom:10px">高風險</div>
        <div class="risk-grid">{''.join(risk_cells)}</div>
      </div>
      <div>
        <div class="eyebrow" style="margin-bottom:10px">高機會</div>
        <div class="opp-list">{opp_html}</div>
      </div>
    </div>
  </section>"""


def render_adjustments(context: Dict[str, Any]) -> str:
    adjs = context.get("adjustments") or []
    if not adjs:
        return f"""\
  <section class="section">
    <div class="section-head">
      <h2>建議調整</h2>
      <span class="sub">具體標的 · 動作 · 觸發</span>
    </div>
    <div class="prose"><p>（建議調整清單待 agent 補入）</p></div>
  </section>"""
    rows = []
    for a in adjs:
        rows.append(f"""\
          <tr>
            <td><span class="sym-trigger" tabindex="0" role="button">{_esc(a.get('ticker', '—'))}</span></td>
            <td class="num">{a.get('current_pct', 0):.1f}%</td>
            <td><span class="adj-action {_esc(a.get('action', 'hold'))}">{_esc(a.get('action_label', ''))}</span></td>
            <td class="why">{_esc(a.get('why', ''))}</td>
            <td class="trig">{_esc(a.get('trigger', ''))}</td>
          </tr>""")
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>建議調整</h2>
      <span class="sub">具體標的 · 動作 · 觸發</span>
    </div>
    <div class="tbl-wrap">
      <table class="adj-tbl">
        <thead><tr><th>標的</th><th>目前</th><th>建議</th><th>理由</th><th>觸發</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </section>"""


def render_actions(context: Dict[str, Any]) -> str:
    a = context.get("actions") or {}
    rows = []
    for label_class, label_zh, key in [("do", "必做", "must_do"),
                                        ("may", "可做", "may_do"),
                                        ("no", "不建議", "avoid"),
                                        ("fix", "補資料", "need_data")]:
        for item in a.get(key, []) or []:
            rows.append(f'<li><span class="lbl {label_class}">{label_zh}</span><span>{_esc(item)}</span></li>')
    body = "\n".join(rows) or '<li><span class="lbl">—</span><span>（行動清單待補）</span></li>'
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>今日行動清單</h2>
      <span class="sub">優先順序</span>
    </div>
    <ul class="actions">
{body}
    </ul>
  </section>"""


def render_sources(prices: Dict[str, Any], context: Dict[str, Any]) -> str:
    rows = []
    for ticker, pr in sorted(prices.items()):
        if ticker.startswith("_"):
            continue
        if not isinstance(pr, dict):
            continue
        fresh = pr.get("price_freshness", "n/a")
        fresh_cls = {"fresh": "fresh", "delayed": "delayed",
                     "stale_after_exhaustive_search": "stale", "n/a": "stale"}.get(fresh, "stale")
        notes = []
        if pr.get("yfinance_auto_fix_applied"):
            notes.append(f"自動修正：{pr.get('yfinance_auto_fix_summary')}")
        if pr.get("yfinance_retry_count"):
            notes.append(f"重試 {pr.get('yfinance_retry_count')} 次")
        if pr.get("yfinance_failure_reason"):
            notes.append(_esc(pr.get("yfinance_failure_reason"))[:60])
        rows.append(f"""\
          <tr>
            <td>{_esc(ticker)}</td>
            <td>{_esc(pr.get('price_source', 'n/a'))}</td>
            <td>{_esc(pr.get('market_state_basis', 'n/a'))}</td>
            <td class="num">{_esc(pr.get('price_as_of', 'n/a'))}</td>
            <td><span class="freshness {fresh_cls}">{_esc(fresh)}</span></td>
            <td>{_esc('；'.join(notes)) or '—'}</td>
          </tr>""")
    gaps = context.get("data_gaps") or []
    gap_html = "".join(f'<li><b>{_esc(g.get("summary", ""))}：</b>{_esc(g.get("detail", ""))}</li>' for g in gaps) \
        or '<li>（無資料缺口）</li>'
    spec_note = context.get("spec_update_note")
    spec_html = (f'<div class="bucket-note" style="margin-top:18px"><b>建議更新 agent spec：</b>{_esc(spec_note)}</div>'
                 if spec_note else "")
    return f"""\
  <section class="section">
    <div class="section-head">
      <h2>資料來源與缺口</h2>
      <span class="sub">每筆價格的取得方式與新鮮度 · 待補資料逐項列出</span>
    </div>
    <div class="eyebrow" style="margin-bottom:10px">最新價來源稽核</div>
    <div class="tbl-wrap">
      <table class="src-tbl">
        <thead>
          <tr><th>標的</th><th>價格來源</th><th>市場狀態</th><th>取得時間</th><th>新鮮度</th><th>備註</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    <div class="eyebrow" style="margin-top:22px;margin-bottom:6px">資料缺口</div>
    <ul class="gap-list">{gap_html}</ul>
    {spec_html}
  </section>"""


# ----------------------------------------------------------------------------- #
# Master assembly
# ----------------------------------------------------------------------------- #

def render_html(
    aggs: Dict[str, TickerAggregate],
    prices: Dict[str, Any],
    context: Dict[str, Any],
    css: str,
    config: Dict[str, float],
) -> str:
    today = _dt.date.today()

    # Totals (USD basis — caller is responsible for FX-converting cash if non-USD)
    total_assets = sum(a.market_value or 0 for a in aggs.values())
    invested = sum(a.market_value or 0 for a in aggs.values() if not a.is_cash)
    cash = sum(a.market_value or 0 for a in aggs.values() if a.is_cash)
    pnl = sum(a.pnl_amount for a in aggs.values() if a.pnl_amount is not None) or None

    pacing = book_pacing(aggs, today)
    _ = special_checks(aggs, total_assets, config)  # results currently surfaced via context["alerts"]

    lang_attr = {"繁體中文": "zh-Hant", "english": "en", "japanese": "ja",
                 "簡體中文": "zh-Hans"}.get(context.get("language"), "zh-Hant")

    # Render sections (§10 order)
    sections = [
        render_masthead(context),
        render_alerts(context),
        render_today_summary(context),                                     # §10.1 #1
        render_dashboard(aggs, total_assets, invested, cash, pnl),         # §10.1 #2
        render_holdings_table(aggs, total_assets, prices, today),          # §10.1 #3
        render_pnl_ranking(aggs),                                          # §10.4 chart
        render_holding_period(pacing),                                     # §10.1 #4
        render_theme_sector(context),                                      # §10.1 #5
        render_news(context),                                              # §10.1 #6
        render_events(context),                                            # §10.1 #7
        render_high_risk_opp(aggs, total_assets, context),                 # §10.1 #8
        render_adjustments(context),                                       # §10.1 #9
        render_actions(context),                                           # §10.1 #10
        render_sources(prices, context),                                   # §10.1 #11
    ]

    return f"""<!doctype html>
<html lang="{lang_attr}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(context.get('title', '投資組合健康檢查'))}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
{chr(10).join(s for s in sections if s)}
  <footer class="footer">
    本報告依 <code>docs/portfolio_report_agent_guidelines.md</code> 規範產出，價格為產出時靜態快照，未持續刷新。
  </footer>
</div>
</body>
</html>
"""


# ----------------------------------------------------------------------------- #
# CLI
# ----------------------------------------------------------------------------- #

def _cli(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--holdings", default="HOLDINGS.md", type=Path)
    p.add_argument("--settings", default="SETTINGS.md", type=Path)
    p.add_argument("--prices", required=True, type=Path,
                   help="JSON output from scripts/fetch_prices.py")
    p.add_argument("--context", default=None, type=Path,
                   help="Editorial context JSON (today summary, news, actions, ...)")
    p.add_argument("--sample", default=Path(__file__).resolve().parent.parent / "reports" / "_sample_redesign.html",
                   type=Path, help="Canonical visual reference (read-only, supplies CSS)")
    p.add_argument("--output", default=None, type=Path,
                   help="Output HTML path; default: reports/<timestamp>_portfolio_report.html")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _cli(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if not args.holdings.exists():
        print(f"ERROR: {args.holdings} not found", file=sys.stderr); return 2
    if not args.prices.exists():
        print(f"ERROR: {args.prices} not found (run fetch_prices.py first)", file=sys.stderr); return 3

    lots = parse_holdings(args.holdings)
    aggs = aggregate(lots)
    prices = json.loads(args.prices.read_text(encoding="utf-8"))
    merge_prices(aggs, prices)

    context: Dict[str, Any] = {}
    if args.context and args.context.exists():
        context = json.loads(args.context.read_text(encoding="utf-8"))
    elif args.context:
        logging.warning("Context file %s not found; rendering with placeholders.", args.context)

    css = load_canonical_css(args.sample)
    config = {**DEFAULTS}
    html_doc = render_html(aggs, prices, context, css, config)

    if args.output is None:
        ts = _dt.datetime.now().strftime("%Y-%m-%d_%H%M")
        args.output = Path("reports") / f"{ts}_portfolio_report.html"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {args.output} ({len(html_doc):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
