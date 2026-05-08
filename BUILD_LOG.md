# leka-product-catalogs — Build Log

## v1.2.0 — 2026-05-08

**Summary:** Storefront card polish across all brands — photo-first thumbnails, cleaner overlay, Vortex theme + logo.

**Files added:**
- `medusa-storefront/src/lib/image-scoring.ts` — `scoreImage`/`pickPrimaryImage`/`sortImagesByScore` (penalize drawings/CAD/certs, reward photos/renders/heroes)
- `medusa-storefront/public/placeholder-product.svg` — graceful fallback when an image URL fails
- `medusa-storefront/public/vortex-logo.svg` — copy of the Vortex wordmark, now `fill="currentColor"`

**Files modified:**
- `medusa-storefront/src/components/product-card.tsx` — uses `pickPrimaryImage`, moves the series/collection name out of the image overlay into the body row, adds `onError` swap to the placeholder
- `medusa-storefront/src/components/vendors/vendor-product-card.tsx` — uses `pickPrimaryImage`, adds `onError` to all four existing branches, adds a new `vortex` branded card
- `medusa-storefront/src/app/[brand]/[handle]/product-detail.tsx` — gallery reorders via `sortImagesByScore` so the default-selected image is the best photo
- `medusa-storefront/src/lib/vendor-themes.ts` — adds the `vortex` theme (navy primary `#000732`, cyan accent `#00B7E4`, white header for strong logo contrast)
- `medusa-storefront/src/components/vendors/vendor-header.tsx` — `VendorLogotype` `case "vortex"` renders the SVG wordmark inheriting `currentColor`
- `medusa-storefront/next.config.js` — whitelists `vortex-intl.com` and `cdn.vortex-intl.com` alongside the existing `www.vortex-intl.com`
- `vortex-catalog/web-app/public/assets/vortex-logo.svg` — adds `fill="currentColor"` so `.brand-logo { color: ... }` actually drives the logo color
- `scripts/sync_vendors_to_medusa.py` — sorts `images[]` by the same scoring rule before assigning `thumbnail = images[0]`, so freshly synced products store the best-photo first

**Outcome:** TypeScript clean (tsc --noEmit). Cards across Wisdom/Vinci/Vortex now lead with product photos; collection name lives in the body and truncates instead of wrapping; Vortex header renders the wordmark in deep navy on white.

---

## v1.1.0 — 2026-05-06

**Summary:** Vendor-specific storefront theming for 4 brands (Berliner, Eurotramp, Rampline, 4soft).

**Files added:**
- `medusa-storefront/src/lib/vendor-themes.ts` — theme registry (colors, hero, origin tagline per vendor)
- `medusa-storefront/src/components/vendors/vendor-header.tsx` — branded header with logotype treatment + accent-colored cart button
- `medusa-storefront/src/components/vendors/vendor-hero.tsx` — full-width gradient hero banner above product grid
- `medusa-storefront/src/components/vendors/vendor-product-card.tsx` — per-vendor card styles (Berliner: industrial left-border; Eurotramp: rounded + red underline; Rampline: minimal Nordic; 4soft: playful pastel)

**Files modified:**
- `medusa-storefront/src/app/[brand]/layout.tsx` — uses `VendorHeader` for themed brands, generic header for wisdom/vinci/vortex
- `medusa-storefront/src/app/[brand]/catalog-content.tsx` — renders `VendorHero` + `VendorProductCard` when theme exists; falls back to generic components

**Outcome:** TypeScript clean (tsc --noEmit). Wisdom, Vinci Play, and Vortex Aquatics are unaffected (no theme entry = generic layout). Next step: deploy to Cloud Run and verify on `catalogs.leka.studio`.

---

## v1.0.0 — (prior)

Initial storefront with 7 vendor brands, generic shared layout, Medusa backend integration, GCS product images.
