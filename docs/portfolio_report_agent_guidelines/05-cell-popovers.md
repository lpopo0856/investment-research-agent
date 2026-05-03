## 13. Cell popovers (Symbol & Price)

### 13.1 Behavior

Symbol and Price cells expose non-modal detail popovers: desktop opens on hover/focus; touch/tablet opens as fixed bottom sheet on tap/focus; fade/slide unless reduced-motion. Native `<button popovertarget>` / HTML popover is deprecated. Use CSS descendant popover under trigger so hover state persists and JS is unnecessary.

### 13.2 Markup contract

Trigger must be `<div tabindex="0" role="button">`, not `<button>`, because popovers contain block/table content. Holdings phone cards reuse the same Symbol/Price trigger contract as the desktop table; do not create visually similar substitute controls.

```html
<td><div class="sym-trigger" tabindex="0" role="button"><span class="sym-text">NVDA</span><div class="pop pop-sym" role="tooltip">...</div></div></td>
<td class="num price-cell"><div class="price-trigger" tabindex="0" role="button"><span class="price-num">$211.62</span><span class="price-sub pos">較前收 +1.40%</span><div class="pop pop-px" role="tooltip">...</div></div></td>
```

Only real Symbol/Price popover triggers may use `.sym-trigger` / `.price-trigger`; static ticker text in other tables must use `.sym-label` or plain text with no `tabindex`, `role="button"`, pointer cursor, or dotted underline. The trigger text (`.sym-trigger .sym-text`, `.price-trigger .price-num`) should show a dotted underline even before hover/focus so users can identify the hover/tap affordance; non-interactive cells must not show that affordance.

### 13.3 Desktop CSS requirements

Use page palette (`--surface`, `--ink`, `--muted`, `--hairline`, `--pos`, `--neg`); no dark/reverse-color popovers. Required layer vars: `--table-header-z:70`, `--popover-host-z:40`, `--popover-z:50`. Sticky table header: `position:sticky; top:0; z-index:var(--table-header-z); background:var(--paper); box-shadow:0 1px 0 var(--hairline-2)`.

`.pop` desktop essentials: `position:absolute; top:calc(100% + 8px); left:0; z-index:var(--popover-z); background:var(--surface); color:var(--ink); border:1px solid var(--hairline-2); border-radius:4px; padding:12px 14px; box-shadow:0 6px 20px rgba(15,25,31,.10),0 1px 2px rgba(0,0,0,.04); width:max-content; min-width:min(300px,calc(100vw - 64px)); max-width:min(560px,calc(100vw - 64px)); font-size:clamp(12px,0.25vw + 11.4px,13px); line-height:1.55; text-align:left; opacity:0; visibility:hidden; transform:translateY(-4px); transition:opacity .18s ease,transform .18s ease,visibility 0s linear .18s; pointer-events:none`.

Show rule: `.sym-trigger:hover>.pop`, `.sym-trigger:focus-within>.pop`, `.price-trigger:hover>.pop`, `.price-trigger:focus-within>.pop` → `opacity:1; visibility:visible; transform:translateY(0); pointer-events:auto; transition:opacity .18s ease,transform .18s ease,visibility 0s`. Right-side table cells anchor right: `.tbl-wrap td:nth-last-child(-n+3) .pop{left:auto;right:0}`. Active host cells use `position:relative; z-index:var(--popover-host-z)` via `:has(.sym-trigger:is(:hover,:focus-within))` / price equivalent. Popover tables: width 100%, table-layout auto, desktop cells nowrap; popover table header not sticky.

### 13.4 Symbol popover content

Company/instrument full name (translate natural language), asset class + theme tags, `since YYYY-MM · <duration> · N lot(s)`, optional one-line bucket rationale.

### 13.5 Price popover content

Heading ticker + translated "per-lot P&L"; subline latest price + selected source + timestamp/freshness; table one row per lot with translated `取得日 / 成本 / 數量 / 損益`, numeric right/tabular; `<tfoot class="summary">` with average cost / total cost / total P&L, top border, semibold. Lot cost `?` → row P&L `n/a`, exclude from average-cost calc.

### 13.6 Responsive / touch

`.tbl-wrap` overflow rule: desktop ≥881px no overflow; tablet may set `overflow-x:auto` only when popovers switch to fixed bottom sheet, otherwise descendant popovers clip. Phone holdings (≤600px) use `.holdings-cards` outside the table wrapper for normal reading; the cards still reuse `.sym-trigger` / `.price-trigger`, so the fixed bottom-sheet popover behavior below remains mandatory.

For `@media (max-width:880px), (hover:none)`, `.pop` becomes fixed bottom sheet:

```css
.pop{position:fixed;left:max(12px,env(safe-area-inset-left));right:max(12px,env(safe-area-inset-right));bottom:max(12px,env(safe-area-inset-bottom));top:auto;width:auto;max-width:none;max-height:min(72vh,calc(100dvh - 32px));overflow:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;transform:translateY(20px);box-shadow:0 10px 30px rgba(15,25,31,.18),0 2px 6px rgba(0,0,0,.08)}
.pop table{table-layout:fixed}.pop table th,.pop table td{white-space:normal;overflow-wrap:anywhere}
```

Touch `@media (hover:none)`: suppress hover show; require focus-within tap; tap outside blurs/dismisses. Safe-area insets, `100dvh` max height, internal scrolling, long-text wrapping, and active-cell z-index promotion are mandatory.

### 13.7 Reduced motion

`@media (prefers-reduced-motion: reduce){.pop{transition:opacity .01s linear, visibility 0s !important; transform:none !important}}`

### 13.8 Anti-patterns

No dark popovers; no click-to-open desktop behavior; no row/cell-anchored popovers; no `<button>` trigger with block/table descendants; no `overflow:hidden` on `.tbl-wrap`; no mobile sheet without viewport bounds/internal scroll/safe-area; no clipped popovers under sticky headers.
