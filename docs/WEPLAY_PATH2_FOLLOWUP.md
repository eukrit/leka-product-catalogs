# Weplay Path 2 — image association for the remaining 1,095 products

**Status:** OPEN — captured 2026-05-10 after Path 1B (`v2.8.4`) shipped 100 imaged Weplay products.

## What's done (Path 1B, v2.8.4)

- Sales Channel `sc_01KR6Z0VBSXWYZDVGF30EAP0EQ` ("Weplay") created, publishable key linked.
- 100 Weplay products are live in Medusa, served at `https://catalogs.leka.studio/weplay`.
- All 1,195 products in `vendors/weplay/products/*` have been re-shaped to the Medusa schema by `scripts/shape_weplay_to_medusa_schema.py`. The 1,095 without photo matches carry `status="draft_no_images"` and `images: []`.

## What's blocked

The upstream scrape stored 4,770 photos in `vendors/weplay/attachments/*` but never linked them to products. Only **381 / 4,770 (8%)** of attachments carry a URL-encoded SKU path (`/Products/XX/SKU/...jpg`). The other 4,389 have opaque scrambled filenames (`B0d41c5f6449f444fdb.jpg`) that came from a different scrape pattern (`/public/files/product/thumb/...`) — no SKU encoded. Indexing those URLs gave us only 95 unique SKU folders → matched 100 products; 1,095 still un-imaged.

Roughly 500 of the 1,095 un-imaged products have AI-inferred non-SKU IDs (`00B`, `3D-CRYSTAL-PUZZLE`, `4CM-SOFTWOOD-BLOCKS-152-PCS`) that no URL pattern can ever match. The other ~600 have plausible SKUs (`KB0001`, `EM5502`) but the corresponding `/Products/<XX>/<SKU>/` folders simply weren't crawled.

## Three paths forward (pick one when you tackle this)

### A. Targeted re-crawl (recommended, lowest cost/highest fidelity)
For each of the ~600 un-imaged real-SKU products, fetch `https://www.e-weplay.com.tw/UserFiles/images/Products/<XX>/<SKU>/` directly (the prefix is the first two letters of the SKU). Store new photos as `attachments` docs with `sha`, `gcs_path`, and **importantly** a new field `linked_skus: [<SKU>]` so the join is explicit. Then re-run the shaping pass + sync. Should resolve ~600 of the 1,095 cleanly.

The ~500 AI-inferred-SKU products need a separate decision — either delete them as scrape noise, or hand-curate.

### B. Vision-based image→product matching
Use Gemini Vision to look at each of the 4,389 unmatched photos and match them to product names + descriptions. Estimate ~$30–60 in Vertex calls. Higher false-match risk; treat as a fallback only after path A.

### C. Defer permanently
Accept Weplay as a 100-product catalog. Hide the 1,095 drafts entirely (or move them to a `vendors/weplay-pending/` collection). Lowest effort but largest catalog gap.

## Files / state to touch when this work happens

- `scripts/shape_weplay_to_medusa_schema.py` — already handles the join; once `attachments` carry `linked_skus` it will pick them up if the join key is added (one-line change in `build_attachment_index`).
- `vendors/weplay/products/*` — the 1,095 `draft_no_images` docs; flip to `status="active"` once images are attached.
- `scripts/sync_vendors_to_medusa.py --brand=weplay --skip-no-images` — same command will sync the new batch (incrementally — existing 100 will UPDATE, new ones will CREATE).
- `medusa-storefront/src/lib/medusa-client.ts` — bump `productCount` to the new total.

## Why Path 1B was the right move now

Shipping the 100 photo-confirmed products gives the storefront a real catalog instead of the "Catalog coming soon" stub from v2.8.1. The remaining work is upstream data quality, not Medusa pipeline work — no point holding the 100 ready-to-ship products hostage to a re-crawl decision.
