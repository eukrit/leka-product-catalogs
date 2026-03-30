"""
Shared image extraction and upload pipeline for all brands.

Handles: PDF extraction → format conversion → GCS upload → Firestore mapping.
"""
import os
import re
import fitz  # PyMuPDF
from PIL import Image
from io import BytesIO
from google.cloud import storage


GCS_BUCKET = "ai-agents-go-documents"
GCS_BASE_PATH = "product-images"


def extract_images_from_pdf(pdf_path, output_dir, brand, catalog_name="catalog"):
    """Extract images from a PDF and save to output_dir.

    Args:
        pdf_path: Path to the PDF file
        output_dir: Local directory to save extracted images
        brand: Brand slug (e.g. "wisdom")
        catalog_name: Catalog identifier for naming

    Returns:
        List of dicts: [{filename, page, path}, ...]
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    extracted = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        images = page.get_images(full=True)

        for img_idx, img_info in enumerate(images):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            # Convert non-browser formats to JPEG
            if image_ext in ("jpx", "jp2", "jbig2"):
                img = Image.open(BytesIO(image_bytes))
                buf = BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=90)
                image_bytes = buf.getvalue()
                image_ext = "jpeg"

            filename = f"{brand}_{catalog_name}_p{page_num + 1}_{img_idx}.{image_ext}"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)

            extracted.append({
                "filename": filename,
                "page": page_num + 1,
                "path": filepath,
            })

    doc.close()
    return extracted


def upload_images_to_gcs(image_paths, brand, subfolder="catalog"):
    """Upload local images to GCS.

    Args:
        image_paths: List of local file paths
        brand: Brand slug
        subfolder: Subfolder within brand's image directory

    Returns:
        List of GCS URLs
    """
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    urls = []

    for path in image_paths:
        filename = os.path.basename(path)
        gcs_path = f"{GCS_BASE_PATH}/{brand}/{subfolder}/{filename}"
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(path)
        urls.append(f"gs://{GCS_BUCKET}/{gcs_path}")

    return urls


def build_image_entry(url, alt_text="", is_primary=False, source="catalog_pdf"):
    """Create a standard image entry dict for Firestore."""
    return {
        "url": url,
        "alt_text": alt_text,
        "is_primary": is_primary,
        "source": source,
    }
