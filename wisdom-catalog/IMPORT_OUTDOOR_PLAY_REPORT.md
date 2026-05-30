# Wisdom Outdoor-Play — Medusa Import Report

- **Run timestamp (UTC):** 2026-05-29T19:52:34+00:00
- **Mode:** LIVE
- **Medusa backend:** https://leka-medusa-backend-rg5gmtwrfa-as.a.run.app
- **Collection handle:** `wisdom-outdoor-play`
- **Collection id:** `pcol_01KSTM5ZC4H197S057QC2TNATR`
- **Strategy:** Option A — link existing 255 Leka-Project products + create 17 new wisdom-* products.
- **Image filter:** URL rewrite → HEAD check → Gemini verify (`gemini-2.5-flash`, conf≥0.7).

## Summary

| Metric | Count |
|---|---:|
| total in json | 272 |
| linked existing | 255 |
| created new | 17 |
| skipped | 0 |
| missing from firestore | 17 |
| products with images | 140 |
| products without images | 132 |
| broken image urls | 45 |
| gemini accept | 168 |
| gemini reject | 96 |
| gemini error | 0 |
| gemini cached | 4 |
| image refresh applied | 0 |

**SKU reconciliation:** linked (255) + created (17) + skipped (0) = 272 (target: 272)

**Unique-product reconciliation:** `wisdom-outdoor-play` collection holds **227 products** post-import (verified live via `/admin/products?collection_id=…&limit=1` → `count: 227`). The 45-product gap (272 SKUs → 227 products) reflects many-to-one mappings in the merged JSON — multiple Wisdom item codes share a single `firestore.matched_id` (e.g. `CSS-BZ` and `CSS-BZ-V02` both map to existing Medusa product `leka-project-qv8v9i2v`). This is expected and matches how the Leka-Project SC was de-duplicated in the v2.x rebrand. Each of the 272 source SKUs is accounted for; no SKU was silently dropped.

### Gemini verification

| Metric | Value |
|---|---:|
| jobs | 264 |
| accept | 168 |
| reject | 96 |
| error | 0 |
| cached | 4 |

## SKUs missing from Firestore (created as new wisdom-* with placeholder) (17)

| SKU | Name |
|---|---|
| HW1-S003-V01 | HW1-S003-V01 |
| HW1-S140 | Nature's Elements Outdoor |
| HW1-S149 | Nature's Elements Outdoor |
| HW1-S1A055 | Reservoir Group |
| HW1-S240 | Outdoor Beverage Cart |
| HW1-S240-V01 | Outdoor Beverage Cart |
| HW1-S242 | 0.7m |
| HW1-S268 | Music Wallboard-B |
| HW1-S269 | Music Wallboard Set-Lines |
| HW1-S284 | Water Play-Wheels Set |
| HW1-S372 | Colorful Mirror |
| HW1-S375 | Nature's Elements Outdoor |
| HW1-S610 | Pre-treated Pinewood |
| HW1-S611 | Outdoor Classroom - Teacher Table |
| HW1-S638 | Age Group: 3Y+ |
| HW1-S689 | Age Group: 3Y+ |
| KB1-HWQJ04-V01 | Nature's Elements Outdoor Role Play Set |

## SKUs with no verified images (got placeholder) (132)

| SKU | Title | Match | Broken | Gemini-Rejected |
|---|---|---|---|---|
| CSS-CBZJ-BZ | Castle Support Standard Package | sku | 0 | 0 |
| CSS-JDZJ-BZ | Classical Support Standard Package | sku | 0 | 1 |
| CSS-JQ | Sand & Water - Jumbo Version | matched_id | 0 | 1 |
| CSS-JQ-V01 | Sand & Water - Jumbo Version | sku | 0 | 1 |
| CSS-QBGD-BZ | Wallboard Tubes & Connector Standard Package | matched_id | 0 | 3 |
| CSS-QBWJ-BZ | Wallboard Toys Standard Package | sku | 0 | 3 |
| CSS-XPB-PMSG | Accessory Package-Semicircular Tubes | sku | 0 | 3 |
| GP2-T029-V01 | GP2-TC007-V01-06 | matched_id | 0 | 0 |
| GP2-T040 | Transport Theme Chalkboard | sku | 0 | 1 |
| GP2-T042 | Emotion Theme Chalkboard | sku | 0 | 1 |
| GP2-T043-V02 | Dimension：81×118cm | sku | 0 | 2 |
| GP2-T044 | Emotion Theme Whiteboard | sku | 0 | 1 |
| GP2-T053 | Themed Mirror Wallboard | sku | 1 | 0 |
| GP2-T057 | Outdoor Chalkboard 1-100 Number
Square - Coloured | sku | 0 | 1 |
| GP2-T058 | Outdoor Chalkboard 1-20 Number
Square-Black & White | sku | 0 | 1 |
| GP2-T059 | Outdoor Chalkboard Alphabet Square -
Black & White | sku | 0 | 2 |
| GP2-T062 | Garden Collection Chalkboards | sku | 2 | 0 |
| GP2-TC012 | Power Trolley Wheel-Yellow | sku | 0 | 1 |
| GP3-1312-V02 | Sand & Water Play Set-Round | sku | 0 | 1 |
| GP3-SW404C-V01 | Sand and Water Table C | matched_id | 0 | 0 |
| GP3-SW404C-V02 | Sand and Water Table C | sku | 0 | 0 |
| HW1-S001-V01 | Nature's Elements Outdoor
Bubble Wash Tunnel | matched_id | 0 | 0 |
| HW1-S001-V03 | Nature's Elements Outdoor
Bubble Wash Tunnel | matched_id | 0 | 0 |
| HW1-S003-V01 | HW1-S003-V01 | - | 0 | 0 |
| HW1-S007 | Nature's Elements Outdoor Insect
-prevented & Anti-cold Flow | sku | 0 | 3 |
| HW1-S008-V01 | Entrance Ramp | sku | 0 | 0 |
| HW1-S009 | Wonky Road | matched_id | 2 | 0 |
| HW1-S009-V01 | Wonky Road | sku | 2 | 0 |
| HW1-S010 | Slow-down Road | matched_id | 2 | 0 |
| HW1-S010-V01 | Slow-down Road | sku | 2 | 0 |
| HW1-S011 | Arch Bridge | matched_id | 2 | 0 |
| HW1-S011-V01 | Arch Bridge | sku | 2 | 0 |
| HW1-S014 | Tunnel | matched_id | 2 | 0 |
| HW1-S014-V01 | Tunnel | sku | 2 | 0 |
| HW1-S016-V01 | Nature's Elements Outdoor Kitchen Set | matched_id | 0 | 0 |
| HW1-S016-V02 | Nature's Elements Outdoor Kitchen Set | matched_id | 0 | 0 |
| HW1-S017 | Nature's Elements Outdoor Cupboard | matched_id | 0 | 0 |
| HW1-S020-V01 | Nature's Elements Outdoor
Play House | matched_id | 0 | 0 |
| HW1-S020-V02 | Nature's Elements Outdoor
Play House | matched_id | 0 | 0 |
| HW1-S023-V03 | Nature's Elements Outdoor Teepee | matched_id | 0 | 0 |
| HW1-S023-V05 | Nature's Elements Outdoor Teepee | matched_id | 0 | 0 |
| HW1-S024-V01 | Nature's Elements Outdoor
Kiosk | matched_id | 0 | 0 |
| HW1-S025-V01 | Nature's Elements Outdoor
Kitchen Set-Sink | matched_id | 0 | 0 |
| HW1-S026-V01 | Nature's Elements Outdoor
Kitchen Set-Barbecue | matched_id | 0 | 0 |
| HW1-S027-V01 | Nature's Elements Outdoor
Kitchen Set-Oven | matched_id | 0 | 0 |
| HW1-S028-V01 | Nature's Elements Outdoor
Kitchen Set-Refrigerator | matched_id | 0 | 0 |
| HW1-S029 | Nature's Elements
Outdoor Chalkboard Easel-Planting Set | sku | 0 | 0 |
| HW1-S030 | Nature's Elements
Outdoor Whiteboard Easel-Planting Set | sku | 0 | 0 |
| HW1-S031 | Nature's Elements
Outdoor Transparent Easel-Planting Set | sku | 0 | 0 |
| HW1-S032-V02 | Flowerpot Stand | sku | 0 | 1 |
| … | (82 more rows truncated) | … |

## Broken image URLs (HEAD non-2xx) (45)

| SKU | Status | Error | URL |
|---|---|---|---|
| GP2-T053 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/GP2-T053_wisdom_2025_p502_5be38ee3.jpeg |
| GP2-T062 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/GP2-T062_wisdom_2025_p502_72c88883.jpeg |
| GP2-T062 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/GP2-T062_wisdom_2025_p98_ba2534c4.jpeg |
| HW1-S009 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S009-V01_wisdom_2025_p503_2fb2d50e.jpeg |
| HW1-S009 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S009-V01_wisdom_2025_p108_3428531e.jpeg |
| HW1-S009-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S009-V01_wisdom_2025_p503_2fb2d50e.jpeg |
| HW1-S009-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S009-V01_wisdom_2025_p108_3428531e.jpeg |
| HW1-S010 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S010-V01_wisdom_2025_p503_d3bc1659.jpeg |
| HW1-S010 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S010-V01_wisdom_2025_p108_0614e451.jpeg |
| HW1-S010-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S010-V01_wisdom_2025_p503_d3bc1659.jpeg |
| HW1-S010-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S010-V01_wisdom_2025_p108_0614e451.jpeg |
| HW1-S011 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S011-V01_wisdom_2025_p503_cdf9a29d.jpeg |
| HW1-S011 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S011-V01_wisdom_2025_p108_7d93b2e8.jpeg |
| HW1-S011-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S011-V01_wisdom_2025_p503_cdf9a29d.jpeg |
| HW1-S011-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S011-V01_wisdom_2025_p108_7d93b2e8.jpeg |
| HW1-S014 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S014-V01_wisdom_2025_p503_7360ecd5.jpeg |
| HW1-S014 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S014-V01_wisdom_2025_p108_7d93b2e8.jpeg |
| HW1-S014-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S014-V01_wisdom_2025_p503_7360ecd5.jpeg |
| HW1-S014-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S014-V01_wisdom_2025_p108_7d93b2e8.jpeg |
| HW1-S058 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S058_wisdom_2025_p502_16f3361f.jpeg |
| HW1-S072 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S072_wisdom_2025_p501_24e2e6df.jpeg |
| HW1-S072 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S072_wisdom_2025_p78_da57d640.jpeg |
| HW1-S073 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S073_wisdom_2025_p501_05da58d1.jpeg |
| HW1-S073 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S073_wisdom_2025_p78_066a846f.jpeg |
| HW1-S079 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S079_wisdom_2025_p502_785f1528.jpeg |
| HW1-S079 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S079_wisdom_2025_p81_ca71a676.jpeg |
| HW1-S252 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S252-V01_wisdom_2025_p87_59eb0f18.jpeg |
| HW1-S252-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S252-V01_wisdom_2025_p87_59eb0f18.jpeg |
| HW1-S261 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-S261_wisdom_2025_p88_deb0483e.jpeg |
| HW1-SP03 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP03_wisdom_2025_p502_a9e0678a.jpeg |
| HW1-SP03 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP03_wisdom_2025_p88_41dbbdd0.jpeg |
| HW1-SP04 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP04_wisdom_2025_p88_56567e3b.jpeg |
| HW1-SP04 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP04_wisdom_2025_p88_276338ce.jpeg |
| HW1-SP05 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP05_wisdom_2025_p88_26621d06.jpeg |
| HW1-SP05 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP05_wisdom_2025_p87_59eb0f18.jpeg |
| HW1-SP06 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP06_wisdom_2025_p88_a163a96b.jpeg |
| HW1-SP06 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP06_wisdom_2025_p87_a0524c8b.jpeg |
| HW1-SP07 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP07_wisdom_2025_p88_1db9e2fd.jpeg |
| HW1-SP07 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP07_wisdom_2025_p87_eaa9c40e.jpeg |
| HW1-SP08 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP08_wisdom_2025_p88_cf3e724a.jpeg |
| HW1-SP08 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP08_wisdom_2025_p87_8ae4aee4.jpeg |
| HW1-SP09 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP09_wisdom_2025_p502_7d451f23.jpeg |
| HW1-SP09 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW1-SP09_wisdom_2025_p88_4c99a894.jpeg |
| HW4-SZ002-V01 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW4-SZ002-V01_wisdom_2025_p96_532b3ebc.jpeg |
| HW4-SZ008-V02 | 403 |  | https://storage.googleapis.com/ai-agents-go-documents/product-images/verified/HW4-SZ008-V02_wisdom_2025_p96_e3e29b2a.jpeg |

## Images rejected by Gemini (matches=false or confidence<0.70) (104)

| SKU | Conf | Depicted | URL |
|---|---|---|---|
| CSS-BZ | 1.00 | pipe fittings | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-BZ-V02_img1.jpeg |
| CSS-BZ | 0.90 | a wooden game board or barrier with holes | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-BZ-V02_img2.jpeg |
| CSS-BZ-V02 | 1.00 | pipe fittings | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-BZ-V02_img1.jpeg |
| CSS-BZ-V02 | 0.90 | a wooden game board or barrier with holes | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-BZ-V02_img2.jpeg |
| CSS-DMWJ-BZ | 1.00 | pipe fittings | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-DMWJ-BZ_img1.jpeg |
| CSS-JDZJ-BZ | 0.90 | giant wooden game board | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/CSS-JDZJ-BZ_wisdom_2025_p77_8756e070.jpeg |
| CSS-JQ | 1.00 | pipe fittings | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/CSS-JQ-V01_wisdom_2025_p77_a992c993.jpeg |
| CSS-JQ-V01 | 1.00 | pipe fittings | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/CSS-JQ-V01_wisdom_2025_p77_a992c993.jpeg |
| CSS-QBGD-BZ | 0.90 | various freestanding water and sand play stations | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-QBGD-BZ-V01_img0.jpeg |
| CSS-QBGD-BZ | 1.00 | pipe fittings | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-QBGD-BZ-V01_img1.jpeg |
| CSS-QBGD-BZ | 0.90 | wooden play panel with holes | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-QBGD-BZ-V01_img2.jpeg |
| CSS-QBWJ-BZ | 1.00 | water and sand play stations | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-QBWJ-BZ_img0.jpeg |
| CSS-QBWJ-BZ | 1.00 | pipe fittings | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-QBWJ-BZ_img1.jpeg |
| CSS-QBWJ-BZ | 0.00 | reject | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-QBWJ-BZ_img2.jpeg |
| CSS-XPB-PMSG | 1.00 | various water and sand play accessories including  | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-XPB-PMSG_img0.jpeg |
| CSS-XPB-PMSG | 1.00 | pipe fittings | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-XPB-PMSG_img1.jpeg |
| CSS-XPB-PMSG | 1.00 | wooden game board with circular holes | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-XPB-PMSG_img2.jpeg |
| CSS-XPB-SG | 0.90 | various water play accessories including troughs,  | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-XPB-SG_img0.jpeg |
| CSS-XPB-SG | 1.00 | wooden play panel with holes | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-XPB-SG_img2.jpeg |
| FS-WP0005C | 0.80 | playground merry-go-round with tricycles | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/FS-WP0005C_usa_2025_p116_b1369eac.jpeg |
| GP2-T040 | 1.00 | silhouettes of various transport vehicles | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T040_wisdom_2025_p98_e73d0ba5.jpeg |
| GP2-T042 | 0.90 | emotion faces | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T042_wisdom_2025_p98_edb10502.jpeg |
| GP2-T043-V02 | 0.00 | reject | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T043-V02_wisdom_2025_p98_e5fc1e59.jpeg |
| GP2-T043-V02 | 0.00 | reject | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T043-V02_wisdom_2025_p503_6baec52c.jpeg |
| GP2-T044 | 0.90 | drawings of faces expressing emotions | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T044_wisdom_2025_p98_4d007436.jpeg |
| GP2-T052 | 1.00 | five black decorative shapes | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T052_wisdom_2025_p502_72c88883.jpeg |
| GP2-T057 | 0.90 | a colored 1-100 number grid | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T057_wisdom_2025_p98_f5e734b8.jpeg |
| GP2-T058 | 0.90 | black and white number grid | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T058_wisdom_2025_p98_20a49e03.jpeg |
| GP2-T059 | 0.90 | alphabet display board | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T059_wisdom_2025_p98_804db2d1.jpeg |
| GP2-T059 | 0.90 | wooden play stand with awning and small chalkboard | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T059_wisdom_2025_p503_ad0ab005.jpeg |
| GP2-T063 | 1.00 | animal and fruit shaped chalkboards | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-T063_wisdom_2025_p98_ba2534c4.jpeg |
| GP2-TC012 | 1.00 | yellow tricycles on a red storage rack | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP2-TC012_wisdom_2025_p108_ee2181fe.jpeg |
| GP3-1312-V02 | 0.90 | a multi-compartment sand and water play set with t | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/GP3-1312-V02_wisdom_2025_p78_1f524bac.jpeg |
| HW1-S007 | 0.90 | butterfly-shaped flower bed | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S007_wisdom_2025_p84_b69c38ea.jpeg |
| HW1-S007 | 0.90 | outdoor wooden flower beds with plants | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S007_wisdom_2025_p84_88c2d571.jpeg |
| HW1-S007 | 0.90 | plant with a trellis | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S007_wisdom_2025_p84_ef3cf600.jpeg |
| HW1-S022 | 1.00 | small wooden picnic table | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S022_wisdom_2025_p102_b0269b3b.jpeg |
| HW1-S022 | 0.90 | black plastic tank with a red lid | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S022_wisdom_2025_p102_65f99d47.jpeg |
| HW1-S032-V02 | 1.00 | wooden planter | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S032-V02_wisdom_2025_p97_6855cf69.jpeg |
| HW1-S033 | 0.90 | garden sign | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S033_wisdom_2025_p83_6d4e4bc5.jpeg |
| HW1-S056 | 1.00 | wooden toy boat with buckets | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S056_wisdom_2025_p74_75ab5be8.jpeg |
| HW1-S060 | 1.00 | planter box with trellis and climbing roses | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S060_wisdom_2025_p81_973b4ea8.jpeg |
| HW1-S060 | 0.90 | water play station with multiple activity panels | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S060_wisdom_2025_p79_90a801cf.jpeg |
| HW1-S060 | 1.00 | wooden lattice panel | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S060_wisdom_2025_p81_3ebe7b8b.jpeg |
| HW1-S082 | 0.90 | miniature garden decorations | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S082_wisdom_2025_p502_86c01957.jpeg |
| HW1-S089 | 0.80 | wooden planter with birdhouse | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S089_wisdom_2025_p81_c8bf5bcd.jpeg |
| HW1-S091 | 0.90 | a multi-functional wooden outdoor play structure w | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S091_wisdom_2025_p81_e420c09e.jpeg |
| HW1-S092 | 0.90 | hamster habitat or playhouse | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S092_wisdom_2025_p82_1b34cef4.jpeg |
| HW1-S095 | 1.00 | wooden gate with a hamster figure | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S095_wisdom_2025_p82_7bdc5211.jpeg |
| HW1-S143 | 0.90 | colorful play panel structure | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/HW1-S143_wisdom_2025_p92_0f3f025c.jpeg |
| … | (54 more rows truncated) | … |

## Sample of 5 linked / created products (5)

| SKU | Action | Handle / PID | Thumbnail |
|---|---|---|---|
| CHW-MGJJ | LINK (sku) | prod_01KNKVVKHZ08HDR886BKPJBHR3 | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/CHW-MGJJ_wisdom_2025_p95_5907c2ba.jpeg |
| CSS-BZ | LINK (matched_id) | prod_01KNKW12PZEHXHGPNTFSCSJT1G | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-BZ-V02_img0.jpeg |
| CSS-BZ-V02 | LINK (sku) | prod_01KNKW12PZEHXHGPNTFSCSJT1G | https://catalogs.leka.studio/api/i/leka-project/catalog/CSS-BZ-V02_img0.jpeg |
| CSS-CBZJ-BZ | LINK (sku) | prod_01KNKW13627C98GJA8G11H421W | - |
| CSS-DMGD-BZ | LINK (matched_id) | prod_01KNKW13MXV7V38WFZRENDCS3E | https://catalogs.leka.studio/api/i/leka-project/spatial_v2/CSS-DMGD-BZ-V01_wisdom_2025_p77_d4f58784.jpeg |

## Verification commands

```bash
TOKEN=$(curl -s -X POST "$MEDUSA_URL/auth/user/emailpass" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$MEDUSA_ADMIN_EMAIL\",\"password\":\"$MEDUSA_ADMIN_PASSWORD\"}" | jq -r .token)

# 1. Collection exists?
curl -s "$MEDUSA_URL/admin/collections?handle=wisdom-outdoor-play" -H "Authorization: Bearer $TOKEN" | jq '.collections | length'

# 2. Product count in collection
curl -s "$MEDUSA_URL/admin/products?collection_id=pcol_01KSTM5ZC4H197S057QC2TNATR&limit=1" -H "Authorization: Bearer $TOKEN" | jq '.count'
```
