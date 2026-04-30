"""
Verified image-to-product mapping.
Strategy:
1. Build full text index of PDF (product codes → PDF pages)
2. For each product code found, extract images on that page
3. Use spatial proximity to assign the closest image to each code
4. Max 2 images per product
"""
import os
import re
import json
import math
import hashlib
import fitz  # PyMuPDF
from collections import defaultdict
from PIL import Image as PILImage
import io as iomod
from google.cloud import firestore, storage

SERVICE_ACCOUNT_PATH = r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-0d28f3991b7b.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_PATH

DOWNLOADS_DIR = r"C:\Users\eukri\OneDrive\Documents\Claude Code\2026 Product Catalogs Claude\Wisdom Slack Downloads"
IMG_DIR = r"C:\Users\eukri\OneDrive\Documents\Claude Code\2026 Product Catalogs Claude\verified_images"
BUCKET_NAME = "ai-agents-go-documents"
GCS_PREFIX = "product-images/verified"
MAX_IMAGES = 2
MIN_IMG_AREA = 3000  # min width*height pixels

os.makedirs(IMG_DIR, exist_ok=True)

# All product codes from Firestore
def load_product_codes():
    db = firestore.Client(project="ai-agents-go", database="leka-product-catalogs")
    codes = set()
    for doc in db.collection("products_wisdom").stream():
        codes.add(doc.id)
    return codes


def build_pdf_index(pdf_path):
    """Build index: product_code → list of (pdf_page, x, y) positions."""
    doc = fitz.open(pdf_path)
    index = defaultdict(list)

    for pg in range(len(doc)):
        page = doc[pg]
        # Search using text dict for positions
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    bbox = span.get("bbox", [0, 0, 0, 0])
                    cx = (bbox[0] + bbox[2]) / 2
                    cy = (bbox[1] + bbox[3]) / 2

                    # Find product codes in this text span
                    patterns = [
                        r'([A-Z]{2,5}\d?-[A-Z]*\d+[A-Z]*(?:-[A-Z]?\d+)*)',
                        r'(\d{2,3}-\d{5}(?:-\d+)*)',
                    ]
                    for pat in patterns:
                        for m in re.finditer(pat, text):
                            code = m.group(1)
                            if len(code) >= 6:
                                index[code].append({"page": pg, "x": cx, "y": cy})

    doc.close()
    return index


def extract_and_save_image(doc, page, xref, product_code, catalog_name, pg_num):
    """Extract image, convert to JPEG, save locally, return filename."""
    try:
        base_image = doc.extract_image(xref)
    except Exception:
        return None

    if not base_image or len(base_image["image"]) < 2000:
        return None

    w = base_image.get("width", 0)
    h = base_image.get("height", 0)
    if w < 50 or h < 50 or w * h < MIN_IMG_AREA:
        return None

    img_data = base_image["image"]
    img_hash = hashlib.md5(img_data).hexdigest()[:8]
    fname = f"{product_code}_{catalog_name}_p{pg_num+1}_{img_hash}.jpeg"
    local_path = os.path.join(IMG_DIR, fname)

    if os.path.exists(local_path):
        return fname

    # Convert to JPEG
    try:
        img = PILImage.open(iomod.BytesIO(img_data))
        img = img.convert("RGB")
        img.save(local_path, "JPEG", quality=85)
    except Exception:
        # Try saving raw
        try:
            with open(local_path, "wb") as f:
                f.write(img_data)
        except Exception:
            return None

    return fname


def map_products_to_images(pdf_path, catalog_name, product_codes, pdf_index):
    """For each product found in the PDF, find its closest image."""
    doc = fitz.open(pdf_path)
    mappings = {}  # code → list of {filename, page, distance}

    # Get all product codes found in this PDF that are also in Firestore
    matched_codes = {code: positions for code, positions in pdf_index.items()
                     if code in product_codes}

    print(f"  {len(matched_codes)} Firestore products found in PDF")

    # Process page by page
    pages_to_process = set()
    for code, positions in matched_codes.items():
        for pos in positions:
            pages_to_process.add(pos["page"])

    print(f"  Processing {len(pages_to_process)} pages...")

    for pg_num in sorted(pages_to_process):
        page = doc[pg_num]

        # Get image positions on this page
        img_list = page.get_images(full=True)
        img_positions = []
        for img_info in img_list:
            xref = img_info[0]
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            rect = rects[0]
            cx = (rect.x0 + rect.x1) / 2
            cy = (rect.y0 + rect.y1) / 2
            area = (rect.x1 - rect.x0) * (rect.y1 - rect.y0)
            if area < 1000:  # skip tiny images
                continue
            img_positions.append({
                "xref": xref,
                "x": cx, "y": cy,
                "area": area,
                "rect": rect,
            })

        if not img_positions:
            continue

        # For each product code on this page, find closest image
        codes_on_page = {code: [p for p in positions if p["page"] == pg_num]
                         for code, positions in matched_codes.items()
                         if any(p["page"] == pg_num for p in positions)}

        for code, positions in codes_on_page.items():
            for pos in positions:
                # Find closest image
                best_img = None
                best_dist = float("inf")
                for img in img_positions:
                    d = math.sqrt((pos["x"] - img["x"])**2 + (pos["y"] - img["y"])**2)
                    if d < best_dist:
                        best_dist = d
                        best_img = img

                if best_img and best_dist < 600:
                    fname = extract_and_save_image(doc, page, best_img["xref"],
                                                   code, catalog_name, pg_num)
                    if fname:
                        if code not in mappings:
                            mappings[code] = []
                        # Avoid duplicates
                        if not any(m["filename"] == fname for m in mappings[code]):
                            mappings[code].append({
                                "filename": fname,
                                "page": pg_num + 1,
                                "distance": best_dist,
                                "catalog": catalog_name,
                            })

    doc.close()
    return mappings


def upload_and_update(all_mappings):
    """Upload verified images to GCS and update Firestore."""
    # Limit to MAX_IMAGES per product
    for code in all_mappings:
        all_mappings[code].sort(key=lambda x: x["distance"])
        all_mappings[code] = all_mappings[code][:MAX_IMAGES]

    # Upload to GCS
    client = storage.Client(project="ai-agents-go")
    bucket = client.bucket(BUCKET_NAME)

    uploaded_files = set()
    for code, imgs in all_mappings.items():
        for img in imgs:
            if img["filename"] in uploaded_files:
                continue
            local_path = os.path.join(IMG_DIR, img["filename"])
            if not os.path.exists(local_path):
                continue
            blob_name = f"{GCS_PREFIX}/{img['filename']}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(local_path, content_type="image/jpeg")
            uploaded_files.add(img["filename"])

    print(f"  Uploaded {len(uploaded_files)} unique images to GCS")

    # Clear old images and set new ones in Firestore
    db = firestore.Client(project="ai-agents-go", database="leka-product-catalogs")

    # First clear all existing
    batch = db.batch()
    bc = 0
    for doc in db.collection("products_wisdom").stream():
        if doc.to_dict().get("images"):
            batch.update(doc.reference, {"images": []})
            bc += 1
            if bc >= 400:
                batch.commit()
                batch = db.batch()
                bc = 0
    if bc > 0:
        batch.commit()
    print(f"  Cleared images from {bc} products")

    # Set verified images
    batch = db.batch()
    bc = 0
    updated = 0
    for code, imgs in all_mappings.items():
        doc_ref = db.collection("products_wisdom").document(code)
        doc = doc_ref.get()
        if not doc.exists:
            continue
        image_entries = []
        for i, img in enumerate(imgs):
            image_entries.append({
                "url": f"https://storage.googleapis.com/{BUCKET_NAME}/{GCS_PREFIX}/{img['filename']}",
                "alt_text": f"Product image from {img['catalog']} p{img['page']}",
                "is_primary": i == 0,
                "source": f"catalog_pdf_{img['catalog']}_verified",
            })
        batch.update(doc_ref, {
            "images": image_entries,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
        bc += 1
        updated += 1
        if bc >= 400:
            batch.commit()
            batch = db.batch()
            bc = 0
            print(f"  Updated {updated} products...")

    if bc > 0:
        batch.commit()

    print(f"  Total updated: {updated} products")
    return updated


def main():
    import sys
    sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print("Loading product codes from Firestore...")
    product_codes = load_product_codes()
    print(f"  {len(product_codes)} products in Firestore")

    catalogs = [
        ("2025 Wisdom catalog.pdf", "wisdom_2025"),
        ("2025-06-13 International catalogue 06 06 2025.pdf", "intl_2025"),
        ("2025-06-13 USA Catalogue 06 06 2025.pdf", "usa_2025"),
        ("2025-06-19 Europe Playground Product Catalogue update 202506.pdf", "europe_2025"),
    ]

    all_mappings = {}

    for fname, cat_name in catalogs:
        fpath = os.path.join(DOWNLOADS_DIR, fname)
        if not os.path.exists(fpath):
            print(f"Skip {fname}: not found")
            continue

        print(f"\n=== {fname} ===")
        print("Building text index...")
        pdf_index = build_pdf_index(fpath)
        print(f"  {len(pdf_index)} unique codes found in PDF")

        print("Mapping products to images...")
        mappings = map_products_to_images(fpath, cat_name, product_codes, pdf_index)
        print(f"  {len(mappings)} products mapped")

        # Merge (keep best distance)
        for code, imgs in mappings.items():
            if code not in all_mappings:
                all_mappings[code] = []
            all_mappings[code].extend(imgs)

    # Deduplicate by filename
    for code in all_mappings:
        seen = set()
        unique = []
        for img in sorted(all_mappings[code], key=lambda x: x["distance"]):
            if img["filename"] not in seen:
                seen.add(img["filename"])
                unique.append(img)
        all_mappings[code] = unique[:MAX_IMAGES]

    print(f"\n=== SUMMARY ===")
    print(f"Products with verified images: {len(all_mappings)}")
    counts = defaultdict(int)
    for imgs in all_mappings.values():
        counts[len(imgs)] += 1
    for k in sorted(counts):
        print(f"  {k} image(s): {counts[k]} products")

    # Save mapping
    with open(os.path.join(IMG_DIR, "verified_mapping.json"), "w", encoding="utf-8") as f:
        json.dump(all_mappings, f, ensure_ascii=False, indent=2, default=str)

    print("\n=== UPLOADING & UPDATING FIRESTORE ===")
    upload_and_update(all_mappings)

    print("\nDone!")


if __name__ == "__main__":
    main()
