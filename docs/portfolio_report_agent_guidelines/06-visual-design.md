## 14. Visual design standard

### 14.1 Direction

Overall direction is **editorial × research-desk note**: warm-paper background, ink-black text, hairline rules, generous whitespace, hierarchy via typography rather than color blocks / shadows / heavy borders.

**Not** a generic blue SaaS dashboard, **not** a dark-gradient hero card, **not** stacked saturated color blocks.

Priorities: scan efficiency, number clarity, risk visibility.

### 14.2 Design tokens (declare via `:root` variables)

```css
:root{
  /* Surface */
  --paper:        #f7f5ef;     /* warm paper body background — never pure white or cool gray */
  --surface:      #ffffff;
  --surface-2:    #fbfaf6;
  --hairline:     #e7e3d8;     /* primary divider */
  --hairline-2:   #d8d3c6;     /* heavier divider (table top/bottom rule, region frame) */

  /* Ink */
  --ink:          #15191f;     /* primary text — never pure #000 */
  --ink-soft:     #2c333d;
  --muted:        #6b7280;
  --muted-2:      #8a8f99;

  /* Semantic */
  --pos:          #15703d;     /* positive return, positive news */
  --neg:          #b42318;     /* negative return, alerts */
  --warn:         #b15309;     /* rich valuation, overheated */
  --info:         #1d4690;
  --accent:       #1f2937;
  --accent-warm:  #8a5a1c;     /* editorial warm accent */
}
```

### 14.3 Typography

**Must use system stacks — do not load any external font / Google Fonts.**

```css
/* Body / Text */
font-family:
  "SF Pro Text", -apple-system, BlinkMacSystemFont,
  "Segoe UI Variable Text", "Segoe UI",
  "PingFang TC", "Microsoft JhengHei UI", "Microsoft JhengHei",
  "Noto Sans CJK TC", system-ui, sans-serif;

/* Display / Headings */
font-family:
  "SF Pro Display", -apple-system, BlinkMacSystemFont,
  "Segoe UI Variable Display", "Segoe UI",
  "PingFang TC", "Microsoft JhengHei UI", system-ui, sans-serif;
```

**Required typography settings:**

- `body` must enable `-webkit-font-smoothing:antialiased` and `text-rendering:optimizeLegibility`.
- Globally enable `font-feature-settings: "ss01", "cv11", "tnum" 1, "lnum" 1`.
- Numeric classes (`.num`, `.kpi .v`, `.bar-value`, numeric table cells) must additionally force `font-variant-numeric: tabular-nums lining-nums`.
- Heading weights live in **620–680**, **never above 720**. Body 400–500. KPI numbers 620. Labels / eyebrows 700.
- Large headings get `letter-spacing:-.012em` (tight). Small-caps eyebrows / table headers get `letter-spacing:.12em–.22em` and `text-transform:uppercase`.
- Line-height: body **1.62**, heading **1.18**, KPI numbers **1.1**.

### 14.4 Fluid font-size scale (HARD floors)

The page must remain readable on a 360px-wide phone *and* a 27" monitor. Use `clamp()` for elements that scale, hard-coded sizes for elements that should not. **Never** ship a viewport-only rule that pushes any user-facing text below the floor.

| Element | `clamp(min, fluid, max)` | Floor |
|---|---|---|
| `body` (base) | `clamp(14px, 0.85vw + 11.6px, 15.5px)` | 14px on phone |
| Masthead `h1` | `clamp(22px, 3vw + 10px, 36px)` | 22px |
| Section `h2` | `clamp(15px, 0.6vw + 13px, 19px)` | 15px |
| KPI value `.kpi .v` | `clamp(22px, 1.5vw + 16px, 30px)` | 22px |
| Table cell (default) | `clamp(12.5px, 0.3vw + 11.6px, 13.5px)` | 12.5px |
| Table cell (Price headline) | `clamp(15px, 0.6vw + 13px, 17px)` | 15px |
| Subline / `.sub` / `.subnum` | `clamp(11px, 0.2vw + 10.4px, 12px)` | 11px |
| Small-caps eyebrow / `.k` / table `<th>` | `clamp(10px, 0.15vw + 9.5px, 11.5px)` | 10px |
| Tooltip / popover body | `clamp(12px, 0.25vw + 11.4px, 13px)` | 12px |
| Footer / fine print | `clamp(11px, 0.15vw + 10.6px, 12px)` | 11px |

These floors override any media query. The phone breakpoint may *fix* a value at the floor (e.g. body 14px) but must never go lower.

### 14.5 Layout & component rules

- **Page container:** `max-width:1180px`, side padding 40px, top 56px, bottom 80px. Do not go to 1480px+ wide layouts.
- **Masthead** (replaces hero card): newspaper-style — 3px black top rule, 1px hairline bottom rule. Contains: eyebrow (small-caps category), headline, dek subhead (≤ 780px wide), and a meta row (generated time, FX rate, data source, next event). **Do not** use dark gradient blocks, glow circles, or box-shadow.
- **Warning callout:** `--surface-2` background + 3px `--neg` left rule + a small `badge` chip. Bullet list may use 2-column `columns`, each item ≤ 1.5 lines. **Do not** use a saturated red wash.
- **KPI strip:** horizontal 4-column strip. 1px hairline top and bottom; 1px hairline between columns. Do not use individual cards with box-shadow and colored top bars. Each cell contains: small-caps label, big number, small delta line.
- **Section heading (`section-head`):** `h2` on the left, small `sub` on the right (`--muted`), 1px hairline below. **Do not** add gradient bars or color rails before `h2`.
- **Charts:**
  - Donut: SVG `circle` with `stroke-dasharray`. Center shows total. Radius 42, stroke-width 20. Slice colors come from `--accent`, `--pos`, `--accent-warm`, `--info`, `--warn`. **No** neon-blue / cyan gradients.
  - Bar chart: track 6px tall, `#ebe7da` background, `border-radius:2px`. Bar uses solid color (default `--ink`; for signed values use `--pos` / `--neg` / `--warn` / `--info`). **No** 18px-thick bars with linear-gradient fills.
- **Table:** 1px `--ink` top and bottom rule. Row dividers 1px `--hairline`. Header is sticky (`position:sticky; top:0`) with opaque `var(--paper)` background, `z-index:var(--table-header-z)`, small-caps `--muted`, and a 1px bottom shadow/rule so scrolling body rows cannot cover it. Hover row uses `--surface-2`. Numeric cells `text-align:right` + tabular-nums. Ticker weight 680. Category chip uses thin-bordered `tag`.
- **Symbol cell trigger** (`div.sym-trigger[tabindex="0"][role="button"]`): inherits font from cell, no background, no border, padding 0, `cursor:help`, dotted underline on hover or focus. Looks like plain text until probed.
- **Price cell trigger:** same chrome-free styling. The cell wraps `price + .sub move` inside the trigger so the whole price block is hoverable and the popover anchors correctly.
- **Popover (`.pop`):** `--surface` background, `--ink` text, padding 12–14px, border-radius 4px, `box-shadow:0 6px 20px rgba(15,25,31,.10), 0 1px 2px rgba(0,0,0,.04)` on desktop and a stronger bottom-sheet shadow on mobile. Desktop uses `width:max-content`, `min-width:min(300px, calc(100vw - 64px))`, and `max-width:min(560px, calc(100vw - 64px))`; do not use a narrow fixed width that causes avoidable wrapping. Tablet / phone uses fixed bottom-sheet placement, safe-area insets, high z-index, `max-height:min(72vh, calc(100dvh - 32px))`, internal scrolling, and long-text wrapping. Inner table uses 11.5px tabular numerics; desktop lot-table cells stay `white-space:nowrap`, while mobile/touch sheets restore normal wrapping.
- **Risk heatmap:** 5-column grid. Cells separated by 1px hairline (not gap). Each cell carries a 3px left risk rule (low / mid / high = light blue / amber / red). Cell contents: ticker, `Risk N/10`, `weight · move`. **Do not** flood the cell with saturated background color.
- **Action list:** 84px label column on the left (translated per SETTINGS), description on the right. Rows separated by dotted hairline.
- **Border-radius:** keep page-wide radius in **2–4px**. Only chips / badges may go to 3–4px; bar tracks 2px. Popovers may go to 4px. **Never** use radius ≥ 8px. **Never** use `border-radius:999px` (pill) on cards, bars, or tracks.
- **Shadow:** as a rule, no box-shadow on the page. Popovers are the single exception. Hover hints cap at `0 1px 0 rgba(0,0,0,.04)`. **Never** ship `0 10px 28px rgba(...)` floating shadows on regular content.
- **Separation hierarchy:** prefer hairline (1px) + whitespace; then semantic color; only then a faint background tint.

### 14.6 Price-cell static styling

```css
.price-cell{position:relative;}
.price-trigger{
  display:inline-flex;
  flex-direction:column;
  align-items:flex-end;
  gap:2px;
  cursor:help;
}
.price-num{
  color:var(--ink);
  font-size:clamp(15px, 0.6vw + 13px, 17px);
  font-weight:650;
  line-height:1.12;
  font-variant-numeric:tabular-nums lining-nums;
}
.price-sub{
  color:var(--muted);
  font-size:clamp(11px, 0.2vw + 10.4px, 12px);
  font-variant-numeric:tabular-nums lining-nums;
}
.price-sub.pos{color:var(--pos);}
.price-sub.neg{color:var(--neg);}
```

### 14.7 Responsive / mobile (RWA) breakpoints

The HTML must include `<meta name="viewport" content="width=device-width, initial-scale=1">` and three breakpoint tiers. **Treat phone behavior as a first-class concern — most quick re-checks happen on a phone.**

| Tier | Range | What changes |
|---|---|---|
| Desktop | ≥ 881px | Default layout — all multi-column grids active, no horizontal scroll. Body 14.5–15.5px, table 13–13.5px |
| Tablet | 601–880px | KPI strip → 2 cols. `cols-2` / `cols-3` → 1 col. Donut + bars stack. Risk heatmap → 2 cols. Body 14–14.5px, table 13px. Bar-row label width tightens |
| Phone | ≤ 600px | KPI strip → 1 col. Risk heatmap → 1 col. Holdings table is wrapped in `.tbl-wrap` with horizontal scroll. **First column (Symbol) is `position:sticky; left:0; z-index:1` with a 1px shadow** so the user never loses row context while scrolling; **the header's first cell must override back to `z-index:calc(var(--table-header-z) + 1)` and `background:var(--paper)`** so it stays above row cells. **Body 14px floor, table 12.5px floor, sublines 11px floor — never lower.** Footer / legend density tightens. Action labels narrow to a 64px column |

**Required wrappers and patterns:**

- The holdings table is always wrapped in `.tbl-wrap`:
  ```html
  <div class="tbl-wrap"><table>…</table></div>
  ```
  Desktop `.tbl-wrap` must **not** set `overflow-x:auto`; otherwise browsers may clip descendant popovers. Enable `overflow-x:auto` and `-webkit-overflow-scrolling:touch` only at tablet / phone breakpoints, where popovers switch to fixed bottom sheets. Keep a negative left/right margin equal to the page's side padding and a `min-width` on the inner table (≥ 680px on phone, ≥ 760px on tablet) so the layout doesn't collapse into illegibility.
- **Sticky first column on phone:** applies to both `th:first-child` and `td:first-child`, with `background:var(--surface)` so cells don't bleed through during scroll, and a 1px right shadow (`box-shadow:1px 0 0 var(--hairline)`) as the affordance edge. Add a later `thead th:first-child{z-index:calc(var(--table-header-z) + 1);background:var(--paper)}` override because the generic first-column rule otherwise lowers the sticky header's z-index.
- **KPI strip on phone:** collapse to 1 column with row borders. Numeric value font respects the `clamp()` floor.
- All cells that use `border-right` or `border-left` for column-style separation must have those properties **reset** under the phone breakpoint to avoid orphan rules.
- **Touch targets** (popover triggers, links inside tables) must remain **≥ 30px tall** on phone.
- **Test the report at 360px width before shipping.** Open in iOS Safari and Chrome Mobile. Verify the popovers position correctly and never clip outside the viewport.

### 14.8 Anti-patterns (must avoid)

- Dark gradient hero (`linear-gradient(135deg,#0b1220,...)`).
- Heavy box-shadow (`0 10px 28px rgba(...)` or stronger) on regular content (popovers excepted).
- Saturated background washes (red / blue / green flooding a region).
- Heading weights ≥ 800.
- Pill border-radius (999px) on cards, bars, tracks.
- Multiple `<style>` blocks overriding each other. The new spec allows **one** `<style>` block, ordered: tokens → base → layout → components.
- Loading any external font (Google Fonts, `@font-face` over the network).
- Reintroducing IRR or annualized-return columns (see §9.4).
- Bilingual or English-fallback labels in any cell, header, or button when SETTINGS specifies a non-English language (see §5).
- Visible font sizes below the floors in §14.4.

### 14.9 Reference implementation

`reports/_sample_redesign.html` **CRITICAL — MUST READ** is the canonical reference. New reports must align color, typography, layout, and component styling with this file. If it is missing, rebuild from the tokens and rules in this section.

---

