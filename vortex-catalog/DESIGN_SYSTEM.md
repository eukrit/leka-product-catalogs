# Vortex Aquatics — Design System

Derived from live tokens on [www.vortex-intl.com](https://www.vortex-intl.com) (WordPress theme `vortex`), extracted from the compiled theme stylesheet on 2026-04-21.

Source: `https://www.vortex-intl.com/wp-content/themes/vortex/dist/styles/main_4d2020b1.css`

Use these tokens (NOT Leka's tokens) in [web-app/public/styles.css](web-app/public/styles.css). The Leka tokens (purple #8003FF, Manrope) stay on `catalogs.leka.studio` parent brand; the Vortex catalog is a sub-brand with its own identity.

---

## Color tokens

Ranked by usage frequency in the live theme CSS (most-used first):

| Token | Hex | Usage count | Role |
|---|---|---|---|
| `--vortex-blue` | `#153cba` | 132 | **Primary brand** — dark water blue. Buttons (`.linkround--blue`, `.vortex-form__submit`, CTA fills), links, headings-on-light. |
| `--vortex-white` | `#ffffff` | 119 | Surfaces, header background on light pages |
| `--vortex-magenta` | `#ff33d4` | 95 | **Hot accent** — used on link hover (`--clear:hover`, `--transparent:hover`, `--white:hover`, `--grey:hover`), CTA hover states, focus. Playful counterpoint to the navy blue. |
| `--vortex-black` | `#000000` | 63 | Hero text on light, default body text |
| `--vortex-grey-50` | `#f2f2f2` | 18 | Card/section backgrounds, product page body bg (observed via inline `background-color: #f2f2f2` on product pages) |
| `--vortex-grey-500` | `#757575` | 18 | Secondary text, meta labels (`.title--grey`) |
| `--vortex-cyan` | `#6ed4fc` | 15 | **Secondary accent** — light cyan "water" highlight |
| `--vortex-yellow` | `#ffe000` | 11 | Tertiary accent (highlights, badges) |
| `--vortex-red` | `#d72500` | 11 | Error / validation |
| `--vortex-navy-deep` | `#000732` | 2 | Deepest navy for display type |

### Semantic aliases (use these in component CSS)

```css
--color-primary: var(--vortex-blue);      /* #153cba */
--color-accent:  var(--vortex-magenta);   /* #ff33d4 */
--color-water:   var(--vortex-cyan);      /* #6ed4fc */
--color-bg:      var(--vortex-grey-50);   /* #f2f2f2 */
--color-surface: var(--vortex-white);     /* #ffffff */
--color-text:    var(--vortex-black);     /* #000 */
--color-text-muted: var(--vortex-grey-500); /* #757575 */
--color-border:  #dddddd;
```

---

## Typography

Two families, both already Google Fonts:

| Role | Family | Weights used | Source |
|---|---|---|---|
| Headings / display | **Work Sans** | 500, 600, 700, 800 | `font-family: Work Sans, sans-serif !important` on hero titles / `.title--*` |
| Body / UI | **Nunito** | 400, 500, 600, 700 | `font-family: Nunito, sans-serif` on paragraphs, buttons, nav |

Google Fonts import:
```html
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;500;600;700&family=Work+Sans:wght@500;600;700;800&display=swap" rel="stylesheet">
```

Type scale (observed):
- Display: 48–64px, Work Sans 700, uppercase on some sections
- H1: 36–44px, Work Sans 700
- H2: 28–32px, Work Sans 600
- Body: 16px, Nunito 400, line-height 1.5
- Small / meta: 13–14px, Nunito 500, uppercase, letter-spacing 0.05em

---

## Shape tokens

| Token | Value | Notes |
|---|---|---|
| `--radius-card` | `12px` | Product cards, modals (slightly larger than Leka's 16px feel in their sharper layout) |
| `--radius-button` | `9999px` | Pill buttons (`.linkround` uses fully-rounded pill — confirmed in theme CSS `.linkround` class shape) |
| `--radius-pill` | `9999px` | Badges, chips |
| `--shadow-card` | `0 4px 8px rgba(0,0,0,0.1)` | Hover elevation (directly from theme: `box-shadow: 0 4px 8px 0 rgba(0,0,0,.1)`) |
| `--shadow-hero` | `0 10px 40px rgba(21,60,186,0.16)` | Hero/CTA tint — custom, blue-tinted |

---

## Logo

- **Source**: SVG sprite symbol `#vortex-logo` from `https://www.vortex-intl.com/wp-content/themes/vortex/dist/images/svg_map_68028944.svg`
- **Local copy**: [web-app/public/assets/vortex-logo.svg](web-app/public/assets/vortex-logo.svg)
- **viewBox**: `0 0 192 41` (wordmark, ~4.7:1 aspect ratio)
- **Usage**: Header, ~160px wide. Keep `fill` defaulted so it inherits `currentColor` — color the parent to `--vortex-blue` on light backgrounds, `#fff` on dark.

---

## Application rules

1. **Primary buttons**: pill shape, filled `--vortex-blue`, white text, hover → `--vortex-magenta` background + 4px shadow
2. **Secondary buttons**: pill shape, transparent bg, 1px `--vortex-blue` border, blue text, hover → magenta border + text
3. **Cards**: white surface, 12px radius, `--shadow-card` on hover, magenta underline on title hover
4. **Filter chips / badges**: pill, cyan bg, navy text
5. **Links**: `--vortex-blue`, hover → `--vortex-magenta`, underline on hover only
6. **Section backgrounds**: alternate `--color-bg` (#f2f2f2) and `--color-surface` (white) for rhythm
7. **Hero**: dark navy (`--vortex-navy-deep` or gradient from `--vortex-blue` to `--vortex-navy-deep`), white display type, cyan/magenta accents

---

## Verification

Spot-check against the live site (hit with a browser, inspect element):
- Footer link color matches `#153cba` ✓
- Hover state on "Products" nav link turns `#ff33d4` ✓
- Work Sans loads for headings (`H1`, `.title.title--black`) ✓
- Nunito loads for body text (`p`, `.linkround`) ✓
