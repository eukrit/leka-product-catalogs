# Handoff: Build Vendor-Specific Storefront Pages

**Status:** Ready to start
**Owner:** Next Claude session
**Created:** 2026-04-11
**Goal:** Replace the generic shared storefront layout with vendor-specific designs that match each vendor's website branding.

---

## Current State

All 6 brand catalogs share **one** generic Leka-branded layout at `/{brand}` and `/{brand}/[handle]`. The brand differentiation is limited to:
- A colored letter avatar in the header
- Brand name + description
- Product count

**This is not enough.** Each vendor has a strong brand identity on their own website that customers expect when browsing their catalog. We need to build distinct, branded experiences per vendor while keeping the same Medusa backend, cart, checkout, and account flows.

### What stays shared (DO NOT change):
- `/` landing page (brand selector)
- Cart, checkout, account, order pages
- Medusa client, auth, cart libs
- API integration patterns
- The Leka design system as the *fallback*

### What becomes vendor-specific:
- Per-vendor catalog page (`/{brand}/page.tsx`)
- Per-vendor product detail page (`/{brand}/[handle]/page.tsx`)
- Per-vendor brand layout (header, footer, colors, typography)
- Per-vendor product card style
- Per-vendor hero/banner sections

---

## Vendor Design Sources

For each vendor, study their live website to extract:
- Color palette (primary, secondary, accent, background, text)
- Typography (font families, weights, sizes, line heights)
- Logo (download SVG/PNG and put in `public/logos/{vendor}.svg`)
- Hero/banner imagery and treatment
- Product card style (image ratio, badge style, hover states)
- Header/navigation pattern
- Footer style
- Spacing and layout grid
- Iconography
- CTA button style

| Vendor | Website | Slug | Sales Channel | Color Direction |
|--------|---------|------|---------------|-----------------|
| Berliner Seilfabrik | https://www.berliner-seilfabrik.com | `berliner` | sc_01KNQAA3QDYHP15Y9K4PPRMDF0 | Industrial / orange + black, technical aesthetic |
| Eurotramp | https://www.eurotramp.com | `eurotramp` | sc_01KNQAA3Y72W17B7CP2VQ93T3M | Sport / red + white, athletic feel |
| Rampline | https://www.rampline.no | `rampline` | sc_01KNQAA448RY0YPR51FNPM2TVA | Norwegian / minimal, lots of whitespace, action photography |
| 4soft | https://www.4soft.cz | `4soft` | sc_01KNQAA4A8SF4ZT9S8N0AHGY3Y | Playful / bright multicolor, kids-focused |
| Wisdom | (catalog only, no public site) | `wisdom` | sc_01KNKTHC0B7KFEDSZ3NNM49JQW | Stay with current Leka design |
| Vinci Play | https://www.vinci-play.com | `vinciplay` | sc_01KNKTHC77716EPCE3E2BKAMQP | Existing magenta+navy works, keep it |

For Wisdom and Vinci Play, the current design is already acceptable. The work is for the **4 vendor brands**.

---

## Architecture Plan

### File structure (proposed)

```
medusa-storefront/src/
├── app/
│   ├── [brand]/
│   │   ├── page.tsx                    # Server component, picks the right layout
│   │   ├── catalog-content.tsx         # Generic fallback (current code)
│   │   ├── [handle]/
│   │   │   ├── page.tsx                # Server component, picks the right detail
│   │   │   └── product-detail.tsx      # Generic fallback (current code)
│   │   ├── layout.tsx                  # Generic fallback header/footer
│   │   ├── (vendor-pages)/             # Vendor-specific pages — NEW
│   │   │   ├── berliner/
│   │   │   │   ├── catalog.tsx
│   │   │   │   ├── product-detail.tsx
│   │   │   │   └── layout.tsx
│   │   │   ├── eurotramp/
│   │   │   ├── rampline/
│   │   │   └── 4soft/
├── styles/
│   ├── vendors/                        # Per-vendor CSS modules — NEW
│   │   ├── berliner.module.css
│   │   ├── eurotramp.module.css
│   │   ├── rampline.module.css
│   │   └── 4soft.module.css
├── components/
│   ├── vendors/                        # Per-vendor reusable components — NEW
│   │   ├── berliner/
│   │   │   ├── ProductCard.tsx
│   │   │   ├── HeroBanner.tsx
│   │   │   └── Header.tsx
│   │   ├── eurotramp/
│   │   ├── rampline/
│   │   └── 4soft/
└── lib/
    └── vendor-themes.ts                # Theme registry — NEW
```

### Implementation pattern

The brand layout / page should branch based on vendor slug:

```tsx
// app/[brand]/page.tsx
import { getBrand } from "@/lib/medusa-client"
import { getVendorTheme } from "@/lib/vendor-themes"

export default async function BrandPage({ params }) {
  const { brand } = await params
  const VendorCatalog = getVendorTheme(brand)?.Catalog ?? GenericCatalog
  return <VendorCatalog brandSlug={brand} />
}
```

The `vendor-themes.ts` registry maps slugs to vendor-specific React components plus theme tokens.

---

## Per-Vendor Build Steps

Repeat for each of the 4 vendors:

### Step 1 — Capture design tokens
1. Open the vendor website with browser dev tools
2. Sample colors (primary, secondary, accent, neutral, success, error)
3. Identify font families (computed-style on body and headings)
4. Download the logo (SVG preferred; right-click → Inspect → find the SVG / image URL)
5. Take 3-4 screenshots: home page, product listing, product detail, footer
6. Save to `public/logos/{vendor}.svg` and `docs/design-refs/{vendor}/`

### Step 2 — Build the theme module
Create `medusa-storefront/src/lib/vendor-themes/{vendor}.ts` exporting:
```ts
export const berlinerTheme = {
  colors: { primary: "#FF6B00", text: "#1A1A1A", bg: "#FFFFFF", accent: "#000000" },
  fonts: { heading: "'Roboto Slab', serif", body: "'Inter', sans-serif" },
  logo: "/logos/berliner.svg",
  hero: { image: "/hero/berliner.jpg", tagline: "Rope Play Since 1865" },
}
```

### Step 3 — Build the layout component
`components/vendors/{vendor}/Header.tsx` — vendor logo, nav links matching their site, locale switcher, cart button.
`components/vendors/{vendor}/Footer.tsx` — vendor company info, links, certifications, contact.

### Step 4 — Build the catalog page
`app/[brand]/(vendor-pages)/{vendor}/catalog.tsx` — wraps the existing data-fetching logic but renders with the vendor's visual language. Use the vendor's product card style (e.g., Berliner uses square cards with thick borders, Eurotramp uses rounded with red accents).

### Step 5 — Build the product detail page
`app/[brand]/(vendor-pages)/{vendor}/product-detail.tsx` — same data, vendor-specific layout. Some vendors emphasize technical specs heavily (Berliner's safety certifications), others lead with imagery (Rampline's lifestyle photos).

### Step 6 — Register in vendor-themes.ts
```ts
import { berlinerTheme } from "./vendor-themes/berliner"
import BerlinerCatalog from "@/app/[brand]/(vendor-pages)/berliner/catalog"
import BerlinerLayout from "@/app/[brand]/(vendor-pages)/berliner/layout"
// ...
export const VENDOR_THEMES = {
  berliner: { theme: berlinerTheme, Catalog: BerlinerCatalog, Layout: BerlinerLayout },
  // ...
}
```

### Step 7 — Wire the brand layout to use vendor layout
Update `app/[brand]/layout.tsx` to fetch the vendor layout from the registry and fall back to the current generic one for `wisdom` and `vinciplay`.

### Step 8 — Test
- All 6 brands accessible at `/{brand}`
- Each vendor has distinct visual identity
- Cart, checkout, account still work (these stay generic)
- Mobile responsive
- SEO metadata still applied (already done in current code via `generateMetadata`)

---

## Reference Files

### Existing storefront code (read these first)
- `medusa-storefront/src/app/[brand]/layout.tsx` — current generic layout
- `medusa-storefront/src/app/[brand]/page.tsx` — server component wrapper (already has `generateMetadata`)
- `medusa-storefront/src/app/[brand]/catalog-content.tsx` — current catalog client
- `medusa-storefront/src/app/[brand]/[handle]/page.tsx` — server component wrapper
- `medusa-storefront/src/app/[brand]/[handle]/product-detail.tsx` — current detail client
- `medusa-storefront/src/components/product-card.tsx` — current generic card
- `medusa-storefront/src/lib/medusa-client.ts` — brand registry (BRANDS map)
- `medusa-storefront/tailwind.config.ts` — current Leka design tokens

### Backend / data
- All 991 vendor products are live in Medusa with `metadata.brand_slug` set
- Images are served from GCS: `https://storage.googleapis.com/ai-agents-go-documents/product-images/{vendor}/{handle}/...`
- Medusa backend: https://leka-medusa-backend-538978391890.asia-southeast1.run.app
- Each vendor has its own publishable key (already wired in `medusa-client.ts`)

### Deployment
- Cloud Run service: `leka-medusa-storefront` (asia-southeast1)
- Manual build submit: see commit `8c760c7` for the working pattern (Cloud Build trigger from GitHub push isn't auto-firing — investigate `7cd91f80-0871-43b2-8ff9-e44cc032a542` trigger)
- Custom domain: `catalogs.leka.studio` → `leka-medusa-storefront`

### Production safeguards
- Wisdom and Vinci Play already have customers — DO NOT break their flows
- Feature-flag the vendor pages if needed (e.g., env var `VENDOR_THEMES_ENABLED=true`)
- Test on direct Cloud Run URL before relying on the custom domain
- All public-facing changes should respect `mandatory_copyright_requirements` — don't copy vendor websites verbatim, just match the visual style

---

## Suggested Order of Work

1. **Set up the architecture** — vendor-themes.ts registry, file structure, generic fallback wired through. Ship this with no visible changes (still uses generic for everyone).
2. **Berliner first** (largest vendor, 466 products, most complex content) — full implementation as the reference.
3. **Eurotramp** — sportier feel, simpler than Berliner.
4. **Rampline** — minimal Scandinavian, mostly typography work.
5. **4soft** — playful and colorful, most divergent from Leka style.
6. **QA pass** — each vendor on mobile + desktop, dark images on different backgrounds, long product titles, missing data states.
7. **Deploy and verify on `catalogs.leka.studio`**.

Estimated effort: 4-6 sessions, one per vendor + one for architecture + one for QA.

---

## Out of Scope (Explicitly)

- Translations — handled separately (see `lib/i18n.ts`)
- Image re-hosting — already done (7,281 images uploaded to GCS)
- New product imports — vendor catalog already complete
- Backend changes — Medusa stays as-is
- Payment provider configuration — already manual provider linked
- Shipping options — already configured (Standard FOB free + Express $50)
- Admin UI — separate concern, fix CORS deployment
- Custom domain DNS — already pointed to `ghs.googlehosted.com`

---

## Open Questions for the Next Session

1. Do we want each vendor's storefront to feel like a clone of their site, or just inspired by it? (Recommend: inspired — fully cloning has copyright concerns and dilutes Leka as the platform.)
2. Should we add a "Powered by Leka" badge or footer to each vendor page? (Recommend: yes, small, in the footer.)
3. Do we want vendor-specific URLs like `berliner.catalogs.leka.studio` or stick with path-based `catalogs.leka.studio/berliner`? (Recommend: path-based for now — subdomain mapping adds Cloud Run cert work.)
4. Should the cart be shared across vendors or per-vendor? Currently per-vendor (good — keep it).
5. Any vendor-specific feature requests (configurators, custom dimensions, request-quote forms)?

---

## Quick Start for Next Session

```
cd "C:\Users\Eukrit\OneDrive\Documents\Claude Code\leka-product-catalogs"
claude
```

Then:
> Read `docs/HANDOFF_VENDOR_STOREFRONTS.md` and start with Step 1 — set up the vendor-themes architecture, then build the Berliner Seilfabrik storefront as the reference implementation. Source design tokens from https://www.berliner-seilfabrik.com.
