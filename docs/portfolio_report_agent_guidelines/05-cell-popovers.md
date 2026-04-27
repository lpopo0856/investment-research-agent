
### 13.1 Behavior summary

Both the Symbol and Price cells expose a popover that:

- **Opens on hover** (desktop).
- **Slides up as a bottom sheet on tap** (touch / tablet).
- Fades in / out — no click required, no toggle state.

The previous `<button popovertarget>` + native HTML `popover` pattern is **deprecated** because:
- It required a click to open, conflicting with hover-to-preview UX.
- Native top-layer rendering disabled fade-in animations and made the popover feel modal.

The new pattern is a **CSS-driven `:hover` / `:focus-within` popover, structured as a *descendant* of the trigger** so hover propagates naturally and there is no JavaScript dependency for show/hide.

### 13.2 HTML structure

```html
<td>
  <div class="sym-trigger" tabindex="0" role="button">
    NVDA
    <div class="pop pop-sym" role="tooltip">
      …translated: company name, asset class, since-line, lot count, rationale…
    </div>
  </div>
</td>

<td class="num price-cell">
  <div class="price-trigger" tabindex="0" role="button">
    <span class="price-num">$211.62</span>
    <span class="price-sub pos">較前收 +1.40%</span>
    <div class="pop pop-px" role="tooltip">
      <h4>NVDA · 每批損益</h4>
      <div class="pop-sub">最新價 $211.62 · 來源：Twelve Data · 2026-04-27 09:00</div>
      <table>… per-lot rows + summary tfoot …</table>
    </div>
  </div>
</td>
```

**Trigger element rules:**
- The trigger is a `<div tabindex="0" role="button">` (not `<button>`) because the popover may contain a `<table>`, which is invalid inside a `<button>`.
- `role="button"` keeps screen-reader semantics; `tabindex="0"` keeps keyboard focusability.

### 13.3 CSS pattern (desktop)

Use the same surface palette as the rest of the page. **Do not** use a dark background with light text — that breaks the editorial look and makes the popover feel like a different application surface.

```css
:root{
  --table-header-z:70;
  --popover-host-z:40;
  --popover-z:50;
}

thead th{
  position:sticky;
  top:0;
  z-index:var(--table-header-z);
  background:var(--paper);
  box-shadow:0 1px 0 var(--hairline-2);
}

.pop{
  position:absolute;
  top:calc(100% + 8px);              /* anchored just below the trigger, near the cursor */
  left:0;
  z-index:var(--popover-z);

  background:var(--surface);          /* light paper surface */
  color:var(--ink);                   /* primary ink */
  border:1px solid var(--hairline-2);
  border-radius:4px;
  padding:12px 14px;

  /* The single allowed elevated shadow on the page */
  box-shadow:0 6px 20px rgba(15,25,31,.10), 0 1px 2px rgba(0,0,0,.04);

  width:max-content;
  min-width:min(300px, calc(100vw - 64px));
  max-width:min(560px, calc(100vw - 64px));
  font-size:clamp(12px, 0.25vw + 11.4px, 13px);
  line-height:1.55;
  text-align:left;
  overflow-wrap:normal;

  /* Hidden by default; fade in via opacity + small lift */
  opacity:0;
  visibility:hidden;
  transform:translateY(-4px);
  transition:opacity .18s ease, transform .18s ease, visibility 0s linear .18s;
  pointer-events:none;
}

/* Cells in the right portion of the table anchor right so popovers don't overflow */
.tbl-wrap td:nth-last-child(-n+3) .pop{left:auto;right:0}

/* Raise the active table cell so descendant popovers are not trapped below sticky cells. */
tbody td:has(.sym-trigger:is(:hover,:focus-within)),
tbody td:has(.price-trigger:is(:hover,:focus-within)){
  position:relative;
  z-index:var(--popover-host-z);
}

/* Show on hover or focus — descendant popover keeps :hover state while pointed at */
.sym-trigger:hover > .pop,
.sym-trigger:focus-within > .pop,
.price-trigger:hover > .pop,
.price-trigger:focus-within > .pop{
  opacity:1;visibility:visible;transform:translateY(0);
  transition:opacity .18s ease, transform .18s ease, visibility 0s;
  pointer-events:auto;
}

.pop table{
  width:100%;
  min-width:0;
  table-layout:auto;
}
.pop table th,.pop table td{
  white-space:nowrap;
  overflow-wrap:normal;
}
.pop thead th{
  position:static;
  z-index:auto;
  background:transparent;
  box-shadow:none;
}
```

Internal styling uses the same tokens as the page body — `--ink` text on `--surface`, `--muted` for sublines, `--hairline` for dividers, `--pos` / `--neg` for signed numbers. **No custom dark-mode palette inside the popover.** On desktop, popovers must expand to fit their content up to the viewport-aware max width; do not force table cells or short labels to wrap early. Long flex value cells such as `.pop-row .v` should use `min-width:0; text-align:right; overflow-wrap:break-word;` so only genuinely long prose wraps.

### 13.4 Symbol popover content

- Company / instrument full name (translated when natural).
- Asset class and theme tags.
- `since YYYY-MM · <duration> · N lot(s)` line.
- Optional one-line rationale (why the position is in Long / Mid / Short bucket, if non-obvious).

### 13.5 Price popover content

- A heading with the ticker + "每批損益" (translated per SETTINGS).
- A subline with the latest price, selected source, and timestamp / freshness.
- A small table: one row per lot with columns `取得日 / 成本 / 數量 / 損益` (translated). Numeric columns right-aligned with tabular numerals.
- A `<tfoot class="summary">` row showing **平均成本 / 總成本 / 總損益**. Top-bordered, semibold.
- If cost is `?` for a lot, render that row's P&L as `n/a` and exclude it from the average-cost calculation.

### 13.6 Responsive (RWA) — popover on tablet, phone, and touch

A subtle but critical detail: `.tbl-wrap` activates `overflow-x:auto` on tablet (≤ 880px) and phone (≤ 600px) to allow horizontal scrolling of the wide table. Browsers coerce `overflow-y` to `auto` whenever `overflow-x` is non-visible, which would clip any popover that extends below its cell. The fix:

- **Desktop ≥ 881px** — `.tbl-wrap` has *no* overflow constraint (the table fits within the page container at its `min-width:760px`). Popover is `position:absolute`, anchored to the trigger, fades in below the cell.
- **Tablet 601–880px** and **Phone ≤ 600px** — `.tbl-wrap` enables `overflow-x:auto`. To escape the resulting overflow context, the popover switches to a fixed bottom sheet using safe-area insets: `position:fixed; left:max(12px, env(safe-area-inset-left)); right:max(12px, env(safe-area-inset-right)); bottom:max(12px, env(safe-area-inset-bottom));`. It must also set `max-height:min(72vh, calc(100dvh - 32px)); overflow:auto; overscroll-behavior:contain;` so long text or lot tables scroll inside the sheet instead of exceeding the viewport.
- **Touch (`@media (hover:none)`)** — hover does not fire reliably; suppress the hover trigger and only respond to `:focus-within` (i.e. tap). Tap outside the trigger blurs the focus and dismisses the sheet automatically.
- **Layering** — because this pattern intentionally does not use native HTML top-layer popovers, the CSS must explicitly separate layers: sticky table headers use `z-index:var(--table-header-z)` and an opaque `var(--paper)` background so scrolling rows never cover the header; `.pop` uses `z-index:var(--popover-z)` and the active table cell uses `z-index:var(--popover-host-z)` via `:has(...)`.

```css
@media (max-width:880px), (hover:none){
  .pop{
    position:fixed;
    left:max(12px, env(safe-area-inset-left));
    right:max(12px, env(safe-area-inset-right));
    bottom:max(12px, env(safe-area-inset-bottom));
    top:auto;
    width:auto;max-width:none;
    max-height:calc(100vh - 32px);
    max-height:min(72vh, calc(100dvh - 32px));
    overflow:auto;
    overscroll-behavior:contain;
    -webkit-overflow-scrolling:touch;
    transform:translateY(20px);
    box-shadow:0 10px 30px rgba(15,25,31,.18), 0 2px 6px rgba(0,0,0,.08);
  }
  .pop table{table-layout:fixed}
  .pop table th,.pop table td{white-space:normal;overflow-wrap:anywhere}
  .sym-trigger:hover > .pop,
  .sym-trigger:focus-within > .pop,
  .price-trigger:hover > .pop,
  .price-trigger:focus-within > .pop{
    opacity:1;visibility:visible;transform:translateY(0);pointer-events:auto;
  }
}
@media (hover:none){
  /* Tap-only: suppress hover, require focus */
  .sym-trigger:hover > .pop,
  .price-trigger:hover > .pop{opacity:0;visibility:hidden;transform:translateY(20px);pointer-events:none}
}
```

### 13.7 Reduced motion

Honor `@media (prefers-reduced-motion: reduce)` — drop the fade and slide to an instant show / hide:

```css
@media (prefers-reduced-motion: reduce){
  .pop{transition:opacity .01s linear, visibility 0s !important;transform:none !important}
}
```

### 13.8 Anti-patterns (must avoid)

- **Reverse-color popovers** (dark background + light text). The popover is part of the page palette, not a separate surface.
- **Click-to-open popovers** on desktop. The user explicitly wants hover preview; clicking is reserved for nothing in this column.
- **Popovers anchored to the cell or the row** rather than to the trigger element — that pushes them away from the cursor and weakens the "next to mouse" feel.
- **`<button>` as the trigger when content includes block elements** (e.g. tables) — invalid HTML; use `<div tabindex="0" role="button">`.
- **`overflow:hidden` on `.tbl-wrap`** — silently clips popovers. Use `overflow-x:auto` only when needed (tablet + phone) and rely on the `position:fixed` bottom-sheet escape hatch.
- **Mobile bottom sheets without viewport bounds** — any mobile / touch popover must have safe-area-aware left/right/bottom, a `100dvh`-based max height, internal scrolling, long-text wrapping, and active-cell z-index promotion.

---

