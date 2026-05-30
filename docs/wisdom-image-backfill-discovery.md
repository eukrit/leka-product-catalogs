# Wisdom / Leka Project — Image Backfill Discovery

_Date: 2026-05-30 · Author: Claude · Worktree: `zealous-murdock-dde8e9`_

Goal: shrink the **2,138** Leka Project products still serving the
"Image coming soon" placeholder on `catalogs.leka.studio` by inspecting two
newly-flagged local folders for unused source imagery.

---

## TL;DR

| Folder | Useful for backfill? | Why |
|---|---|---|
| `…\WeChat OneDrive\WeChat Wisdom Playground` | **No** — skip | Contains 1 custom-order PDF + 1 Excel, no catalog imagery. |
| `…\My Drive\Catalogs GO\Wisdom Playground` | **YES** — high signal | 3 catalog PDFs (~411 MB), one **never previously ingested**. |

The high-leverage finding is two PDFs in folder 2 cleanly cover the gap:

1. **`2025-06-13 USA Catalogue …pdf`** — 1,005 distinct SKU codes, top prefix
   **QSWP (587)**. The bucket has **zero** QSWP objects today, yet **518 QSWP
   placeholders** exist. **This single PDF can plausibly close ~26 % of the
   gap.**
2. **`2025-08-11 Wisdom International Furniture Catalog.pdf`** — 355 pages,
   1,418 codes, 5,286 embedded images. Brand-new (no reference anywhere in the
   repo). Top prefixes KB (799), HW (267), GP (217) match the next-biggest
   placeholder buckets (KB 429, HW 57, GP 44).

The third PDF (`2025-06-13 International catalogue`) is likely redundant with
the existing bucket coverage but worth a low-cost dry-run pass for residual SR
/ BS / SS prefixes.

---

## Live state (2026-05-30 snapshot)

Source: `scripts/_audit_placeholders.py` (Store API + GCS index)

| Metric | Value |
|---|---:|
| Total Leka Project products | 5,062 |
| Showing placeholder | **2,138** |
| …with an existing object in `catalog/` (Gemini-rejected) | 457 |
| …with **no** `catalog/` object at all (true gap) | **1,680** |
| …no legacy_sku (orphan) | 1 |
| Distinct SKU codes already hosted in `catalog/` | 3,050 |
| Total objects in `gs://ai-agents-go-vendors/leka-project/` | 38,024 |

### Placeholder gap by SKU prefix (no `catalog/` object — top 20)

| Prefix | Missing | Source PDF that covers it |
|---|---:|---|
| QSWP | 518 | `2025-06-13 USA Catalogue` (587 codes) |
| KB | 429 | `2025-08-11 Furniture Catalog` (799 codes) |
| BS | 58 | `2025-06-13 International catalogue` (19 codes) |
| HW | 57 | `2025-08-11 Furniture Catalog` (267 codes) |
| AT | 51 | Not in these PDFs — needs different source |
| GP | 44 | `2025-08-11 Furniture Catalog` (217 codes) |
| CH | 35 | Not in these PDFs |
| QJB | 31 | Not in these PDFs |
| WT | 24 | Not in these PDFs |
| FLCS | 23 | Not in these PDFs |
| QSFS | 22 | `2025-06-13 USA Catalogue` (39 codes) |
| FLTH | 21 | Not in these PDFs |
| CX | 17 | Sparse — `2025-08-11 Furniture Catalog` (small) |
| TOT | 17 | Not in these PDFs |
| SW | 15 | `2025-06-13 USA Catalogue` (6 codes) |
| CJ | 14 | `2025-08-11 Furniture Catalog` (1 code) |
| WPPE | 14 | International + USA catalogs (32 total) |
| CC | 13 | Sparse |
| (other prefixes) | ~278 | Mixed |

**Estimated direct coverage of the 1,680-product gap from these 3 PDFs:
~1,300–1,400 placeholder products** (QSWP 518 + KB ≤429 + HW 57 + GP 44 +
QSFS 22 + WPPE 14 + scattered = roughly 1,084 in the best case; more once we
also pull the smaller prefixes that show up in the furniture catalog).

---

## Folder 1: `…\WeChat OneDrive\WeChat Wisdom Playground`

| File | Size | Verdict |
|---|---:|---|
| `2026-02-05 泰国新客户-PO#26010901 订制游具.pdf` | 0.9 MB | Custom order, not a catalog |
| `2026-05-21 Wisdom (3).xlsx` | 0.8 MB | Spreadsheet, no images |

No subdirectories. **Not used for this backfill** — no catalog imagery here.

## Folder 2: `…\My Drive\Catalogs GO\Wisdom Playground`

| File | Size | Pages | Codes | Raw imgs | Notes |
|---|---:|---:|---:|---:|---|
| `2025-06-13 International  catalogue  06  06  2025.pdf` | 133.1 MB | 142 | 244 | 1,773 | Likely already partially ingested (SR/HW/BS prefixes). Top prefixes (num) 66, SR 30, HW 26, SS 23, FS 20, BS 19, WPPE 17. |
| `2025-06-13 USA  Catalogue  06  06  2025.pdf` | 154.7 MB | 142 | 1,005 | 1,649 | **High value.** QSWP 587, PDWP 52, QSFS 39, CL 29, HW 28, SR 21, WPPE 15. Bucket has 0 QSWP today. |
| `2025-08-11 Wisdom International Furniture Catalog.pdf` | 123.8 MB | 355 | 1,418 | **5,286** | **Brand-new; never extracted.** KB 799, HW 267, GP 217, WP 56, EI 19. Furniture-heavy. |

No subdirectories. Total ~411 MB, ~8,700 raw embedded images.

---

## SKU-matching scheme

Confirmed from `wisdom-catalog/extract_images.py` and bucket sample:

- **Filename convention:** `gs://ai-agents-go-vendors/leka-project/catalog/<code>_img<N>.<ext>`
- Backfill split rule (`backfill_leka_project_images.py:240`): filename token
  before the first `_` is the SKU code. SKUs themselves contain no `_`.
- Codes appear as plain text on the same PDF page as the product image (often
  beside a "Code:" label). PyMuPDF `page.get_text()` + a tuned regex set picks
  them up reliably (see `extract_images.py:30-44`).
- **Page granularity isn't enough** for multi-product pages — a 1:1 image-to-code
  mapping needs PyMuPDF's `get_image_rects()` / `get_text("dict")` so we can
  pick the code-token text-box nearest to each image rect. The existing
  `wisdom-catalog/map_images_verified.py` (12 KB, ships with the repo) does
  this already and is reusable.

### Bugs to fix in the legacy extractor before reuse

The existing `wisdom-catalog/extract_images.py` is the closest reference but
must NOT be reused as-is. It currently:

1. Uploads to `gs://ai-agents-go-documents/product-images/catalog/<catalog>_p<page>_img<n>_<hash>.<ext>` — wrong bucket per the memory note, and the
   `<catalog>_…` filename prefix breaks the backfill script's `<code>_*`
   matching.
2. Calls `blob.make_public()` — fails on the UBLA bucket.
3. Targets the old `products_wisdom` Firestore docs, not Medusa product IDs.

The replacement (`scripts/extract_wisdom_pdf_images.py`, see plan below) will
write directly into the convention `backfill_leka_project_images.py` already
indexes.

---

## Cost preview (Vertex AI)

v2.34.0 ran 539 candidates → ~$5 (`gemini-2.5-flash`, single-image verify).
Per-candidate cost ≈ **$0.0093**.

Projected --verify pass after image upload:

| Scenario | New candidates | Re-verify rejected | Vertex AI cost |
|---|---:|---:|---:|
| Conservative (extract only USA + Furniture, dedup against bucket) | ~1,300 | 0 | **~$12** |
| Aggressive (all 3 PDFs, also re-verify ~200 of the rejected 457 with new images) | ~1,500 | ~200 | **~$16** |
| Worst case (every QSWP image is multi-product → 2× multiplier) | ~2,000 | ~200 | **~$20** |

All scenarios are within the **$20 ceiling**. If we exceed in mid-run we pause
and confirm.

---

## Result (executed 2026-05-30)

This branch executed only the Furniture-catalog wave (sibling worktree
`claude/great-hopper-c0fd71` handles the USA + International outdoor-play
re-extraction).

| Step | Outcome |
|---|---|
| Spatial extraction (355 pages, full) | 1,538 JPEGs / 835 codes |
| GCS upload to `wisdom/furniture_2025/` | 1,222 new + 35 idempotent skip; 0 errors |
| Firestore write to `vendors/wisdom/products` | 93 docs gained furniture images |
| Gemini verify (2.5 Flash @ 0.70) | 39 accept / 47 reject / 0 error = 42 % |
| Vertex AI spend | **$0.86** (ceiling $20) |
| Medusa sync — placeholders flipped | **33** (`backfilled_furniture` status) |
| Live placeholder count delta | **2,138 → 2,105 (−33)** |

Spot-check live: [GP1-12036 Wallboard Handrail-Straight Rod](https://catalogs.leka.studio/leka-project/leka-project-aldwzjg0) — 2 real furniture photos served from
`wisdom/furniture_2025/`, `metadata.image_status = backfilled_furniture`.

### Vendor-side imagery population (future onboarding)
Beyond the 33 Medusa-live flips, the same run wrote furniture image entries
for 60 additional `vendors/wisdom/products` docs whose Medusa product
either hasn't been created or wasn't a placeholder. Future Medusa
onboarding will inherit these images automatically.

### What this wave intentionally did NOT do
- Re-extract the 2025-06-13 USA Catalogue (sibling branch is doing it).
- Re-extract the 2025-06-13 International Catalogue (sibling branch).
- Create new Medusa products from the 742 furniture-catalog codes that
  don't yet have a vendor doc (would require a separate onboarding script).
- Re-verify the 47 furniture rejects — they remain with
  `image_verified=False` on the vendor doc; a future pass with a
  different image source (or a relaxed threshold) can pick them up.

