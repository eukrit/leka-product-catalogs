# Eurotramp Image Audit — 2026-05-30

Source: live Medusa backend `https://leka-medusa-backend-538978391890.asia-southeast1.run.app`

## Why this audit re-classifies images

The catalogs storefront image scorer (v0.19.2) treats anything that isn't a regex-matched cert as a candidate product photo. In practice many Medusa Eurotramp images are *feature badges* (`madeingermany_*.jpg`, `uv-lightresistant_*.jpg`), *UI symbols* (`symbol-*`), *placeholders* (`placeholder.jpg`), or *vector drawings* (`vector-*`). None of those are product photographs.

This audit classifies each Medusa image as one of:

- `photo` — leading article number, `productdetails-`, or `-preview-` (real photo)
- `cert` — TÜV / GS / ISO / compliance
- `feature-badge` — feature-wording-as-filename (made-in-germany, uv-light-resistant, …)
- `symbol` — `symbol-*` or `mediaType-*` UI icons
- `vector` — CAD line drawings (`vector-*`)
- `merchant` — distributor logos
- `placeholder` — literal `placeholder.jpg`
- `unknown` — anything else (conservative: treated as not-a-photo)

**Backfill target** = `photo_count == 0` — at least one real product photo must be added to Medusa.

## Summary

- Total Eurotramp products: **187**
- **Backfill targets (zero real photos in Medusa)**: **27**
  - of which have *only* certs/badges/symbols/etc.: 27
  - of which have **no images at all**: 2
  - of which have at least one cert image: 5
- Products whose `thumbnail` is **not** a real photo: **72**
  - of which thumbnail is a cert image: **10**
- Products that already have ≥1 real photo: **160**

## Backfill targets — products with zero real product photos

These products need real photographs added. Most have only feature badges + the TÜV cert + a vector drawing. The cert image will continue to win on the storefront until a real photo lands in Medusa.

| handle | title | images | photo | cert | badge | symbol | vector | thumb_kind | vendor_url |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| `eurotramp-adhesive-cartridge-for-kids-tramp-impact-protection-e97003` | adhesive cartridge for Kids Tramp impact protection | 1 | 0 | 0 | 0 | 0 | 0 | unknown | — |
| `eurotramp-bonded-impact-protection-system-kids-tramp-xl-e97544` | Bonded impact protection system Kids Tramp XL | 0 | 0 | 0 | 0 | 0 | 0 | none | — |
| `eurotramp-booster-board-freestyle` | Booster Board "Freestyle" | 8 | 0 | 0 | 1 | 0 | 0 | feature-badge | [link](https://www.eurotramp.com/en/products/booster-board-freestyle/) |
| `eurotramp-customized-fabrications` | Customized Fabrications | 1 | 0 | 0 | 1 | 0 | 0 | feature-badge | [link](https://www.eurotramp.com/en/products/customized-fabrications/) |
| `eurotramp-eurotramp-play` | Eurotramp PLAY! | 31 | 0 | 0 | 1 | 0 | 8 | feature-badge | [link](https://www.eurotramp.com/en/products/eurotramp-play/) |
| `eurotramp-eurotramp-play-light-epl0001` | Eurotramp PLAY! Light | 3 | 0 | 0 | 0 | 0 | 0 | unknown | — |
| `eurotramp-impactprotection-system-kids-tramp-e97044` | impactprotection system Kids Tramp | 0 | 0 | 0 | 0 | 0 | 0 | none | — |
| `eurotramp-jumping-bed-kids-tramp-kindergarten-e21897` | Jumping bed Kids Tramp Kindergarten | 6 | 0 | 0 | 0 | 0 | 4 | vector | — |
| `eurotramp-jumping-bed-kids-tramp-kindergarten-xl-e21879` | Jumping bed Kids Tramp "Kindergarten" XL | 4 | 0 | 0 | 0 | 0 | 4 | vector | — |
| `eurotramp-kids-tramp-kindergarten-loop` | Kids Tramp "Kindergarten Loop" | 35 | 0 | 1 | 7 | 0 | 1 | cert | [link](https://www.eurotramp.com/en/products/kids-tramp-kindergarten-loop/) |
| `eurotramp-kids-tramp-kindergarten-loop-xl` | Kids Tramp "Kindergarten Loop XL" | 35 | 0 | 1 | 7 | 0 | 1 | cert | [link](https://www.eurotramp.com/en/products/kids-tramp-kindergarten-loop-xl/) |
| `eurotramp-kids-tramp-playground-loop` | Kids Tramp "Playground Loop" | 36 | 0 | 1 | 9 | 0 | 0 | cert | [link](https://www.eurotramp.com/en/products/kids-tramp-playground-loop/) |
| `eurotramp-kids-tramp-playground-loop-xl` | Kids Tramp "Playground Loop XL" | 36 | 0 | 1 | 9 | 0 | 0 | cert | [link](https://www.eurotramp.com/en/products/kids-tramp-playground-loop-xl/) |
| `eurotramp-safety-platforms-universal-freestyle` | Safety platforms "Competition Universal" | 1 | 0 | 0 | 0 | 0 | 0 | unknown | [link](https://www.eurotramp.com/en/products/safety-platforms-universal-freestyle/) |
| `eurotramp-set-of-landing-mats-dmt` | Set of landing mats | 3 | 0 | 0 | 0 | 0 | 0 | unknown | [link](https://www.eurotramp.com/en/products/set-of-landing-mats-dmt/) |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97006` | single tile impact protection Kids Tramp Track centrepiece | 2 | 0 | 0 | 0 | 0 | 0 | unknown | — |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97008` | single tile impact protection Kids Tramp Track centrepiece | 2 | 0 | 0 | 0 | 0 | 0 | unknown | — |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97012` | single tile impact protection Kids Tramp Track centrepiece | 2 | 0 | 0 | 0 | 0 | 0 | unknown | — |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97013` | single tile impact protection Kids Tramp Track centrepiece | 1 | 0 | 0 | 0 | 0 | 0 | unknown | — |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-cornerpiece-e97005` | single tile impact protection Kids Tramp track cornerpiece | 2 | 0 | 0 | 0 | 0 | 0 | unknown | — |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-cornerpiece-e97007` | single tile impact protection Kids Tramp track cornerpiece | 1 | 0 | 0 | 0 | 0 | 0 | unknown | — |
| `eurotramp-spotting-mat-freestyle` | Eurotramp Spotting mat "Freestyle" | 1 | 0 | 0 | 0 | 0 | 0 | unknown | [link](https://www.eurotramp.com/en/products/spotting-mat-freestyle/) |
| `eurotramp-trampoline-set-one-field` | Trampoline Set "Stationary" - one jump area | 10 | 0 | 0 | 2 | 0 | 0 | feature-badge | [link](https://www.eurotramp.com/en/products/trampoline-set-one-field/) |
| `eurotramp-trampoline-set-stationary` | Trampoline Set "Stationary" | 13 | 0 | 0 | 5 | 0 | 0 | feature-badge | [link](https://www.eurotramp.com/en/products/trampoline-set-stationary/) |
| `eurotramp-transport-case-hdts` | HDTS transport case | 1 | 0 | 0 | 0 | 0 | 0 | unknown | [link](https://www.eurotramp.com/en/products/transport-case-hdts/) |
| `eurotramp-wehrfritz-fun-round-kindergarten-94750` | Wehrfritz Fun round "Kindergarten" | 3 | 0 | 0 | 0 | 0 | 3 | vector | — |
| `eurotramp-wehrfritz-fun-xl-kindergarten` | Wehrfritz FUN XL "Kindergarten" | 18 | 0 | 1 | 5 | 11 | 1 | cert | [link](https://www.eurotramp.com/en/products/wehrfritz-fun-xl--kindergarten/) |

## Full audit (all Eurotramp products)

| handle | images | photo | cert | badge | symbol | vector | placeholder | unknown | thumb |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `eurotramp-adaption-bars-safety-platform-integral-ultimate` | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-adhesive-cartridge-for-kids-tramp-impact-protection-e97003` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-adhesive-cartridge-for-kids-tramp-impact-protection-e97043` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-albatross` | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-anchor-bar-kids-tramp-e20970` | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-anti-slip-plate-dmt` | 8 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-bonded-impact-protection-kids-tramp-track-10m-e97941` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bonded-impact-protection-kids-tramp-track-4m-e97441` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bonded-impact-protection-kids-tramp-track-6m-e97641` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bonded-impact-protection-kids-tramp-track-8m-e97841` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bonded-impact-protection-system-kids-tramp-e97041` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bonded-impact-protection-system-kids-tramp-loop-e97051` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bonded-impact-protection-system-kids-tramp-loop-xl-e97542` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bonded-impact-protection-system-kids-tramp-xl-e97544` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | ❌ — |
| `eurotramp-bonded-impact-protection-system-wehrfritz-fun-round-e94700` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bonded-impact-protection-system-wehrfritz-fun-xl-e94541` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-booster-board` | 10 | 4 | 0 | 1 | 0 | 1 | 0 | 4 | ❌ feature-badge |
| `eurotramp-booster-board-freestyle` | 8 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-bounce-cloud` | 30 | 2 | 1 | 3 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-bouncecloud-3-piece-combination-green-93020` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bouncecloud-3-piece-combination-orange-93022` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bouncecloud-3-piece-combination-yellow-93021` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bouncecloud-6-piece-combination-green-93030` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bouncecloud-6-piece-combination-orange-93032` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bouncecloud-6-piece-combination-yellow-93031` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bouncecloud-orange-93002` | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bouncecloud-yellow-93001` | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bumper-dorado` | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bumper-teamgym` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-bungee-longe` | 11 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | ❌ placeholder |
| `eurotramp-clamping-jaw-inside-bouncecloud-e44193` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-clamping-jaw-outside-center-bouncecloud-e44194` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-clamping-jaw-outside-corner-bouncecloud-e44195` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-complete-competition-trampoline` | 16 | 7 | 0 | 1 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-concrete-foundation` | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | ✅ photo |
| `eurotramp-customized-fabrications` | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-dorado` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-double-minitramp-190` | 21 | 2 | 0 | 0 | 0 | 0 | 0 | 19 | ✅ photo |
| `eurotramp-eurotramp-play` | 31 | 0 | 0 | 1 | 0 | 8 | 0 | 0 | ❌ feature-badge |
| `eurotramp-eurotramp-play-light-epl0001` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | ❌ unknown |
| `eurotramp-eurotramp-spotting-mat` | 15 | 7 | 0 | 0 | 0 | 0 | 0 | 1 | ✅ photo |
| `eurotramp-fivesquare` | 11 | 2 | 0 | 1 | 0 | 0 | 0 | 1 | ❌ feature-badge |
| `eurotramp-frame-bouncecloud-e41093` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-frame-pads-set-80mm-safety-plus` | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-grand-master` | 38 | 16 | 1 | 1 | 0 | 1 | 0 | 19 | ✅ photo |
| `eurotramp-grand-master-exclusiv` | 38 | 17 | 0 | 0 | 0 | 1 | 0 | 20 | ✅ photo |
| `eurotramp-grand-master-exclusiv-open-end` | 21 | 2 | 0 | 0 | 0 | 0 | 0 | 19 | ✅ photo |
| `eurotramp-ground-trampoline-freestyle` | 24 | 9 | 0 | 1 | 0 | 0 | 0 | 14 | ❌ feature-badge |
| `eurotramp-ground-trampoline-indoor` | 13 | 6 | 1 | 1 | 0 | 1 | 0 | 4 | ✅ photo |
| `eurotramp-ground-trampoline-outdoor` | 22 | 11 | 1 | 5 | 0 | 0 | 0 | 5 | ✅ photo |
| `eurotramp-hdts` | 14 | 1 | 0 | 1 | 0 | 0 | 0 | 12 | ❌ feature-badge |
| `eurotramp-hobbytramp` | 9 | 2 | 0 | 0 | 0 | 0 | 1 | 6 | ✅ photo |
| `eurotramp-icepad` | 10 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-impact-protection-system` | 30 | 4 | 0 | 3 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-impactprotection-system-kids-tramp-e97044` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | ❌ — |
| `eurotramp-jumping-bed-kids-tramp-kindergarten-e21897` | 6 | 0 | 0 | 0 | 0 | 4 | 0 | 2 | ❌ vector |
| `eurotramp-jumping-bed-kids-tramp-kindergarten-xl-e21879` | 4 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | ❌ vector |
| `eurotramp-jumping-bed-kids-tramp-playground-additional-coating-e21898b` | 6 | 5 | 0 | 0 | 0 | 1 | 0 | 0 | ❌ vector |
| `eurotramp-jumping-bed-kids-tramp-playground-e21898` | 6 | 5 | 0 | 0 | 0 | 1 | 0 | 0 | ❌ vector |
| `eurotramp-jumping-bed-kids-tramp-playground-xl-additional-coating-e21899b` | 6 | 5 | 0 | 0 | 0 | 1 | 0 | 0 | ❌ vector |
| `eurotramp-jumping-bed-kids-tramp-playground-xl-e21899` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-kids-tramp-track-playground-10m-e21009` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-kids-tramp-track-playground-4m-e21004` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-kids-tramp-track-playground-6m-e21006` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-kids-tramp-track-playground-8m-e21008` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-wehrfritz-fun-round-kindergarten-e21950` | 6 | 4 | 0 | 0 | 0 | 2 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-wehrfritz-fun-round-playground-additional-coating-e21947b` | 6 | 4 | 0 | 0 | 0 | 2 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-wehrfritz-fun-round-playground-e21947` | 6 | 4 | 0 | 0 | 0 | 2 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-wehrfritz-fun-xl-kindergarten-e21945` | 6 | 4 | 0 | 0 | 0 | 2 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-wehrfritz-fun-xl-playground-additional-coating-e21946b` | 6 | 4 | 0 | 0 | 0 | 2 | 0 | 0 | ✅ photo |
| `eurotramp-jumping-bed-wehrfritz-fun-xl-playground-e21946` | 6 | 4 | 0 | 0 | 0 | 2 | 0 | 0 | ✅ photo |
| `eurotramp-kids-tramp-kindergarten` | 36 | 1 | 1 | 7 | 0 | 1 | 0 | 2 | ❌ cert |
| `eurotramp-kids-tramp-kindergarten-loop` | 35 | 0 | 1 | 7 | 0 | 1 | 0 | 2 | ❌ cert |
| `eurotramp-kids-tramp-kindergarten-loop-xl` | 35 | 0 | 1 | 7 | 0 | 1 | 0 | 2 | ❌ cert |
| `eurotramp-kids-tramp-kindergarten-xl` | 36 | 1 | 1 | 7 | 0 | 1 | 0 | 2 | ❌ cert |
| `eurotramp-kids-tramp-playground` | 36 | 1 | 1 | 9 | 0 | 0 | 0 | 1 | ❌ cert |
| `eurotramp-kids-tramp-playground-loop` | 36 | 0 | 1 | 9 | 0 | 0 | 0 | 2 | ❌ cert |
| `eurotramp-kids-tramp-playground-loop-xl` | 36 | 0 | 1 | 9 | 0 | 0 | 0 | 2 | ❌ cert |
| `eurotramp-kids-tramp-playground-xl` | 37 | 1 | 1 | 9 | 0 | 0 | 0 | 2 | ❌ cert |
| `eurotramp-kids-tramp-track-playground` | 24 | 5 | 1 | 9 | 7 | 1 | 0 | 1 | ✅ photo |
| `eurotramp-kids-tramp-track-playground-10m-97049` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-kids-tramp-track-playground-10m-97059` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-kids-tramp-track-playground-4m-97044` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-kids-tramp-track-playground-4m-97054` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-kids-tramp-track-playground-6m-97046` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-kids-tramp-track-playground-6m-97056` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-kids-tramp-track-playground-8m-97048` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-kids-tramp-track-playground-8m-97058` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-landing-mat-cover` | 12 | 1 | 0 | 1 | 0 | 0 | 1 | 2 | ❌ unknown |
| `eurotramp-leaf-spring-bouncecloud-e31196` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-lifting-roller-stand` | 16 | 8 | 0 | 1 | 0 | 0 | 0 | 7 | ❌ feature-badge |
| `eurotramp-lifting-roller-stand-safe-comfort` | 11 | 3 | 0 | 1 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-long-leaf-spring-connecting-cable-e33393` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-master` | 33 | 12 | 1 | 1 | 0 | 1 | 0 | 18 | ✅ photo |
| `eurotramp-mats-tramp` | 9 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | ✅ photo |
| `eurotramp-minitramp-trolley` | 11 | 3 | 0 | 1 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-minitrampoline-112-125` | 42 | 12 | 1 | 1 | 0 | 3 | 6 | 19 | ❌ cert |
| `eurotramp-mounting-tool-kids-tramp-e31100` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-octotramp` | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-open-end-minitramp` | 33 | 10 | 1 | 1 | 0 | 2 | 0 | 19 | ✅ photo |
| `eurotramp-playpro-rubber-protection-lip-for-kids-tramp-e97048` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-playpro-rubber-protection-lip-for-kids-tramp-track-10m-e97948` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-playpro-rubber-protection-lip-for-kids-tramp-track-4m-e97448` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-playpro-rubber-protection-lip-for-kids-tramp-track-6m-e97648` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-playpro-rubber-protection-lip-for-kids-tramp-track-8m-e97848` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-playpro-rubber-protection-lip-for-kids-tramp-xl-e97548` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-playpro-rubber-protection-ring-for-kids-tramp-loop-e97047` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-plug-in-connector-bouncecloud-e93001` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-premium` | 33 | 8 | 0 | 0 | 0 | 0 | 0 | 25 | ❌ placeholder |
| `eurotramp-roller-stand` | 11 | 3 | 0 | 1 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-rubber-protection-bar-kids-tramp-150x150-cm-e97022` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-rubber-protection-bar-kids-tramp-xl-200x200-cm-e97522` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-rubber-protection-bars-kids-tramp-xl-200x200cm-4-sides-e97502` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-rubber-protection-ring` | 16 | 8 | 0 | 0 | 0 | 8 | 0 | 0 | ✅ photo |
| `eurotramp-rubber-protections-bars-kids-tramp-150x150cm-4-pieces-e97002` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-run-up-track-dmt` | 10 | 2 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-safety-platforms-and-safety-mats-integral` | 14 | 9 | 0 | 1 | 0 | 0 | 0 | 4 | ❌ feature-badge |
| `eurotramp-safety-platforms-and-safety-mats-universal` | 21 | 11 | 0 | 1 | 0 | 0 | 0 | 9 | ❌ feature-badge |
| `eurotramp-safety-platforms-universal-freestyle` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-service-bag` | 12 | 4 | 0 | 1 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-set-of-landing-mats-dmt` | 3 | 0 | 0 | 0 | 0 | 0 | 1 | 2 | ❌ unknown |
| `eurotramp-short-leaf-spring-connecting-cable-e33394` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-single-tile-impact-protection-kids-tramp-cornerpiece-e97302` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-cornerpiece-e97303` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-cornerpiece-e97305` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-cornerpiece-e97306` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-cornerpiece-e97402` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-cornerpiece-e97403` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-cornerpiece-e97405` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-cornerpiece-e97406` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-centrepiece-e97308` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-centrepiece-e97408` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-cornerpiece-e97307` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-cornerpiece-e97407` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-xl-centrepiece-left-e97310` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-xl-centrepiece-left-e97410` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-xl-centrepiece-right-e97311` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-xl-centrepiece-right-e97411` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-xl-cornerpiece-e97309` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-loop-xl-cornerpiece-e97409` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97006` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | ❌ unknown |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97008` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | ❌ unknown |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97012` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | ❌ unknown |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97013` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97056` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97058` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-centrepiece-e97059` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-cornerpiece-e97005` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | ❌ unknown |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-cornerpiece-e97007` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-cornerpiece-e97055` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-track-cornerpiece-e97057` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-xl-centrepiece-e97301` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-xl-centrepiece-e97304` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-xl-centrepiece-e97401` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-single-tile-impact-protection-kids-tramp-xl-centrepiece-e97404` | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-somersault-belt-twisting-belt` | 8 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-spieth-ground-safety-mat` | 3 | 1 | 0 | 0 | 0 | 0 | 1 | 1 | ❌ unknown |
| `eurotramp-sport-thieme-adventure-tramp` | 22 | 11 | 1 | 7 | 0 | 0 | 0 | 3 | ✅ photo |
| `eurotramp-sport-thieme-adventure-tramp-built-in-frame` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-spotting-mat-freestyle` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-stability-plate` | 11 | 3 | 0 | 1 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-steel-spring-145x20mm-e31120` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-tchoukball` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-teamgym` | 18 | 7 | 1 | 1 | 0 | 1 | 1 | 7 | ✅ photo |
| `eurotramp-teamgym-freestyle` | 10 | 2 | 0 | 1 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-top-sheet-for-bouncecloud-e21030` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-top-sheet-for-bouncecloud-e21031` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-top-sheet-for-bouncecloud-e21032` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-torsion-spring-left-bouncecloud-e31195` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-torsion-spring-right-bouncecloud-e31194` | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-trampoline-set-freestyle` | 5 | 3 | 0 | 2 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-trampoline-set-one-field` | 10 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-trampoline-set-stationary` | 13 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | ❌ feature-badge |
| `eurotramp-trampoline-track-air-track-plus` | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-trampoline-track-stationary` | 21 | 9 | 0 | 1 | 0 | 1 | 9 | 1 | ❌ feature-badge |
| `eurotramp-trampoline-track-stationary-2` | 21 | 9 | 0 | 1 | 0 | 1 | 9 | 1 | ❌ feature-badge |
| `eurotramp-trampoline-track-vario` | 20 | 9 | 0 | 1 | 0 | 0 | 9 | 1 | ❌ feature-badge |
| `eurotramp-transport-case-hdts` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | ❌ unknown |
| `eurotramp-trimm-tramp` | 9 | 3 | 0 | 0 | 0 | 1 | 0 | 5 | ✅ photo |
| `eurotramp-ultimate` | 62 | 28 | 1 | 2 | 0 | 1 | 0 | 30 | ✅ photo |
| `eurotramp-ultimate-dmt-6x6` | 36 | 8 | 1 | 1 | 0 | 1 | 1 | 24 | ✅ photo |
| `eurotramp-ultimate-freestyle` | 35 | 11 | 1 | 1 | 0 | 0 | 0 | 22 | ✅ photo |
| `eurotramp-underwater-trampoline` | 10 | 1 | 0 | 2 | 0 | 0 | 0 | 0 | ✅ photo |
| `eurotramp-wehrfritz-fun-round` | 16 | 1 | 1 | 5 | 7 | 1 | 1 | 0 | ✅ photo |
| `eurotramp-wehrfritz-fun-round-kindergarten-94750` | 3 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | ❌ vector |
| `eurotramp-wehrfritz-fun-xl-kindergarten` | 18 | 0 | 1 | 5 | 11 | 1 | 0 | 0 | ❌ cert |
| `eurotramp-wehrfritz-fun-xl-playground` | 16 | 1 | 1 | 7 | 6 | 1 | 0 | 0 | ✅ photo |
