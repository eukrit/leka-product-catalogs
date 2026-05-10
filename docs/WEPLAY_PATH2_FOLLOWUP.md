# Weplay Path 2 — image association for the remaining 1,095 products

**Status:** OPEN — Path 2 investigation 2026-05-10 confirmed local data alone cannot unlock new products. A live re-crawl is required.

## What's done (Path 1B, v2.8.4)

- Sales Channel `sc_01KR6Z0VBSXWYZDVGF30EAP0EQ` ("Weplay") created, publishable key linked.
- 100 Weplay products are live in Medusa, served at `https://catalogs.leka.studio/weplay`.
- All 1,195 products in `vendors/weplay/products/*` have been re-shaped to the Medusa schema by `scripts/shape_weplay_to_medusa_schema.py`. The 1,095 without photo matches carry `status="draft_no_images"` and `images: []`.

## What's blocked

The upstream scrape stored 4,770 photos in `vendors/weplay/attachments/*` but never linked them to products. Only **381 / 4,770 (8%)** of attachments carry a URL-encoded SKU path (`/Products/XX/SKU/...jpg`). The other 4,389 have opaque scrambled filenames (`B0d41c5f6449f444fdb.jpg`) that came from a different scrape pattern (`/public/files/product/thumb/...`) — no SKU encoded. Indexing those URLs gave us only 95 unique SKU folders → matched 100 products; 1,095 still un-imaged.

Roughly 500 of the 1,095 un-imaged products have AI-inferred non-SKU IDs (`00B`, `3D-CRYSTAL-PUZZLE`, `4CM-SOFTWOOD-BLOCKS-152-PCS`) that no URL pattern can ever match. The other ~600 have plausible SKUs (`KB0001`, `EM5502`) but the corresponding `/Products/<XX>/<SKU>/` folders simply weren't crawled.

## Path 2 attempts (2026-05-10) — what was tried and what we learned

### Attempt A1: directory listing crawl (FAILED)
Probed `https://www.e-weplay.com.tw/UserFiles/images/Products/<XX>/<SKU>/` for 12 unmatched real-SKU products (AT0002, ED0001, EM5502, EM5504, EM5513, KB0001, KB0007, KB0008, KB0020, KB1300, etc.). All returned 404 — the web server doesn't expose Apache-style directory listings. Path A1 only works if you already know the exact image filename, which is the join we're trying to recover.

### Attempt A3: re-crawl missing site_structure URLs (FAILED)
After A2's diagnostic, tried the obvious next step: fetch the ~3,800 `product_detail` URLs in `vendors/weplay/site_structure/*` that aren't cached. Findings from a 5-URL pilot (2026-05-10):

- Of 4,063 missing URLs labelled `product_detail`, ~2,400 are actually image URLs (`.jpg`) that the upstream extractor miscategorized; ~1,400 are real `e-weplay.com.tw/mod/product/index.php?REQUEST_ID=…` page URLs.
- All 5 page URLs returned **HTTP 200, 51-52 KB, 0 SKU markers, 0 `/Products/XX/SKU/` image URLs**. Page `<title>` is `商品一覽` ("Product List") — every URL falls through to the default category-listing page rather than a specific product detail.
- Likely root cause: the original scrape worked because it had session cookies / JS-rendered content; raw HTTP without that infrastructure all redirects to the index. The REQUEST_IDs encode `cGFnZT1kZXRhaWwmUE…` (base64 "page=detail&PE...") but the server appears to require additional state to render the actual product.

So A3 needs either a headless browser (Playwright/Puppeteer) that can execute the page's JS, OR a recursive crawl from category pages that maintains valid session state. Both are real scraping projects beyond a quick script. Pilot script deleted.

### Attempt A2: parse cached HTML pages for SKU↔image join
The vendor scrape stored 1,453 cached HTML pages in `gs://ai-agents-go-vendors/weplay/pages/<sha>.html`. These ARE real product detail pages from `e-weplay.com.tw` (REQUEST_ID URLs, Chinese titles like "Weplay 萬象簡易組"). Each page references the SKU via image URLs in the body like `<img src=".../UserFiles/images/Products/KM/KM2000/6800KM2000.1-034-10.jpg">`.

Built `scripts/enrich_weplay_attachments_from_pages.py` (since deleted — see git history at the time of writing). Heuristic: for each page, the "primary SKU" is whatever appears in `/Products/XX/SKU/` URLs (cap at 3 to skip category pages). Cross-reference all other `<img>` URLs on the page (including the opaque-named `/public/files/product/thumb/Bxxxx.jpg` thumbs) to that SKU.

**Findings — and why we did NOT apply this:**
- 1,453 pages scanned → 285 had a unique primary SKU (1–3 folders) → 95 unique SKU keys discovered
- 1,449 attachments newly linkable to those 95 SKUs
- BUT: the 95 page-derived SKU keys overlap **0** of the 144 draft products with real-SKU `item_code` values. They overlap **68 of the 100 already-active products** (subset; the 100 had 95 unique URL-encoded SKU folders to begin with).
- 27 of the 95 page SKUs (KC1801, KC2008, KC2802, etc.) reference products that don't exist in our Firestore at all — they were missed by the upstream extractor.

**Conclusion:** the cached pages cover only the same narrow slice of the catalog the URL-encoded attachments already covered. Running this enrichment would (a) add 1,449 mostly-low-res opaque thumb URLs to product cards that already have 3–10 high-res images each — adding noise, not value — and (b) unlock ZERO new products. So the script was abandoned.

The fundamental gap: out of 5,266 `product_detail` pages catalogued in `vendors/weplay/site_structure/*`, only 1,453 were actually fetched and cached. The missing ~3,800 pages are presumably what would link the 1,095 draft products to their photos.

## Three paths forward (pick one when you tackle this)

### A. Headless-browser recursive re-crawl (recommended)
The 3,800 missing `product_detail` URLs in site_structure are actually unreachable via plain HTTP (Attempt A3 above) — they all fall through to the category-listing page. Need a headless-browser crawl (Playwright/Puppeteer) starting from `https://www.e-weplay.com.tw/` that:
1. Walks the category menus (`?REQUEST_ID=FwtEDBkMWXJrLV4BcnJ*` URLs visible in cached pages' navbar HTML),
2. Follows pagination,
3. Extracts each product detail page with full JS execution,
4. Saves HTML to `gs://ai-agents-go-vendors/weplay/pages/<sha>.html`,
5. Writes attachments (or updates existing attachment docs) with `linked_skus: [...]` based on `/Products/XX/SKU/` image references on each page.

Then run `scripts/shape_weplay_to_medusa_schema.py` (one-line tweak to also accept `linked_skus` in `build_attachment_index`) + `scripts/sync_vendors_to_medusa.py --brand=weplay --skip-no-images`.

Estimate: 1-2 days of work. Probably belongs in a fresh repo (`weplay-recrawler`) rather than this catalog repo.

The ~500 AI-inferred-SKU products (`00B`, `3D-CRYSTAL-PUZZLE`, etc.) need a separate decision — they have no real catalog SKU and likely need to be deleted as scrape noise or hand-curated.

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
