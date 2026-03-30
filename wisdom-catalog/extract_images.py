"""
Extract product images from Wisdom catalog PDFs.
Maps images to product codes by extracting nearby text on each page.
Uploads to GCS and updates Firestore.
"""
import os
import re
import io
import json
import hashlib
import fitz  # PyMuPDF
from google.cloud import storage, firestore

SERVICE_ACCOUNT_PATH = r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-4c81b70995db.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_PATH

DOWNLOADS_DIR = r"C:\Users\eukri\OneDrive\Documents\Claude Code\2026 Product Catalogs Claude\Wisdom Slack Downloads"
LOCAL_IMG_DIR = r"C:\Users\eukri\OneDrive\Documents\Claude Code\2026 Product Catalogs Claude\extracted_images"
BUCKET_NAME = "ai-agents-go-documents"
GCS_PREFIX = "product-images"
GCS_BASE_URL = f"https://storage.googleapis.com/{BUCKET_NAME}/{GCS_PREFIX}"

os.makedirs(LOCAL_IMG_DIR, exist_ok=True)


def extract_product_codes_from_page(page):
    """Extract all product codes found on a page."""
    text = page.get_text()
    # Match patterns like KB1-TKC1A002, QSWP-350106N06, HW1-S723, SW35RP-A0004, etc.
    patterns = [
        r'[A-Z]{2,5}\d?-[A-Z]*\d+[A-Z]*\d*',  # KB1-TKC1A002, HW1-S723
        r'QSWP-\d+[A-Z]\d+',                      # QSWP-350106N06
        r'WPPE-\d+[A-Z]?\d*',                      # WPPE-350001C15
        r'SW\d+[A-Z]*-[A-Z]\d+',                   # SW35RP-A0004
        r'SR-\d+',                                  # SR-21036
        r'\d{2,3}-\d{5}(?:-\d+)?',                  # 63-21029-110113, 72-21014
    ]
    codes = set()
    for pat in patterns:
        for m in re.finditer(pat, text):
            code = m.group(0)
            if len(code) >= 5:  # skip very short matches
                codes.add(code)
    return codes


def extract_images_from_pdf(pdf_path, catalog_name, min_size=5000):
    """Extract images from PDF, map to product codes, save locally."""
    doc = fitz.open(pdf_path)
    results = []
    seen_hashes = set()

    print(f"Processing: {os.path.basename(pdf_path)} ({len(doc)} pages)")

    for page_num in range(len(doc)):
        page = doc[page_num]
        codes = extract_product_codes_from_page(page)
        images = page.get_images(full=True)

        for img_idx, img_info in enumerate(images):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue

            if not base_image or len(base_image["image"]) < min_size:
                continue

            img_data = base_image["image"]
            img_ext = base_image.get("ext", "png")
            width = base_image.get("width", 0)
            height = base_image.get("height", 0)

            # Skip tiny images (icons, logos)
            if width < 80 or height < 80:
                continue

            # Deduplicate by hash
            img_hash = hashlib.md5(img_data).hexdigest()[:12]
            if img_hash in seen_hashes:
                continue
            seen_hashes.add(img_hash)

            # Filename
            fname = f"{catalog_name}_p{page_num+1:04d}_img{img_idx}_{img_hash}.{img_ext}"
            local_path = os.path.join(LOCAL_IMG_DIR, fname)

            with open(local_path, "wb") as f:
                f.write(img_data)

            results.append({
                "local_path": local_path,
                "filename": fname,
                "page": page_num + 1,
                "width": width,
                "height": height,
                "size_bytes": len(img_data),
                "product_codes": list(codes),
                "catalog": catalog_name,
            })

    doc.close()
    return results


def upload_to_gcs(results):
    """Upload extracted images to GCS bucket."""
    client = storage.Client(project="ai-agents-go")
    bucket = client.bucket(BUCKET_NAME)
    uploaded = []

    for i, r in enumerate(results):
        blob_name = f"{GCS_PREFIX}/catalog/{r['filename']}"
        blob = bucket.blob(blob_name)
        ext = r['filename'].split('.')[-1]
        content_type = f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"
        blob.upload_from_filename(r["local_path"], content_type=content_type)
        blob.make_public()
        r["gcs_url"] = blob.public_url
        uploaded.append(r)
        if (i + 1) % 50 == 0:
            print(f"  Uploaded {i+1}/{len(results)} images...")

    return uploaded


def update_firestore(results):
    """Link uploaded images to products in Firestore."""
    db = firestore.Client(project="ai-agents-go")

    # Build mapping: product_code -> list of images
    code_to_images = {}
    for r in results:
        for code in r.get("product_codes", []):
            if code not in code_to_images:
                code_to_images[code] = []
            code_to_images[code].append({
                "url": r["gcs_url"],
                "alt_text": f"Product image from {r['catalog']} page {r['page']}",
                "is_primary": len(code_to_images[code]) == 0,
                "source": f"catalog_pdf_{r['catalog']}",
            })

    updated = 0
    not_found = 0
    for code, images in code_to_images.items():
        doc_ref = db.collection("products").document(code)
        doc = doc_ref.get()
        if doc.exists:
            existing = doc.to_dict().get("images", [])
            existing_urls = {img.get("url") for img in existing}
            new_images = [img for img in images if img["url"] not in existing_urls]
            if new_images:
                # If no existing images, first new one is primary
                if not existing:
                    new_images[0]["is_primary"] = True
                doc_ref.update({
                    "images": existing + new_images,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                })
                updated += 1
        else:
            not_found += 1

    print(f"  Updated {updated} products, {not_found} codes not found in Firestore")
    return updated


def main():
    catalogs = [
        ("2025 Wisdom catalog.pdf", "wisdom_2025"),
        ("2025-06-13 International catalogue 06 06 2025.pdf", "intl_2025"),
        ("2025-06-13 USA Catalogue 06 06 2025.pdf", "usa_2025"),
        ("2025-06-19 Europe Playground Product Catalogue update 202506.pdf", "europe_2025"),
    ]

    all_results = []
    for fname, cat_name in catalogs:
        fpath = os.path.join(DOWNLOADS_DIR, fname)
        if not os.path.exists(fpath):
            print(f"Skip {fname}: not found")
            continue
        results = extract_images_from_pdf(fpath, cat_name)
        print(f"  Extracted {len(results)} images")
        all_results.extend(results)

    print(f"\nTotal images extracted: {len(all_results)}")

    # Save manifest
    manifest_path = os.path.join(LOCAL_IMG_DIR, "manifest.json")
    manifest = [{k: v for k, v in r.items() if k != "local_path"} for r in all_results]
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("\n=== Uploading to GCS ===")
    uploaded = upload_to_gcs(all_results)
    print(f"  Uploaded {len(uploaded)} images to gs://{BUCKET_NAME}/catalog/")

    print("\n=== Updating Firestore ===")
    update_firestore(uploaded)

    print("\nDone!")


if __name__ == "__main__":
    main()
