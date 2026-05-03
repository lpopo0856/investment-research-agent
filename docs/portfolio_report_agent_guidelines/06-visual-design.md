## 14. Visual design standard

### 14.1 Direction

Editorial/research-desk note: warm paper, ink text, hairline rules, whitespace hierarchy, clear numbers/risk. Not blue SaaS, dark gradient hero, saturated blocks, heavy borders/shadows.

### 14.2 Tokens

```css
:root{
  --paper:#f7f5ef; --surface:#ffffff; --surface-2:#fbfaf6;
  --hairline:#e7e3d8; --hairline-2:#d8d3c6;
  --ink:#15191f; --ink-soft:#2c333d; --muted:#6b7280; --muted-2:#8a8f99;
  --pos:#15703d; --neg:#b42318; --warn:#b15309; --info:#1d4690;
  --accent:#1f2937; --accent-warm:#8a5a1c;
}
```

### 14.3 Typography

System fonts only; no external fonts.

```css
/* body */ "SF Pro Text",-apple-system,BlinkMacSystemFont,"Segoe UI Variable Text","Segoe UI","PingFang TC","Microsoft JhengHei UI","Microsoft JhengHei","Noto Sans CJK TC",system-ui,sans-serif;
/* headings */ "SF Pro Display",-apple-system,BlinkMacSystemFont,"Segoe UI Variable Display","Segoe UI","PingFang TC","Microsoft JhengHei UI",system-ui,sans-serif;
```

Required: `-webkit-font-smoothing:antialiased`; `text-rendering:optimizeLegibility`; global `font-feature-settings:"ss01","cv11","tnum" 1,"lnum" 1`; numeric classes force `font-variant-numeric:tabular-nums lining-nums`; heading weight 620-680 never >720; body 400-500; KPI 620; labels/eyebrows 700; large heading letter-spacing `-.012em`; small-caps/table headers `.12em-.22em` uppercase; line-height body 1.62, headings 1.18, KPI 1.1.

### 14.4 Font-size floors (HARD)

| Element | `clamp(min, fluid, max)` | Floor |
|---|---|---|
| body | `clamp(14px, 0.85vw + 11.6px, 15.5px)` | 14px |
| masthead h1 | `clamp(22px, 3vw + 10px, 36px)` | 22px |
| section h2 | `clamp(15px, 0.6vw + 13px, 19px)` | 15px |
| `.kpi .v` | `clamp(22px, 1.5vw + 16px, 30px)` | 22px |
| table cell | `clamp(12.5px, 0.3vw + 11.6px, 13.5px)` | 12.5px |
| price headline | `clamp(15px, 0.6vw + 13px, 17px)` | 15px |
| subline | `clamp(11px, 0.2vw + 10.4px, 12px)` | 11px |
| eyebrow / KPI label / th | `clamp(10px, 0.15vw + 9.5px, 11.5px)` | 10px |
| popover body | `clamp(12px, 0.25vw + 11.4px, 13px)` | 12px |
| footer/fine print | `clamp(11px, 0.15vw + 10.6px, 12px)` | 11px |

Media queries may fix at floor, never below.

### 14.5 Layout/components

- Page: `max-width:1180px`; side padding 40px; top 56px; bottom 80px; no 1480px+ layouts.
- Masthead: newspaper; 3px black top rule, 1px hairline bottom; eyebrow, headline, dek ≤780px, meta row (generated time, FX rate, data source, next event); no gradient/glow/shadow.
- Warning callout: `--surface-2`, 3px `--neg` left rule, small badge, optional 2-col bullets ≤1.5 lines; no saturated red wash.
- KPI strip: 4 columns, hairline top/bottom and between columns; no card shadows/top bars.
- Section head: `h2` left, `.sub` right muted, hairline below; no gradient/color rails.
- Charts: donut SVG circle, radius 42, stroke 20, center total; slice colors `--accent`, `--pos`, `--accent-warm`, `--info`, `--warn`; bars track 6px `#ebe7da`, radius 2px, solid fills only.
- Table: 1px `--ink` top/bottom; 1px `--hairline` rows; sticky header opaque `var(--paper)` with z var; hover `--surface-2`; numeric right/tabular; ticker weight 680; chips thin-bordered.
- Symbol/Price triggers: chrome-free `div[tabindex="0"][role="button"]`, `cursor:help`; symbol dotted underline on hover/focus; price trigger wraps price+subline and anchors popover.
- Popover: light surface; radius 4px; desktop shadow `0 6px 20px rgba(15,25,31,.10),0 1px 2px rgba(0,0,0,.04)`; desktop max `min(560px,100vw-64px)`; mobile bottom sheet with safe-area, `max-height:min(72vh,calc(100dvh - 32px))`, internal scroll.
- Risk heatmap: 5-col grid; 1px hairlines not gaps; 3px left risk rule (low/mid/high = light blue/amber/red); content ticker, `Risk N/10`, `weight · move`; no saturated cell fill.
- Action list: 84px translated label col; description right; dotted hairline rows.
- Radius: page 2-4px; chips/badges 3-4px; bars 2px; never ≥8px or `999px`.
- Shadow: none except popovers; hover hints ≤`0 1px 0 rgba(0,0,0,.04)`.

### 14.6 Price-cell CSS

```css
.price-cell{position:relative}
.price-trigger{display:inline-flex;flex-direction:column;align-items:flex-end;gap:2px;cursor:help}
.price-num{color:var(--ink);font-size:clamp(15px,0.6vw + 13px,17px);font-weight:650;line-height:1.12;font-variant-numeric:tabular-nums lining-nums}
.price-sub{color:var(--muted);font-size:clamp(11px,0.2vw + 10.4px,12px);font-variant-numeric:tabular-nums lining-nums}
.price-sub.pos{color:var(--pos)} .price-sub.neg{color:var(--neg)}
```

### 14.7 Responsive / mobile

HTML requires `<meta name="viewport" content="width=device-width, initial-scale=1">`.

| Tier | Range | Required changes |
|---|---|---|
| Desktop | ≥881px | Default multi-col grids; no table horizontal scroll; body 14.5-15.5px; table 13-13.5px. |
| Tablet | 601-880px | KPI 2 cols; `cols-2/3` 1 col; donut+bars stack; heatmap 2 cols; body 14-14.5px; table 13px; tighter bar labels. |
| Phone | ≤600px | KPI 1 col; heatmap 1 col; holdings use `.holdings-cards` (one holding per card) and `.holdings-table-wrap` is hidden; no normal-reading horizontal scroll at 360/390/430px; each card shows Symbol, Category, Price, Weight, Value, P&L, Action; Symbol/Price controls reuse `div[tabindex="0"][role="button"]` triggers and bottom-sheet popovers; body 14px, table 12.5px, sublines 11px; action labels 64px. |

Table wrapper: default table sections use `<div class="tbl-wrap"><table>…</table></div>`. Desktop `.tbl-wrap` must not set overflow. Tablet may enable `overflow-x:auto` + `-webkit-overflow-scrolling:touch`, negative side margin equal page padding, and inner table `min-width` ≥760px when a table genuinely needs swipe. Holdings are the exception on phone: render `<div class="tbl-wrap holdings-table-wrap"><table class="holdings-tbl">…</table></div>` plus sibling `.holdings-cards`; at ≤600px hide `.holdings-table-wrap` and show `.holdings-cards`. Touch targets ≥30px. Test at 360/390/430px; verify no document horizontal overflow, holdings cards, and bottom-sheet popovers in iOS Safari + Chrome Mobile.

### 14.8 Anti-patterns

No dark-gradient hero; heavy shadows on content; saturated region washes; heading weights ≥800; pill radii; multiple competing `<style>` blocks; external fonts; IRR/annualized-return columns; bilingual/English fallback labels under non-English SETTINGS; font sizes below §14.4.

### 14.9 Reference

`reports/_sample_redesign.html` is canonical visual reference. If missing, rebuild from §14 tokens/rules.
